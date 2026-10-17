"""A minimal fake aiohttp session for offline client tests.

aioresponses is not compatible with the installed aiohttp on Python 3.14, so
this stands in for ``aiohttp.ClientSession``: it records every request and
returns canned responses. It is deliberately dumb — it only implements what
``SpielerplusClient`` uses (``.get``/``.post`` returning an async context
manager with ``.status``/``.text()``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

RouteValue = tuple[int, str] | Callable[[dict[str, Any]], tuple[int, str]]


class FakeResponse:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body

    async def text(self) -> str:
        # Yield so awaiting it is a real suspension point: without one, two
        # tasks gathered together would never interleave and a test of the
        # client's lock would pass even with the lock removed.
        await asyncio.sleep(0)
        return self._body

    async def __aenter__(self) -> "FakeResponse":
        await asyncio.sleep(0)
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class FakeSession:
    """Routes ``(METHOD, url)`` to canned responses and records requests."""

    def __init__(self, routes: dict[tuple[str, str], RouteValue]) -> None:
        self._routes = routes
        self.requests: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._make("GET", url, kwargs)

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._make("POST", url, kwargs)

    def _make(self, method: str, url: str, kwargs: dict[str, Any]) -> FakeResponse:
        request = {
            "method": method,
            "url": url,
            "params": kwargs.get("params"),
            "data": kwargs.get("data"),
            "headers": kwargs.get("headers"),
        }
        self.requests.append(request)
        route = self._routes.get((method, url))
        if route is None:
            raise AssertionError(f"unexpected request: {method} {url}")
        status, body = route(request) if callable(route) else route
        return FakeResponse(status, body)
