"""Pure HTML parsing helpers for SpielerPlus pages.

These functions never touch the network or Home Assistant, so they can be
unit-tested in isolation.
"""

from __future__ import annotations

import re
from datetime import time

from bs4 import BeautifulSoup
from bs4.element import Tag

from .models import Participation, SpEvent, SpMember

_SWITCH_USER_RE = re.compile(r"switch-user\?id=(\d+)")
_PANEL_ID_RE = re.compile(r"^event-([a-z]+)-(\d+)$")
_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})")
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")

_STATUS_BY_TITLE = {
    "Zugesagt": Participation.ZUSAGE,
    "Unsicher": Participation.UNSICHER,
    "Absagen / Abwesend": Participation.ABSAGE,
}


def parse_members(html: str) -> list[SpMember]:
    """Parse the ``/site/select-team`` page into the account's members.

    Handles both the desktop markup (``.select-team-item`` with ``h4.dark`` /
    ``small``) and the mobile markup (``.list-item`` with ``.list-label`` /
    ``.list-sublabel``). Duplicates (same ``switch-user`` id) are collapsed to
    their first occurrence.
    """
    soup = BeautifulSoup(html, "html.parser")
    members: list[SpMember] = []
    seen: set[str] = set()

    for anchor in soup.select('a[href*="switch-user?id="]'):
        match = _SWITCH_USER_RE.search(anchor.get("href", ""))
        if match is None:
            continue
        member_id = match.group(1)
        if member_id in seen:
            continue

        item = anchor.find_parent(class_="select-team-item") or anchor.find_parent(
            class_="list-item"
        )
        if item is None:
            continue

        team_el = item.select_one("h4.dark") or item.select_one(".list-label")
        name_el = item.select_one("small") or item.select_one(".list-sublabel")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            continue

        seen.add(member_id)
        members.append(
            SpMember(
                id=member_id,
                name=name,
                team=team_el.get_text(strip=True) if team_el else "",
            )
        )

    return members


def _parse_time(text: str) -> time | None:
    match = _TIME_RE.search(text.strip())
    if match is None:
        return None
    return time(int(match.group(1)), int(match.group(2)))


def _participation_and_deadline(panel: Tag) -> tuple[Participation, bool]:
    status = Participation.OFFEN
    disabled = False
    for button in panel.select(".participation-widget-buttons button"):
        if button.has_attr("disabled"):
            disabled = True
        if "selected" in (button.get("class") or []):
            status = _STATUS_BY_TITLE.get(
                (button.get("title") or "").strip(), Participation.OFFEN
            )
    deadline_passed = disabled or panel.select_one(".countdown") is not None
    return status, deadline_passed


def parse_events(html: str) -> list[SpEvent]:
    """Parse the ``/events`` page (and its ajax fragments) into events."""
    soup = BeautifulSoup(html, "html.parser")
    events: list[SpEvent] = []

    for panel in soup.select('div.panel[id^="event-"]'):
        id_match = _PANEL_ID_RE.match(panel.get("id", ""))
        if id_match is None:
            continue
        event_type, event_id = id_match.group(1), id_match.group(2)

        title_el = panel.select_one(".panel-heading-text .panel-title")
        date_el = panel.select_one(".panel-heading-info .panel-subtitle")
        if title_el is None or date_el is None:
            continue
        title = title_el.get_text(strip=True)
        date_match = _DATE_RE.search(date_el.get_text())
        if not title or date_match is None:
            continue

        times: dict[str, time | None] = {}
        for item in panel.select(".event-time-item"):
            label_el = item.select_one(".event-time-label")
            value_el = item.select_one(".event-time-value")
            if label_el is None or value_el is None:
                continue
            times[label_el.get_text(strip=True).lower()] = _parse_time(
                value_el.get_text()
            )

        status, deadline_passed = _participation_and_deadline(panel)
        link = panel.select_one("a.event-header-border")

        events.append(
            SpEvent(
                id=event_id,
                type=event_type,
                title=title,
                day=int(date_match.group(1)),
                month=int(date_match.group(2)),
                start_time=times.get("beginn"),
                end_time=times.get("ende"),
                meeting_time=times.get("treffen"),
                location=None,
                participation=status,
                deadline_passed=deadline_passed,
                url=link.get("href") if link else None,
            )
        )

    return events
