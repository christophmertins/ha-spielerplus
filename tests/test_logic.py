from datetime import date, datetime, time

from custom_components.spielerplus import logic
from custom_components.spielerplus.models import Participation, SpEvent


def ev(eid, t="training", d=19, m=10, st=time(18, 30)):
    return SpEvent(
        id=eid,
        type=t,
        title="Training",
        day=d,
        month=m,
        start_time=st,
        end_time=time(20, 30),
        meeting_time=None,
        location=None,
        participation=Participation.OFFEN,
        deadline_passed=False,
        url=None,
    )


def test_resolve_year_rolls_over_new_year():
    assert logic.resolve_year(5, 1, date(2026, 12, 20)) == 2027


def test_resolve_year_keeps_current_year_for_near_past():
    assert logic.resolve_year(17, 10, date(2026, 10, 18)) == 2026


def test_resolve_event_builds_start_end_meeting():
    r = logic.resolve_event(ev("1"), date(2026, 10, 18))
    assert r.start == datetime(2026, 10, 19, 18, 30)
    assert r.end == datetime(2026, 10, 19, 20, 30)
    assert r.meeting is None


def test_next_event_filters_type_and_time():
    events = logic.resolve_events(
        [ev("a"), ev("b", t="game", st=time(14, 0))], date(2026, 10, 18)
    )
    now = datetime(2026, 10, 18, 8, 0)
    assert logic.next_event(events, now).event.id == "b"
    assert logic.next_event(events, now, type_="training").event.id == "a"


def test_upcoming_excludes_past():
    events = logic.resolve_events([ev("a", d=1)], date(2026, 10, 18))
    assert logic.upcoming(events, datetime(2026, 10, 18, 8, 0)) == []


def test_sensor_state_attributes_and_none():
    assert logic.sensor_state(None, []) == (None, {})
    state, attrs = logic.sensor_state(
        logic.resolve_event(ev("a"), date(2026, 10, 18)), []
    )
    assert state == datetime(2026, 10, 19, 18, 30)
    assert attrs["event_id"] == "a" and attrs["participation"] == "offen"
