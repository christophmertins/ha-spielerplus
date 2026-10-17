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


def test_parses_weekday(events):
    assert [e.weekday for e in events] == [0, 1, 5]


def test_unknown_weekday_label_is_none(parser):
    html = (
        '<div class="list event"><div class="panel" id="event-training-9">'
        '<div class="panel-heading-info"><div class="panel-title">Xyz</div>'
        '<div class="panel-subtitle">19.10</div></div>'
        '<div class="panel-heading-text"><div class="panel-title">Training</div></div>'
        "</div></div>"
    )
    assert parser.parse_events(html)[0].weekday is None


def test_garbage_returns_empty(parser):
    assert parser.parse_events("<div class='panel' id='event-training-1'>") == []


def test_live_countdown_does_not_mean_deadline_passed(parser):
    html = (
        '<div class="list event"><div class="panel" id="event-training-9">'
        '<div class="panel-heading-info"><div class="panel-title">Mo.</div>'
        '<div class="panel-subtitle">19.10</div></div>'
        '<div class="panel-heading-text"><div class="panel-title">Training</div></div>'
        '<div class="panel-content"><div class="list-item countdown">'
        "<span>Noch 3 Std.</span></div></div>"
        '<div class="participation-widget-buttons">'
        '<button class="participation-button" title="Zugesagt"></button>'
        "</div></div></div>"
    )
    assert parser.parse_events(html)[0].deadline_passed is False


def test_count_event_panels(parser):
    two = (
        '<div class="panel" id="event-training-1"></div>'
        '<div class="panel" id="event-game-2"></div>'
    )
    assert parser.count_event_panels(two) == 2
    assert parser.count_event_panels("<html><body>leer</body></html>") == 0
