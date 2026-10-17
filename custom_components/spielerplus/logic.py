"""Pure derivation logic for the SpielerPlus integration.

No network and no Home Assistant imports: everything here is unit-testable.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from .const import PARTICIPATION_VALUES
from .models import Participation, ResolvedEvent, SpEvent, SpMember

#: A day/month combination up to this many days in the past still belongs to the
#: current year; further in the past it is assumed to mean next year (new year
#: rollover on the events page).
_PAST_TOLERANCE_DAYS = 30


def participation_value(status: Participation) -> str:
    """Return the ``Participation[participation]`` value for a status."""
    return PARTICIPATION_VALUES[status]


def resolve_year(day: int, month: int, today: date) -> int:
    """Resolve the year for a ``day.month`` pair shown on the events page."""
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return today.year
    if (today - candidate).days > _PAST_TOLERANCE_DAYS:
        return today.year + 1
    return today.year


def resolve_event(event: SpEvent, today: date) -> ResolvedEvent:
    """Resolve an event's day/month into concrete datetimes."""
    day = date(resolve_year(event.day, event.month, today), event.month, event.day)
    start = datetime.combine(day, event.start_time or time(0, 0))
    end = (
        datetime.combine(day, event.end_time)
        if event.end_time is not None
        else start + timedelta(hours=1)
    )
    meeting = (
        datetime.combine(day, event.meeting_time)
        if event.meeting_time is not None
        else None
    )
    return ResolvedEvent(event=event, start=start, end=end, meeting=meeting)


def resolve_events(events: list[SpEvent], today: date) -> list[ResolvedEvent]:
    """Resolve a list of events and sort them by start datetime."""
    return sorted((resolve_event(event, today) for event in events), key=lambda r: r.start)


def upcoming(events: list[ResolvedEvent], now: datetime) -> list[ResolvedEvent]:
    """Return the events that start at or after ``now``."""
    return [event for event in events if event.start >= now]


def next_event(
    events: list[ResolvedEvent], now: datetime, type_: str | None = None
) -> ResolvedEvent | None:
    """Return the next event (optionally of a given type) at or after ``now``."""
    for event in events:
        if event.start < now:
            continue
        if type_ is not None and event.event.type != type_:
            continue
        return event
    return None


def _event_attributes(event: ResolvedEvent) -> dict[str, object]:
    inner = event.event
    return {
        "event_id": inner.id,
        "event_type": inner.type,
        "title": inner.title,
        "start": event.start.isoformat(),
        "end": event.end.isoformat(),
        "meeting_time": event.meeting.isoformat() if event.meeting else None,
        "location": inner.location,
        "participation": str(inner.participation),
        "deadline_passed": inner.deadline_passed,
        "url": inner.url,
    }


def sensor_state(
    event: ResolvedEvent | None, upcoming_events: list[ResolvedEvent]
) -> tuple[datetime | None, dict[str, object]]:
    """Build the native value and attributes for a next-event sensor."""
    if event is None:
        return None, {}
    attributes = _event_attributes(event)
    attributes["events"] = [_event_attributes(item) for item in upcoming_events]
    return event.start, attributes


def calendar_range(
    events: list[ResolvedEvent], start: date, end: date
) -> list[ResolvedEvent]:
    """Return the events whose start date lies within ``[start, end]``."""
    return [event for event in events if start <= event.start.date() <= end]


def event_summary(event: SpEvent) -> str:
    """Short calendar title for an event."""
    return "Training" if event.type == "training" else event.title


def member_options(members: list[SpMember]) -> dict[str, str]:
    """Map member ids to their display labels (for the config flow)."""
    return {member.id: member.label for member in members}
