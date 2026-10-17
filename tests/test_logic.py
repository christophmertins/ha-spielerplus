from datetime import date, datetime, time


def _ev(models, eid, t="training", d=19, m=10, st=time(18, 30)):
    return models.SpEvent(
        id=eid,
        type=t,
        title="Training",
        day=d,
        month=m,
        start_time=st,
        end_time=time(20, 30),
        meeting_time=None,
        location=None,
        participation=models.Participation.OFFEN,
        deadline_passed=False,
        url=None,
    )


def test_resolve_year_rolls_over_new_year(logic):
    assert logic.resolve_year(5, 1, date(2026, 12, 20)) == 2027


def test_resolve_year_keeps_current_year_for_near_past(logic):
    assert logic.resolve_year(17, 10, date(2026, 10, 18)) == 2026


def test_resolve_event_builds_start_end_meeting(logic, models):
    r = logic.resolve_event(_ev(models, "1"), date(2026, 10, 18))
    assert r.start == datetime(2026, 10, 19, 18, 30)
    assert r.end == datetime(2026, 10, 19, 20, 30)
    assert r.meeting is None


def test_resolve_event_attaches_timezone(logic, models):
    from datetime import timezone

    r = logic.resolve_event(_ev(models, "1"), date(2026, 10, 18), tz=timezone.utc)
    assert r.start.tzinfo is timezone.utc
    assert r.end.tzinfo is timezone.utc


def test_next_event_filters_type_and_time(logic, models):
    events = logic.resolve_events(
        [_ev(models, "a"), _ev(models, "b", t="game", st=time(14, 0))],
        date(2026, 10, 18),
    )
    now = datetime(2026, 10, 18, 8, 0)
    assert logic.next_event(events, now).event.id == "b"
    assert logic.next_event(events, now, type_="training").event.id == "a"


def test_upcoming_excludes_past(logic, models):
    events = logic.resolve_events([_ev(models, "a", d=1)], date(2026, 10, 18))
    assert logic.upcoming(events, datetime(2026, 10, 18, 8, 0)) == []


def test_upcoming_keeps_a_running_event(logic, models):
    events = logic.resolve_events([_ev(models, "a")], date(2026, 10, 18))
    # Event runs 19.10.2026 18:30-20:30; at 19:00 it is still running.
    assert logic.upcoming(events, datetime(2026, 10, 19, 19, 0)) != []


def test_upcoming_excludes_finished_events(logic, models):
    events = logic.resolve_events([_ev(models, "a")], date(2026, 10, 18))
    assert logic.upcoming(events, datetime(2026, 10, 19, 21, 0)) == []


def test_describe_event_with_meeting_location_and_deadline(logic, models):
    event = models.SpEvent(
        id="a",
        type="training",
        title="Training",
        day=19,
        month=10,
        start_time=time(18, 30),
        end_time=time(20, 30),
        meeting_time=time(18, 0),
        location="Halle",
        participation=models.Participation.OFFEN,
        deadline_passed=True,
        url=None,
    )
    resolved = logic.resolve_event(event, date(2026, 10, 18))
    assert logic.describe_event(resolved) == (
        "Training, Mo. 19.10.2026, 18:30-20:30, "
        "Treffen 18:00, Halle, Zu-/Absage abgelaufen"
    )


def test_sensor_state_summary(logic, models):
    state, attrs = logic.sensor_state(
        logic.resolve_event(_ev(models, "a"), date(2026, 10, 18)), []
    )
    assert attrs["summary"].startswith("Training, Mo. 19.10.2026, 18:30-20:30")


def test_member_options(logic, models):
    assert logic.member_options(
        [models.SpMember(id="101", name="Kind Eins", team="Team A")]
    ) == {"101": "Kind Eins (Team A)"}


def test_sensor_state_attributes_and_none(logic, models):
    assert logic.sensor_state(None, []) == (None, {})
    state, attrs = logic.sensor_state(
        logic.resolve_event(_ev(models, "a"), date(2026, 10, 18)), []
    )
    assert state == datetime(2026, 10, 19, 18, 30)
    assert attrs["event_id"] == "a" and attrs["participation"] == "offen"
