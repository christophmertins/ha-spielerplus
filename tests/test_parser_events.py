from datetime import time
from pathlib import Path

import pytest

from custom_components.spielerplus.models import Participation
from custom_components.spielerplus.parser import parse_events


@pytest.fixture
def events():
    return parse_events((Path(__file__).parent / "fixtures" / "events.html").read_text())


def test_parses_all_panels(events):
    assert [e.id for e in events] == ["111", "222", "333"]
    assert [e.type for e in events] == ["training", "training", "game"]


def test_training_details(events):
    e = events[0]
    assert (e.title, e.day, e.month) == ("Training", 19, 10)
    assert (e.meeting_time, e.start_time, e.end_time) == (
        time(18, 0),
        time(18, 30),
        time(20, 30),
    )
    assert e.participation is Participation.ZUSAGE
    assert e.deadline_passed is False
    assert e.url == "/training/view?id=111"


def test_no_selection_is_offen(events):
    assert events[1].participation is Participation.OFFEN
    assert events[1].meeting_time is None


def test_deadline_passed_and_disabled(events):
    assert events[2].deadline_passed is True


def test_garbage_returns_empty():
    assert parse_events("<div class='panel' id='event-training-1'>") == []
