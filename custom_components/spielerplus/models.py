"""Data models and enums for the SpielerPlus integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum


class Participation(StrEnum):
    """Participation state of a member for an event."""

    ZUSAGE = "zusage"
    UNSICHER = "unsicher"
    ABSAGE = "absage"
    OFFEN = "offen"


@dataclass(frozen=True, slots=True)
class SpMember:
    """A member/team entry of the logged-in SpielerPlus account."""

    id: str
    name: str
    team: str

    @property
    def label(self) -> str:
        """Human readable label, e.g. ``Kind Eins (Team A)``."""
        return f"{self.name} ({self.team})"


@dataclass(frozen=True, slots=True)
class SpEvent:
    """An event panel as parsed from the SpielerPlus events page."""

    id: str
    type: str
    title: str
    day: int
    month: int
    start_time: time | None = None
    end_time: time | None = None
    meeting_time: time | None = None
    location: str | None = None
    participation: Participation = Participation.OFFEN
    deadline_passed: bool = False
    url: str | None = None


@dataclass(frozen=True, slots=True)
class ResolvedEvent:
    """An event with its day/month resolved to concrete datetimes."""

    event: SpEvent
    start: datetime
    end: datetime
    meeting: datetime | None = None
