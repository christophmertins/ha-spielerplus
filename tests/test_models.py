from datetime import time


def test_participation_values(const, models):
    assert const.PARTICIPATION_VALUES == {
        models.Participation.ZUSAGE: "1",
        models.Participation.UNSICHER: "2",
        models.Participation.ABSAGE: "0",
    }


def test_member_label(models):
    assert (
        models.SpMember(id="101", name="Kind Eins", team="Team A").label
        == "Kind Eins (Team A)"
    )


def test_event_default_participation_is_offen(models):
    event = models.SpEvent(
        id="111",
        type="training",
        title="Training",
        day=19,
        month=10,
        start_time=time(18, 30),
        end_time=time(20, 30),
        meeting_time=time(18, 0),
        location=None,
        participation=models.Participation.OFFEN,
        deadline_passed=False,
        url="/training/view?id=111",
    )
    assert event.participation is models.Participation.OFFEN
    assert event.type == "training"
