from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "select_team.html"


def test_parse_members_deduplicates_desktop_and_mobile(models, parser):
    members = parser.parse_members(FIX.read_text())
    assert members == [
        models.SpMember(id="101", name="Kind Eins", team="Team A"),
        models.SpMember(id="202", name="Kind Zwei", team="Team B"),
    ]


def test_parse_members_on_garbage_returns_empty(parser):
    assert parser.parse_members("<html><body>nope</body></html>") == []
