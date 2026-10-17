"""HTTP client for the SpielerPlus web application.

This is the only module that talks to the network. It wraps an ``aiohttp``
session and speaks the same requests the website's own JavaScript uses.
"""

from __future__ import annotations

import asyncio
import re

import aiohttp

from . import const
from .models import SpMember
from .parser import parse_members

_META_CSRF_RE = re.compile(r'<meta[^>]+name="csrf-token"[^>]+content="([^"]+)"')
_INPUT_CSRF_RE = re.compile(r'<input[^>]+name="_csrf"[^>]+value="([^"]+)"')
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

_LOGIN_TITLES = {"Einloggen", "Login"}


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
            async with self._session.get(url, **kwargs) as response:
                return response.status, await response.text()
        except aiohttp.ClientError as err:
            raise SpielerplusError(f"GET {url} failed: {err}") from err
        except TimeoutError as err:
            raise SpielerplusError(f"GET {url} timed out") from err

    async def _post(self, url: str, data: dict[str, str]) -> tuple[int, str]:
        try:
            async with self._session.post(url, data=data) as response:
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
