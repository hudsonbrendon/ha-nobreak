"""Config flow + setup against the fake upsd."""

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.nobreak.const import DOMAIN

UID = "APC by Schneider_BZ1500XLBI-BR_VIDE ETIQUETA"


async def test_flow_setup_and_controls(hass: HomeAssistant, upsd) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"host": "127.0.0.1", "port": upsd.port, "username": "admin", "password": "s3cret"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.unique_id == UID and entry.data["ups"] == "myups"
    await hass.async_block_till_done()

    ents = {e.translation_key: e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    # load.off / shutdown.reboot must never become buttons
    assert not any("load" in k or "reboot" in k for k in ents)
    assert {"potencia_de_saida", "energia_de_saida", "sensibilidade", "transferencia_baixa", "data_da_bateria",
            "alarme_sonoro", "autoteste_rapido", "rede_eletrica"} <= set(ents)
    assert "carga_minima" not in ents  # not writable on this unit

    load = float(upsd.vars["ups.load"])
    assert float(hass.states.get(ents["potencia_de_saida"]).state) == round(load * 825 / 100, 1)
    assert hass.states.get(ents["rede_eletrica"]).state == "on"
    assert hass.states.get(ents["data_da_bateria"]).state == "unknown"  # 2107/15/31 is garbage

    await hass.services.async_call("select", "select_option", {"entity_id": ents["sensibilidade"], "option": "high"}, blocking=True)
    await hass.services.async_call("date", "set_value", {"entity_id": ents["data_da_bateria"], "date": "2026-11-23"}, blocking=True)
    await hass.services.async_call("button", "press", {"entity_id": ents["autoteste_rapido"]}, blocking=True)
    await hass.services.async_call("switch", "turn_on", {"entity_id": ents["alarme_sonoro"]}, blocking=True)
    assert 'SET VAR myups input.sensitivity "high"' in upsd.received
    assert 'SET VAR myups battery.mfr.date "2026/11/23"' in upsd.received
    assert "INSTCMD myups test.battery.start.quick" in upsd.received
    assert "INSTCMD myups beeper.enable" in upsd.received
    assert hass.states.get(ents["data_da_bateria"]).state == "2026-11-23"
    assert hass.states.get(ents["idade_da_bateria"]).state is not None

    dup = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    dup = await hass.config_entries.flow.async_configure(dup["flow_id"], {"host": "127.0.0.1", "port": upsd.port})
    assert dup["reason"] == "already_configured"

    assert await hass.config_entries.async_unload(entry.entry_id)
