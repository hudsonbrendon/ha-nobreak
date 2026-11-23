"""Buttons for the allow-listed upsd instant commands."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .controls import BUTTONS
from .coordinator import NobreakConfigEntry, NobreakCoordinator
from .entity import NobreakEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: NobreakConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    c = entry.runtime_data
    async_add_entities(
        NobreakButton(c, key, cmd) for key, cmd in BUTTONS.items() if cmd in c.commands
    )


class NobreakButton(NobreakEntity, ButtonEntity):
    def __init__(self, coordinator: NobreakCoordinator, key: str, command: str) -> None:
        super().__init__(coordinator, key)
        self._command = command

    async def async_press(self) -> None:
        await self.coordinator.async_command(self._command)
