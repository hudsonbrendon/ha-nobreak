"""Beeper and load-shedding switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .controls import BEEPER_OFF, BEEPER_ON
from .coordinator import NobreakConfigEntry
from .entity import NobreakEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: NobreakConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    c = entry.runtime_data
    entities: list[SwitchEntity] = [NobreakShedding(c, "economia_automatica")]
    if {BEEPER_ON, BEEPER_OFF} <= c.commands and "ups.beeper.status" in c.data:
        entities.append(NobreakBeeper(c, "alarme_sonoro"))
    async_add_entities(entities)


class NobreakBeeper(NobreakEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        # "muted" is still enabled, only silenced until the next event
        return self.coordinator.data.get("ups.beeper.status") in ("enabled", "muted")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(BEEPER_ON)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(BEEPER_OFF)


class NobreakShedding(NobreakEntity, SwitchEntity):
    """Enables the two-stage load shedding configured in the options."""

    _attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        return self.coordinator.tracker.shed_enabled

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        t = self.coordinator.tracker
        return {"desligados_agora": t.shed_off, "estagio_1": t.shed_stage1, "estagio_2": t.shed_stage2}

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.tracker.shed_enabled = True
        await self.coordinator.async_save()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.tracker.shed_enabled = False
        await self.coordinator.async_save()
        self.async_write_ha_state()
