from pathlib import Path

from custom_components.spielerplus.models import SpMember
from custom_components.spielerplus.parser import parse_members

FIX = Path(__file__).parent / "fixtures" / "select_team.html"


def test_parse_members_deduplicates_desktop_and_mobile():
    members = parse_members(FIX.read_text())
    assert members == [
        SpMember(id="101", name="Kind Eins", team="Team A"),
        SpMember(id="202", name="Kind Zwei", team="Team B"),
    ]


def test_parse_members_on_garbage_returns_empty():
    assert parse_members("<html><body>nope</body></html>") == []
