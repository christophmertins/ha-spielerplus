import asyncio
import json
from pathlib import Path

import pytest

from tests.fake_session import FakeSession

EVENTS_FIXTURE = Path(__file__).parent / "fixtures" / "events.html"
EVENTS_PAGE = (
    "<html><head><title>Termine</title></head><body>"
    f"{EVENTS_FIXTURE.read_text()}</body></html>"
)
LOGIN_PAGE = '<html><head><meta name="csrf-token" content="TOK"></head></html>'
TEAM_PAGE = "<html><title>Team auswählen</title></html>"
LOGIN_REJECTED = "<html><title>Einloggen</title></html>"


def _panel(event_id: str) -> str:
    return (
        f'<div class="panel" id="event-training-{event_id}">'
        '<div class="panel-heading-info"><div class="panel-title">Mo.</div>'
        '<div class="panel-subtitle">19.10</div></div>'
        '<div class="panel-heading-text"><div class="panel-title">Training</div></div>'
        "</div>"
    )


def _page(body: str, title: str = "Termine") -> str:
    return f"<html><head><title>{title}</title></head><body>{body}</body></html>"


def _routes(const, events_body, login_post: str = TEAM_PAGE, ajax=None):
    return {
        ("GET", const.LOGIN_URL): (200, LOGIN_PAGE),
        ("POST", const.LOGIN_URL): (200, login_post),
        ("GET", const.EVENTS_URL): (200, events_body),
        ("POST", const.AJAX_EVENTS_URL): ajax
        or (200, json.dumps({"html": "", "count": -1})),
    }


async def test_get_events_merges_pagination_and_deduplicates(api, const):
    fragment = f'<div class="list event">{_panel("444")}{_panel("111")}</div>'

    def ajax(request):
        if request["data"]["offset"] == "5":
            return 200, json.dumps({"html": fragment, "count": 3})
        return 200, json.dumps({"html": "", "count": -1})

    session = FakeSession(_routes(const, EVENTS_PAGE, ajax=ajax))
    events = await api.SpielerplusClient(session, "a", "b").async_get_events()

    assert [e.id for e in events] == ["111", "222", "333", "444"]


async def test_get_events_raises_when_panels_present_but_unparsed(api, const):
    broken = _page(
        '<div class="list event">'
        '<div class="panel" id="event-training-1">structure changed</div></div>'
    )
    session = FakeSession(_routes(const, broken))
    with pytest.raises(api.SpielerplusError):
        await api.SpielerplusClient(session, "a", "b").async_get_events()


async def test_get_events_raises_on_an_unexpected_page(api, const):
    session = FakeSession(_routes(const, _page("<div>nope</div>", title="Fehler")))
    with pytest.raises(api.SpielerplusError):
        await api.SpielerplusClient(session, "a", "b").async_get_events()


async def test_get_events_relogins_once_when_the_session_expired(api, const):
    calls = {"n": 0}

    def events_route(request):
        calls["n"] += 1
        return (200, LOGIN_REJECTED) if calls["n"] == 1 else (200, EVENTS_PAGE)

    routes = _routes(const, EVENTS_PAGE)
    routes[("GET", const.EVENTS_URL)] = events_route
    session = FakeSession(routes)

    events = await api.SpielerplusClient(session, "a", "b").async_get_events()

    assert [e.id for e in events] == ["111", "222", "333"]
    assert any(
        r["method"] == "POST" and r["url"] == const.LOGIN_URL
        for r in session.requests
    )


async def test_get_events_raises_when_relogin_also_fails(api, const):
    session = FakeSession(_routes(const, LOGIN_REJECTED, login_post=LOGIN_REJECTED))
    with pytest.raises(api.SpielerplusAuthError):
        await api.SpielerplusClient(session, "a", "b").async_get_events()


async def test_switch_user_retries_after_an_expired_session(api, const):
    calls = {"n": 0}

    def switch(request):
        calls["n"] += 1
        return (200, LOGIN_REJECTED) if calls["n"] == 1 else (200, "<html></html>")

    session = FakeSession(
        {
            ("GET", const.LOGIN_URL): (200, LOGIN_PAGE),
            ("POST", const.LOGIN_URL): (200, TEAM_PAGE),
            ("GET", const.SWITCH_USER_URL): switch,
        }
    )
    await api.SpielerplusClient(session, "a", "b").async_select_member("101")

    assert calls["n"] == 2
    assert any(
        r["method"] == "POST" and r["url"] == const.LOGIN_URL
        for r in session.requests
    )


async def test_switch_user_raises_when_relogin_also_fails(api, const):
    session = FakeSession(
        {
            ("GET", const.LOGIN_URL): (200, LOGIN_PAGE),
            ("POST", const.LOGIN_URL): (200, TEAM_PAGE),
            ("GET", const.SWITCH_USER_URL): (200, LOGIN_REJECTED),
        }
    )
    with pytest.raises(api.SpielerplusAuthError):
        await api.SpielerplusClient(session, "a", "b").async_select_member("101")


async def test_get_member_events_reselects_the_member_after_relogin(api, const):
    events_calls = {"n": 0}

    def events_route(request):
        events_calls["n"] += 1
        return (200, LOGIN_REJECTED) if events_calls["n"] == 1 else (200, EVENTS_PAGE)

    routes = _routes(const, EVENTS_PAGE)
    routes[("GET", const.EVENTS_URL)] = events_route
    routes[("GET", const.SWITCH_USER_URL)] = (200, "<html></html>")
    session = FakeSession(routes)

    events = await api.SpielerplusClient(session, "a", "b").async_get_member_events("101")

    assert [e.id for e in events] == ["111", "222", "333"]
    second_events = max(
        i for i, r in enumerate(session.requests) if r["url"] == const.EVENTS_URL
    )
    previous = session.requests[second_events - 1]
    assert previous["url"] == const.SWITCH_USER_URL
    assert previous["params"] == {"id": "101"}


