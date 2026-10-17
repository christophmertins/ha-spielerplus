import pytest

from custom_components.spielerplus import const
from custom_components.spielerplus.api import SpielerplusAuthError, SpielerplusClient
from custom_components.spielerplus.models import SpMember
from tests.fake_session import FakeSession

LOGIN_PAGE = '<html><head><meta name="csrf-token" content="TOK"></head></html>'
TEAM_PAGE = (
    "<html><title>Team auswählen</title>"
    '<div class="select-team-item"><a href="/site/switch-user?id=101"></a>'
    '<h4 class="dark">Team A</h4><small>Kind Eins</small></div></html>'
)


async def test_login_sends_csrf_and_fetches_members():
    session = FakeSession(
        {
            ("GET", const.LOGIN_URL): (200, LOGIN_PAGE),
            ("POST", const.LOGIN_URL): (200, "<html><title>Team auswählen</title></html>"),
            ("GET", const.SELECT_TEAM_URL): (200, TEAM_PAGE),
            ("GET", const.SWITCH_USER_URL): (200, "<html></html>"),
        }
    )
    client = SpielerplusClient(session, "a@b.c", "secret")

    await client.async_login()
    assert await client.async_get_members() == [
        SpMember(id="101", name="Kind Eins", team="Team A")
    ]
    await client.async_select_member("101")

    login_post = next(r for r in session.requests if r["method"] == "POST")
    assert login_post["data"] == {
        "_csrf": "TOK",
        "LoginForm[email]": "a@b.c",
        "LoginForm[password]": "secret",
    }
    switch = next(r for r in session.requests if r["url"] == const.SWITCH_USER_URL)
    assert switch["params"] == {"id": "101"}


async def test_login_failure_raises_auth_error():
    session = FakeSession(
        {
            ("GET", const.LOGIN_URL): (200, LOGIN_PAGE),
            ("POST", const.LOGIN_URL): (200, "<html><title>Einloggen</title></html>"),
        }
    )
    with pytest.raises(SpielerplusAuthError):
        await SpielerplusClient(session, "a@b.c", "bad").async_login()
