"""HTTP client for the SpielerPlus web application.

This is the only module that talks to the network. It wraps an ``aiohttp``
session and speaks the same requests the website's own JavaScript uses.
"""

from __future__ import annotations

import asyncio
import json
import re

import aiohttp

from . import const
from .logic import participation_value
from .models import Participation, SpEvent, SpMember
from .parser import parse_events, parse_members

_META_CSRF_RE = re.compile(r'<meta[^>]+name="csrf-token"[^>]+content="([^"]+)"')
_INPUT_CSRF_RE = re.compile(r'<input[^>]+name="_csrf"[^>]+value="([^"]+)"')
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

_LOGIN_TITLES = {"Einloggen", "Login"}

#: SpielerPlus answers non-browser user agents with HTTP 403.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9",
}


class SpielerplusError(Exception):
    """Raised for any non-auth problem talking to SpielerPlus."""


class SpielerplusAuthError(SpielerplusError):
    """Raised when a request is not authenticated (login page returned)."""


def _title(html: str) -> str:
    match = _TITLE_RE.search(html)
    return match.group(1).strip() if match else ""


class SpielerplusClient:
    """Session based client. All public methods share one lock."""

    def __init__(
        self, session: aiohttp.ClientSession, email: str, password: str
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        #: Serializes requests so the ``switch-user`` context cannot be raced.
        self.lock = asyncio.Lock()

    async def _get(self, url: str, **kwargs) -> tuple[int, str]:
        try:
            kwargs.setdefault("headers", _HEADERS)
            async with self._session.get(url, **kwargs) as response:
                return response.status, await response.text()
        except aiohttp.ClientError as err:
            raise SpielerplusError(f"GET {url} failed: {err}") from err
        except TimeoutError as err:
            raise SpielerplusError(f"GET {url} timed out") from err

    async def _post(self, url: str, data: dict[str, str]) -> tuple[int, str]:
        try:
            async with self._session.post(
                url, data=data, headers=_HEADERS
            ) as response:
                return response.status, await response.text()
        except aiohttp.ClientError as err:
            raise SpielerplusError(f"POST {url} failed: {err}") from err
        except TimeoutError as err:
            raise SpielerplusError(f"POST {url} timed out") from err

    @staticmethod
    def _extract_csrf(html: str) -> str | None:
        match = _META_CSRF_RE.search(html) or _INPUT_CSRF_RE.search(html)
        return match.group(1) if match else None

    async def async_login(self) -> None:
        """Log in, raising ``SpielerplusAuthError`` on bad credentials."""
        async with self.lock:
            await self._login()

    async def _login(self) -> None:
        status, html = await self._get(const.LOGIN_URL)
        if status != 200:
            raise SpielerplusError(f"login page returned HTTP {status}")

        csrf = self._extract_csrf(html)
        if csrf is None:
            raise SpielerplusError("no CSRF token on login page")

        status, html = await self._post(
            const.LOGIN_URL,
            {
                "_csrf": csrf,
                "LoginForm[email]": self._email,
                "LoginForm[password]": self._password,
            },
        )
        if status != 200:
            raise SpielerplusAuthError(f"login returned HTTP {status}")
        if _title(html) in _LOGIN_TITLES:
            raise SpielerplusAuthError("login was rejected")

    async def async_get_members(self) -> list[SpMember]:
        """Load the account's members/teams from the select-team page."""
        async with self.lock:
            status, html = await self._get(const.SELECT_TEAM_URL)
            if status != 200:
                raise SpielerplusError(f"select-team returned HTTP {status}")
            if _title(html) in _LOGIN_TITLES:
                raise SpielerplusAuthError("not logged in")
            return parse_members(html)

    async def async_select_member(self, member_id: str) -> None:
        """Switch the session context to a member/team."""
        async with self.lock:
            status, _ = await self._get(
                const.SWITCH_USER_URL, params={"id": member_id}
            )
            if status >= 400:
                raise SpielerplusError(f"switch-user returned HTTP {status}")

    async def async_get_events(self) -> list[SpEvent]:
        """Load all events of the currently selected member.

        The first page is server-rendered; further pages are appended through
        ``/events/ajaxgetevents`` until the ajax fragments run out.
        """
        async with self.lock:
            status, html = await self._get(const.EVENTS_URL)
            if status != 200:
                raise SpielerplusError(f"events returned HTTP {status}")
            if _title(html) in _LOGIN_TITLES:
                raise SpielerplusAuthError("not logged in")

            events = parse_events(html)
            seen = {event.id for event in events}
            panels_seen = "event-" in html

            offset = 5
            while True:
                status, body = await self._post(
                    const.AJAX_EVENTS_URL, {"offset": str(offset)}
                )
                if status != 200:
                    raise SpielerplusError(f"ajaxgetevents returned HTTP {status}")
                try:
                    payload = json.loads(body)
                except ValueError as err:
                    raise SpielerplusError("ajaxgetevents returned invalid JSON") from err

                fragment = payload.get("html") or ""
                if "event-" in fragment:
                    panels_seen = True
                for event in parse_events(fragment):
                    if event.id not in seen:
                        seen.add(event.id)
                        events.append(event)

                count = payload.get("count")
                if not fragment or count in (None, -1):
                    break
                offset += 5

            if panels_seen and not events:
                raise SpielerplusError(
                    "event panels were present but none could be parsed "
                    "(SpielerPlus layout changed?)"
                )

            return events

    async def async_set_participation(
        self,
        member_id: str,
        event_type: str,
        event_id: str,
        status: Participation,
        reason: str = "",
    ) -> None:
        """Confirm, decline or mark unsure the attendance for an event.

        SpielerPlus requires a reason for ``unsicher``/``absage`` and answers a
        rejected request with HTTP 200 and ``{"error": true}``, so the body is
        inspected too.
        """
        if not reason and status in (Participation.UNSICHER, Participation.ABSAGE):
            reason = const.DEFAULT_PARTICIPATION_REASON

        async with self.lock:
            http_status, body = await self._post(
                const.PARTICIPATION_URL,
                {
                    "Participation[type]": event_type,
                    "Participation[typeid]": event_id,
                    "Participation[participation]": participation_value(status),
                    "Participation[user_id]": member_id,
                    "Participation[reason]": reason,
                },
            )
            if http_status != 200:
                snippet = " ".join(body.split())[:200]
                raise SpielerplusError(
                    f"participation returned HTTP {http_status}: {snippet}"
                )
            try:
                payload = json.loads(body)
            except ValueError as err:
                raise SpielerplusError("participation returned invalid JSON") from err
            if payload.get("error"):
                raise SpielerplusError(
                    "SpielerPlus rejected the participation request"
                )

