"""Calendar with one event per power outage."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import NobreakConfigEntry
from .entity import NobreakEntity
from .tracker import Tracker


def _minutes(seconds: float) -> str:
    return f"{seconds / 60:.0f} min" if seconds >= 60 else f"{seconds:.0f} s"


def outage_events(tracker: Tracker, now: datetime) -> list[CalendarEvent]:
    """Logged outages plus the one in progress (ending now)."""
    events = []
    for o in tracker.outage_log:
        start, end = datetime.fromisoformat(o["inicio"]), datetime.fromisoformat(o["fim"])
        events.append(
            CalendarEvent(
                start=start,
                end=max(end, start + timedelta(seconds=1)),
                summary=f"Queda de energia ({_minutes(o['segundos'])})",
                description=(
                    f"Bateria {o.get('carga_inicial')}% → {o.get('carga_minima')}%, "
                    f"{o.get('energia_kwh', 0) * 1000:.0f} Wh da bateria"
                ),
            )
        )
    if tracker.outage_start is not None:
        events.append(
            CalendarEvent(
                start=tracker.outage_start,
                end=max(now, tracker.outage_start + timedelta(seconds=1)),
                summary="Queda de energia (em andamento)",
                description=f"Bateria {tracker.outage_start_charge}% no início",
            )
        )
    return events


async def async_setup_entry(
    hass: HomeAssistant, entry: NobreakConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([NobreakOutageCalendar(entry.runtime_data, "quedas")])


class NobreakOutageCalendar(NobreakEntity, CalendarEntity):
    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.utcnow()
        events = outage_events(self.coordinator.tracker, now)
        current = [e for e in events if e.start <= now <= e.end]
        return current[-1] if current else (events[-1] if events else None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        events = outage_events(self.coordinator.tracker, dt_util.utcnow())
        return [e for e in events if e.end > start_date and e.start < end_date]
