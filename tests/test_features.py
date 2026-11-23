"""Outage -> load shedding -> events/calendar/repairs, and the actions, against the fake upsd."""

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.nobreak.const import DOMAIN

UID = "APC by Schneider_BZ1500XLBI-BR_VIDE ETIQUETA"


async def _setup(hass: HomeAssistant, upsd, options: dict) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=UID,
        data={"host": "127.0.0.1", "port": upsd.port, "username": "admin", "password": "s3cret", "ups": "myups"},
        options=options,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _ids(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, str]:
    return {e.translation_key: e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}


async def test_outage_shedding_events_calendar(hass: HomeAssistant, upsd) -> None:
    hass.states.async_set("switch.impressora", "on")
    hass.states.async_set("light.fita", "on")
    hass.states.async_set("light.apagada", "off")
    off = async_mock_service(hass, "homeassistant", "turn_off")
    on = async_mock_service(hass, "homeassistant", "turn_on")
    entry = await _setup(
        hass,
        upsd,
        {
            "tarifa": 1.0,
            "economia_estagio1": ["switch.impressora", "light.apagada"],
            "economia_atraso": 0,
            "economia_estagio2": ["light.fita"],
            "economia_carga": 50,
        },
    )
    ids = _ids(hass, entry)
    for key in ("saude_da_bateria", "autonomia_real", "energia_hoje", "custo_hoje", "custo_do_mes",
                "tensao_minima_hoje", "tempo_fora_da_faixa_hoje", "quedas_hoje", "quedas", "eventos",
                "economia_automatica"):
        assert key in ids, key
    coordinator = entry.runtime_data

    upsd.vars.update({"ups.status": "OB DISCHRG", "battery.charge": "90"})
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ids["eventos"]).attributes["event_type"] in ("queda", "economia")
    assert off and off[0].data["entity_id"] == ["switch.impressora"]  # the light already off is left alone
    assert hass.states.get(ids["quedas_hoje"]).state == "1"
    assert hass.states.get(ids["quedas"]).state == "on"  # outage in progress

    upsd.vars["battery.charge"] = "45"
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert off[-1].data["entity_id"] == ["light.fita"]

    upsd.vars.update({"ups.status": "OL CHRG", "battery.charge": "46"})
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert sorted(on[-1].data["entity_id"]) == ["light.fita", "switch.impressora"]
    assert hass.states.get(ids["eventos"]).attributes["event_type"] == "economia"
    assert len(coordinator.tracker.outage_log) == 1
    assert hass.states.get(ids["quedas_de_energia"]).attributes["historico"][0]["carga_minima"] == 45

    # shedding switched off: an outage turns nothing off
    await hass.services.async_call("switch", "turn_off", {"entity_id": ids["economia_automatica"]}, blocking=True)
    calls = len(off)
    upsd.vars["ups.status"] = "OB"
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(off) == calls


async def test_repairs_and_actions(hass: HomeAssistant, upsd) -> None:
    entry = await _setup(hass, upsd, {})
    coordinator = entry.runtime_data

    upsd.vars["ups.status"] = "OL RB"
    await coordinator.async_refresh()
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"substituir_bateria_{entry.entry_id}")
    upsd.vars["ups.status"] = "OL"
    await coordinator.async_refresh()
    assert not ir.async_get(hass).async_get_issue(DOMAIN, f"substituir_bateria_{entry.entry_id}")

    await hass.services.async_call(DOMAIN, "comando", {"comando": "test.panel.start"}, blocking=True)
    assert "INSTCMD myups test.panel.start" in upsd.received
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, "comando", {"comando": "load.off"}, blocking=True)

    await hass.services.async_call(
        DOMAIN, "definir_variavel", {"variavel": "input.transfer.low", "valor": "170"}, blocking=True
    )
    assert 'SET VAR myups input.transfer.low "170"' in upsd.received
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "definir_variavel", {"variavel": "driver.flag.allow_killpower", "valor": "1"}, blocking=True
        )


async def test_options_flow(hass: HomeAssistant, upsd) -> None:
    entry = await _setup(hass, upsd, {})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"tarifa": 0.92, "economia_estagio1": ["switch.x"], "economia_atraso": 3, "economia_estagio2": [],
         "economia_carga": 40, "economia_religar": False},
    )
    await hass.async_block_till_done()
    assert entry.options["tarifa"] == 0.92 and entry.options["economia_atraso"] == 3
    assert entry.runtime_data.price == 0.92
