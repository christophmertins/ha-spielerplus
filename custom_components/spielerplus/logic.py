"""Pure derivation logic for the SpielerPlus integration.

No network and no Home Assistant imports: everything here is unit-testable.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, tzinfo

from .const import PARTICIPATION_VALUES
from .models import Participation, ResolvedEvent, SpEvent, SpMember

#: A day/month combination up to this many days in the past still belongs to the
#: current year; further in the past it is assumed to mean next year (new year
#: rollover on the events page).
_PAST_TOLERANCE_DAYS = 30


def participation_value(status: Participation) -> str:
    """Return the ``Participation[participation]`` value for a status."""
    return PARTICIPATION_VALUES[status]


def resolve_year(day: int, month: int, today: date, weekday: int | None = None) -> int:
    """Resolve the year for a ``day.month`` pair shown on the events page.

    When the panel's weekday is known, the year is the one (of the previous,
    current and next year) whose date falls on that weekday — that is exact,
    because two consecutive years never share a weekday for the same date.
    Without a weekday the ``day.month`` is assumed to be current unless it
    lies further in the past than ``_PAST_TOLERANCE_DAYS``.
    """
    if weekday is not None:
        for candidate_year in (today.year, today.year + 1, today.year - 1):
            try:
                candidate = date(candidate_year, month, day)
            except ValueError:  # e.g. 29 February in a non-leap year
                continue
            if candidate.weekday() == weekday:
                return candidate_year
        # A weekday that matches no nearby year: fall through to the heuristic.

    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return today.year
    if (today - candidate).days > _PAST_TOLERANCE_DAYS:
        return today.year + 1
    return today.year


def resolve_event(
    event: SpEvent, today: date, tz: tzinfo | None = None
) -> ResolvedEvent:
    """Resolve an event's day/month into concrete datetimes.

    When ``tz`` is given the resulting datetimes are timezone-aware (Home
    Assistant requires this for ``timestamp`` sensors).
    """
    day = date(
        resolve_year(event.day, event.month, today, event.weekday), event.month, event.day
    )
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
    if tz is not None:
        start = start.replace(tzinfo=tz)
        end = end.replace(tzinfo=tz)
        meeting = meeting.replace(tzinfo=tz) if meeting is not None else None
    return ResolvedEvent(event=event, start=start, end=end, meeting=meeting)


def resolve_events(
    events: list[SpEvent], today: date, tz: tzinfo | None = None
) -> list[ResolvedEvent]:
    """Resolve a list of events and sort them by start datetime."""
    return sorted(
        (resolve_event(event, today, tz) for event in events), key=lambda r: r.start
    )


def upcoming(events: list[ResolvedEvent], now: datetime) -> list[ResolvedEvent]:
    """Return the events that have not finished yet.

    Events that are currently running are kept, so the calendar stays ``on``
    for the duration of a training.
    """
    return [event for event in events if event.end > now]


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
        "summary": describe_event(event),
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


_WEEKDAYS = ("Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa.", "So.")


def event_summary(event: SpEvent) -> str:
    """Short calendar title for an event."""
    return "Training" if event.type == "training" else event.title


def describe_event(event: ResolvedEvent) -> str:
    """Readable one-line description of an event."""
    inner = event.event
    parts = [
        inner.title,
        f"{_WEEKDAYS[event.start.weekday()]} {event.start.strftime('%d.%m.%Y')}",
        f"{event.start.strftime('%H:%M')}-{event.end.strftime('%H:%M')}",
    ]
    if event.meeting is not None:
        parts.append(f"Treffen {event.meeting.strftime('%H:%M')}")
    if inner.location:
        parts.append(inner.location)
    if inner.deadline_passed:
        parts.append("Zu-/Absage abgelaufen")
    return ", ".join(parts)


def member_options(members: list[SpMember]) -> dict[str, str]:
    """Map member ids to their display labels (for the config flow)."""
    return {member.id: member.label for member in members}
