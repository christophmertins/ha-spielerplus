"""Calendar platform for the SpielerPlus integration."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import const
from .coordinator import SpielerplusCoordinator
from .entity import SpielerplusEntity
from .logic import calendar_range, event_summary
from .models import ResolvedEvent


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one calendar per member."""
    coordinator: SpielerplusCoordinator = hass.data[const.DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_add_entities(
        SpielerplusCalendar(coordinator, entry, member_id)
        for member_id in coordinator.members
    )


class SpielerplusCalendar(SpielerplusEntity, CalendarEntity):
    """Upcoming events of one member as a Home Assistant calendar."""

    _attr_name = None
    _attr_icon = "mdi:calendar-account"

    def __init__(
        self,
        coordinator: SpielerplusCoordinator,
        entry: ConfigEntry,
        member_id: str,
    ) -> None:
        super().__init__(coordinator, entry, member_id)
        self._attr_unique_id = f"{entry.entry_id}:{member_id}:calendar"

    @property
    def event(self) -> CalendarEvent | None:
        """The next upcoming event."""
        upcoming = self.events
        return self._to_calendar_event(upcoming[0]) if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Events within a Home Assistant calendar query range."""
        return [
            self._to_calendar_event(event)
            for event in calendar_range(
                self.events, start_date.date(), end_date.date()
            )
        ]

    @staticmethod
    def _to_calendar_event(event: ResolvedEvent) -> CalendarEvent:
        inner = event.event
        return CalendarEvent(
            start=event.start,
            end=event.end,
            summary=event_summary(inner),
            location=inner.location,
            description=f"{inner.type} · {inner.participation}",
            uid=f"{inner.type}-{inner.id}",
        )
