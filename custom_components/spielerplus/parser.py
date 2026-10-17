"""Pure HTML parsing helpers for SpielerPlus pages.

These functions never touch the network or Home Assistant, so they can be
unit-tested in isolation.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .models import SpMember

_SWITCH_USER_RE = re.compile(r"switch-user\?id=(\d+)")


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
