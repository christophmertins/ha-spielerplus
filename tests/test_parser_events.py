from datetime import time
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "events.html"


@pytest.fixture
def events(parser):
    return parser.parse_events(FIX.read_text())


def test_parses_all_panels(events):
    assert [e.id for e in events] == ["111", "222", "333"]
    assert [e.type for e in events] == ["training", "training", "game"]


def test_training_details(events, models):
    e = events[0]
    assert (e.title, e.day, e.month) == ("Training", 19, 10)
    assert (e.meeting_time, e.start_time, e.end_time) == (
        time(18, 0),
        time(18, 30),
        time(20, 30),
    )
    assert e.participation is models.Participation.ZUSAGE
    assert e.deadline_passed is False
    assert e.url == "/training/view?id=111"


def test_no_selection_is_offen(events, models):
    assert events[1].participation is models.Participation.OFFEN
    assert events[1].meeting_time is None


def test_deadline_passed_and_disabled(events):
    assert events[2].deadline_passed is True


def test_garbage_returns_empty(parser):
    assert parser.parse_events("<div class='panel' id='event-training-1'>") == []
