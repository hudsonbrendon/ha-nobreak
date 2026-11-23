"""Beeper switch."""

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
    if {BEEPER_ON, BEEPER_OFF} <= c.commands and "ups.beeper.status" in c.data:
        async_add_entities([NobreakBeeper(c, "alarme_sonoro")])


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
