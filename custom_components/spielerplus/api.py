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
from .parser import count_event_panels, parse_events, parse_members

_META_CSRF_RE = re.compile(r'<meta[^>]+name="csrf-token"[^>]+content="([^"]+)"')
_INPUT_CSRF_RE = re.compile(r'<input[^>]+name="_csrf"[^>]+value="([^"]+)"')
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

_LOGIN_TITLES = {"Einloggen", "Login"}
_EVENT_TITLE_PREFIXES = ("Termine", "Events")
#: Safety net so a misbehaving pagination endpoint cannot loop forever.
_MAX_EVENT_PAGES = 50

#: SpielerPlus answers non-browser user agents with HTTP 403.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9",
}

_TIMEOUT = aiohttp.ClientTimeout(total=30)


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
        #: The member the session is currently switched to. ``None`` after a
        #: login, because logging in resets the context to the account default.
        self._member_id: str | None = None

    async def _get(self, url: str, **kwargs) -> tuple[int, str]:
        try:
            kwargs.setdefault("headers", _HEADERS)
            kwargs.setdefault("timeout", _TIMEOUT)
            async with self._session.get(url, **kwargs) as response:
                return response.status, await response.text()
        except aiohttp.ClientError as err:
            raise SpielerplusError(f"GET {url} failed: {err}") from err
        except TimeoutError as err:
            raise SpielerplusError(f"GET {url} timed out") from err

    async def _post(self, url: str, data: dict[str, str]) -> tuple[int, str]:
        try:
            async with self._session.post(
                url, data=data, headers=_HEADERS, timeout=_TIMEOUT
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

    @staticmethod
    def _decode_json(body: str) -> dict | None:
        try:
            value = json.loads(body)
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

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
            # A 5xx or a blocked request is an outage, not a wrong password.
            raise SpielerplusError(f"login returned HTTP {status}")
        if _title(html) in _LOGIN_TITLES:
            raise SpielerplusAuthError("login was rejected")
        # A login resets the session to the account's default member.
        self._member_id = None

    async def async_get_members(self) -> list[SpMember]:
        """Load the account's members/teams from the select-team page."""
        async with self.lock:
            status, html = await self._get(const.SELECT_TEAM_URL)
            if status != 200:
                raise SpielerplusError(f"select-team returned HTTP {status}")
            if _title(html) in _LOGIN_TITLES:
                await self._login()
                status, html = await self._get(const.SELECT_TEAM_URL)
                if status != 200:
                    raise SpielerplusError(f"select-team returned HTTP {status}")
                if _title(html) in _LOGIN_TITLES:
                    raise SpielerplusAuthError("not logged in")
            return parse_members(html)

    async def _select_member_locked(self, member_id: str) -> None:
        status, html = await self._get(const.SWITCH_USER_URL, params={"id": member_id})
        if status >= 400:
            raise SpielerplusError(f"switch-user returned HTTP {status}")
        if _title(html) in _LOGIN_TITLES:
            # On a dead session Yii2 answers the switch with the login page and
            # HTTP 200 instead of switching, so the switch would silently be a
            # no-op and the next read would return another member's events.
            await self._login()
            status, html = await self._get(
                const.SWITCH_USER_URL, params={"id": member_id}
            )
            if status >= 400:
                raise SpielerplusError(f"switch-user returned HTTP {status}")
            if _title(html) in _LOGIN_TITLES:
                raise SpielerplusAuthError("session expired and re-login failed")
        self._member_id = member_id

    async def async_select_member(self, member_id: str) -> None:
        """Switch the session context to a member/team."""
        async with self.lock:
            await self._select_member_locked(member_id)

    async def async_get_events(self) -> list[SpEvent]:
        """Load all events of the currently selected member."""
        async with self.lock:
            return await self._fetch_events_locked()

    async def async_get_member_events(self, member_id: str) -> list[SpEvent]:
        """Switch to a member and load its events under a single lock.

        Switching and reading must not be split: an overlapping write would
        leave the session on another member and the events of the wrong member
        would be stored for this one.
        """
        async with self.lock:
            await self._select_member_locked(member_id)
            return await self._fetch_events_locked(member_id)

    async def _fetch_events_locked(self, member_id: str | None = None) -> list[SpEvent]:
        status, html = await self._get(const.EVENTS_URL)
        if status != 200:
            raise SpielerplusError(f"events returned HTTP {status}")

        if _title(html) in _LOGIN_TITLES:
            await self._login()
            if member_id is not None:
                # The login reset the switched member; re-apply it so these
                # events really belong to the member the caller asked for.
                await self._select_member_locked(member_id)
            status, html = await self._get(const.EVENTS_URL)
            if status != 200:
                raise SpielerplusError(f"events returned HTTP {status}")
            if _title(html) in _LOGIN_TITLES:
                raise SpielerplusAuthError("session expired and re-login failed")

        title = _title(html)
        if not title.startswith(_EVENT_TITLE_PREFIXES):
            raise SpielerplusError(
                f"events page has an unexpected title ({title!r}); "
                "SpielerPlus layout changed?"
            )

        events = self._parse_page_strict(html)
        seen = {event.id for event in events}

        offset = 5
        for _ in range(_MAX_EVENT_PAGES):
            status, body = await self._post(
                const.AJAX_EVENTS_URL, {"offset": str(offset)}
            )
            if status != 200:
                raise SpielerplusError(f"ajaxgetevents returned HTTP {status}")
            payload = self._decode_json(body)
            if payload is None:
                raise SpielerplusError("ajaxgetevents returned invalid JSON")

            fragment = payload.get("html") or ""
            added = 0
            for event in self._parse_page_strict(fragment):
                if event.id not in seen:
                    seen.add(event.id)
                    events.append(event)
                    added += 1

            count = payload.get("count")
            if not fragment or count in (None, -1) or added == 0:
                break
            offset += 5

        return events

    @staticmethod
    def _parse_page_strict(html: str) -> list[SpEvent]:
        """Parse one page, failing when panels are present but unparsable."""
        if not html.strip():
            return []
        expected = count_event_panels(html)
        parsed = parse_events(html)
        if expected and len(parsed) < expected:
            raise SpielerplusError(
                "event panels were present but not all could be parsed "
                "(SpielerPlus layout changed?)"
            )
        return parsed

    async def async_set_participation(
        self,
        member_id: str,
        event_type: str,
        event_id: str,
        status: Participation,
        reason: str = "",
    ) -> None:
        """Confirm, decline or mark unsure the attendance for an event.

        The session must act as the target member: SpielerPlus answers a write
        for a member other than the currently selected one with HTTP 403. It
        also requires a reason for ``unsicher``/``absage`` and answers a
        rejected request with HTTP 200 and ``{"error": true}``, so the body is
        inspected too.
        """
        if not reason and status in (Participation.UNSICHER, Participation.ABSAGE):
            reason = const.DEFAULT_PARTICIPATION_REASON

        data = {
            "Participation[type]": event_type,
            "Participation[typeid]": event_id,
            "Participation[participation]": participation_value(status),
            "Participation[user_id]": member_id,
            "Participation[reason]": reason,
        }

        async with self.lock:
            await self._select_member_locked(member_id)
            payload = await self._participation_locked(data, member_id)
            if payload.get("error"):
                raise SpielerplusError(
                    "SpielerPlus rejected the participation request"
                )

    async def _participation_locked(
        self, data: dict[str, str], member_id: str
    ) -> dict:
        """POST the participation, re-logging in once if the session expired."""
        payload = await self._participation_post(data)
        if payload is not None:
            return payload

        # A non-JSON answer means the login page came back instead.
        await self._login()
        # The login reset the switched member; re-apply it or the retry is sent
        # as the wrong member and SpielerPlus answers 403.
        await self._select_member_locked(member_id)
        payload = await self._participation_post(data)
        if payload is None:
            raise SpielerplusError("participation returned an unexpected response")
        return payload

    async def _participation_post(self, data: dict[str, str]) -> dict | None:
        http_status, body = await self._post(const.PARTICIPATION_URL, data)
        if http_status != 200:
            snippet = " ".join(body.split())[:200]
            raise SpielerplusError(
                f"participation returned HTTP {http_status}: {snippet}"
            )
        return self._decode_json(body)
