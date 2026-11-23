"""Event entity: outage, power back, self-test, battery measurement, load shedding."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import EVENT_TYPES
from .coordinator import NobreakConfigEntry
from .entity import NobreakEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: NobreakConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([NobreakEvents(entry.runtime_data, "eventos")])


class NobreakEvents(NobreakEntity, EventEntity):
    _attr_event_types = EVENT_TYPES

    @callback
    def _handle_coordinator_update(self) -> None:
        # several events can come out of one poll (power back + battery
        # measurement + shedding undone); each needs its own state write
        for event_type, attrs in self.coordinator.events:
            self._trigger_event(event_type, attrs)
            self.async_write_ha_state()
        if not self.coordinator.events:
            super()._handle_coordinator_update()