async def test_member_switch_and_fetch_are_not_interleaved_by_a_write(api, const):
    routes = _routes(const, EVENTS_PAGE)
    routes[("GET", const.SWITCH_USER_URL)] = (200, "<html></html>")
    routes[("POST", const.PARTICIPATION_URL)] = (200, "{}")
    session = FakeSession(routes)
    client = api.SpielerplusClient(session, "a", "b")

    await asyncio.gather(
        client.async_get_member_events("101"),
        client.async_set_participation(
            "202", "training", "111", api.Participation.ZUSAGE
        ),
    )

    requests = session.requests
    read_switch = next(
        i
        for i, r in enumerate(requests)
        if r["url"] == const.SWITCH_USER_URL and r["params"] == {"id": "101"}
    )
    assert requests[read_switch + 1]["url"] == const.EVENTS_URL
    write_switch = next(
        i
        for i, r in enumerate(requests)
        if r["url"] == const.SWITCH_USER_URL and r["params"] == {"id": "202"}
    )
    assert requests[write_switch + 1]["url"] == const.PARTICIPATION_URL


def _participation_session(const, body: str = "{}") -> FakeSession:
    return FakeSession(
        {
            ("GET", const.SWITCH_USER_URL): (200, "<html></html>"),
            ("POST", const.PARTICIPATION_URL): (200, body),
        }
    )


def _participation_post(session):
    return next(r for r in session.requests if r["method"] == "POST")


async def test_set_participation_switches_to_the_target_member_first(api, const):
    session = _participation_session(const)
    await api.SpielerplusClient(session, "a", "b").async_set_participation(
        member_id="101", event_type="training", event_id="111",
        status=api.Participation.ZUSAGE,
    )
    switch = session.requests[0]
    assert switch["method"] == "GET"
    assert switch["url"] == const.SWITCH_USER_URL
    assert switch["params"] == {"id": "101"}
    assert session.requests[1]["method"] == "POST"


async def test_set_participation_relogins_on_an_html_answer(api, const):
    calls = {"n": 0}

    def participation(request):
        calls["n"] += 1
        return (200, LOGIN_REJECTED) if calls["n"] == 1 else (200, "{}")

    session = FakeSession(
        {
            ("GET", const.LOGIN_URL): (200, LOGIN_PAGE),
            ("POST", const.LOGIN_URL): (200, TEAM_PAGE),
            ("GET", const.SWITCH_USER_URL): (200, "<html></html>"),
            ("POST", const.PARTICIPATION_URL): participation,
        }
    )
    await api.SpielerplusClient(session, "a", "b").async_set_participation(
        member_id="101", event_type="training", event_id="111",
        status=api.Participation.ZUSAGE,
    )
    assert calls["n"] == 2


async def test_set_participation_reselects_the_member_after_relogin(api, const):
    calls = {"n": 0}

    def participation(request):
        calls["n"] += 1
        return (200, LOGIN_REJECTED) if calls["n"] == 1 else (200, "{}")

    session = FakeSession(
        {
            ("GET", const.LOGIN_URL): (200, LOGIN_PAGE),
            ("POST", const.LOGIN_URL): (200, TEAM_PAGE),
            ("GET", const.SWITCH_USER_URL): (200, "<html></html>"),
            ("POST", const.PARTICIPATION_URL): participation,
        }
    )
    await api.SpielerplusClient(session, "a", "b").async_set_participation(
        member_id="101", event_type="training", event_id="111",
        status=api.Participation.ZUSAGE,
    )

    assert calls["n"] == 2
    posts = [
        i
        for i, r in enumerate(session.requests)
        if r["url"] == const.PARTICIPATION_URL
    ]
    previous = session.requests[posts[1] - 1]
    assert previous["url"] == const.SWITCH_USER_URL
    assert previous["params"] == {"id": "101"}


async def test_set_participation_raises_when_api_reports_error(api, const):
    session = _participation_session(const, '{"error":true,"html":"form"}')
    client = api.SpielerplusClient(session, "a", "b")
    with pytest.raises(api.SpielerplusError):
        await client.async_set_participation(
            member_id="101", event_type="training", event_id="111",
            status=api.Participation.ABSAGE, reason="krank",
        )


async def test_set_participation_defaults_reason_for_absage(api, const):
    session = _participation_session(const)
    await api.SpielerplusClient(session, "a", "b").async_set_participation(
        member_id="101", event_type="training", event_id="111",
        status=api.Participation.ABSAGE,
    )
    assert _participation_post(session)["data"]["Participation[reason]"] == "Home Assistant"


async def test_set_participation_keeps_empty_reason_for_zusage(api, const):
    session = _participation_session(const)
    await api.SpielerplusClient(session, "a", "b").async_set_participation(
        member_id="101", event_type="training", event_id="111",
        status=api.Participation.ZUSAGE,
    )
    assert _participation_post(session)["data"]["Participation[reason]"] == ""


async def test_set_participation_sends_expected_fields(api, const, models):
    session = _participation_session(const)
    client = api.SpielerplusClient(session, "a", "b")

    await client.async_set_participation(
        member_id="101",
        event_type="training",
        event_id="111",
        status=models.Participation.ABSAGE,
        reason="krank",
    )

    assert _participation_post(session)["data"] == {
        "Participation[type]": "training",
        "Participation[typeid]": "111",
        "Participation[participation]": "0",
        "Participation[user_id]": "101",
        "Participation[reason]": "krank",
    }
