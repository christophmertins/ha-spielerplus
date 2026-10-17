from datetime import time

from custom_components.spielerplus.const import PARTICIPATION_VALUES
from custom_components.spielerplus.models import Participation, SpEvent, SpMember


def test_participation_values():
    assert PARTICIPATION_VALUES == {
        Participation.ZUSAGE: "1",
        Participation.UNSICHER: "2",
        Participation.ABSAGE: "0",
    }


def test_member_label():
    assert SpMember(id="101", name="Kind Eins", team="Team A").label == "Kind Eins (Team A)"


def test_event_default_participation_is_offen():
    e = SpEvent(
        id="111",
        type="training",
        title="Training",
        day=19,
        month=10,
        start_time=time(18, 30),
        end_time=time(20, 30),
        meeting_time=time(18, 0),
        location=None,
        participation=Participation.OFFEN,
        deadline_passed=False,
        url="/training/view?id=111",
    )
    assert e.participation is Participation.OFFEN and e.type == "training"
