"""Constants for the SpielerPlus integration."""

from __future__ import annotations

from datetime import timedelta

from .models import Participation

DOMAIN = "spielerplus"

BASE_URL = "https://www.spielerplus.de"
LOGIN_URL = f"{BASE_URL}/site/login"
SELECT_TEAM_URL = f"{BASE_URL}/site/select-team"
SWITCH_USER_URL = f"{BASE_URL}/site/switch-user"
EVENTS_URL = f"{BASE_URL}/events"
AJAX_EVENTS_URL = f"{BASE_URL}/events/ajaxgetevents"
PARTICIPATION_URL = f"{BASE_URL}/events/ajax-participation-form"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=15)

CONF_MEMBERS = "members"
CONF_SCAN_INTERVAL = "scan_interval"

#: Value sent as ``Participation[participation]`` for each state.
PARTICIPATION_VALUES: dict[Participation, str] = {
    Participation.ZUSAGE: "1",
    Participation.UNSICHER: "2",
    Participation.ABSAGE: "0",
}
