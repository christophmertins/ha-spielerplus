import json
from pathlib import Path

import pytest

from tests.fake_session import FakeSession

EVENTS_FIXTURE = Path(__file__).parent / "fixtures" / "events.html"


def _panel(event_id: str) -> str:
    return (
        f'<div class="panel" id="event-training-{event_id}">'
        '<div class="panel-heading-info"><div class="panel-title">Mo.</div>'
        '<div class="panel-subtitle">19.10</div></div>'
        '<div class="panel-heading-text"><div class="panel-title">Training</div></div>'
        "</div>"
    )


async def test_get_events_merges_pagination_and_deduplicates(api, const):
    fragment = f'<div class="list event">{_panel("444")}{_panel("111")}</div>'

    def ajax(request):
        if request["data"]["offset"] == "5":
            return 200, json.dumps({"html": fragment, "count": 3})
        return 200, json.dumps({"html": "", "count": -1})

    session = FakeSession(
        {
            ("GET", const.EVENTS_URL): (200, EVENTS_FIXTURE.read_text()),
            ("POST", const.AJAX_EVENTS_URL): ajax,
        }
    )
    events = await api.SpielerplusClient(session, "a", "b").async_get_events()

    assert [e.id for e in events] == ["111", "222", "333", "444"]


async def test_get_events_requires_login(api, const):
    session = FakeSession(
        {("GET", const.EVENTS_URL): (200, "<html><title>Einloggen</title></html>")}
    )
    with pytest.raises(api.SpielerplusAuthError):
        await api.SpielerplusClient(session, "a", "b").async_get_events()


async def test_get_events_raises_when_panels_present_but_unparsed(api, const):
    html = (
        '<div class="list event">'
        '<div class="panel" id="event-training-1">structure changed</div></div>'
    )
    session = FakeSession(
        {
            ("GET", const.EVENTS_URL): (200, html),
            ("POST", const.AJAX_EVENTS_URL): (
                200,
                json.dumps({"html": "", "count": -1}),
            ),
        }
    )
    with pytest.raises(api.SpielerplusError):
        await api.SpielerplusClient(session, "a", "b").async_get_events()


async def test_set_participation_sends_expected_fields(api, const, models):
    session = FakeSession({("POST", const.PARTICIPATION_URL): (200, "{}")})
    client = api.SpielerplusClient(session, "a", "b")

    await client.async_set_participation(
        member_id="101",
        event_type="training",
        event_id="111",
        status=models.Participation.ABSAGE,
        reason="krank",
    )

    assert session.requests[0]["data"] == {
        "Participation[type]": "training",
        "Participation[typeid]": "111",
        "Participation[participation]": "0",
        "Participation[user_id]": "101",
        "Participation[reason]": "krank",
    }
