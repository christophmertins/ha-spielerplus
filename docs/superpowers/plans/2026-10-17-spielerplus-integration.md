# SpielerPlus Home-Assistant Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A HACS-ready Home Assistant custom integration `spielerplus` that shows the upcoming SpielerPlus events (trainings/games) of each configured member as a calendar plus sensors, and lets the user confirm/decline attendance from HA via buttons and a service.

**Architecture:** A thin aiohttp client (`api.py`) talks to the SpielerPlus Yii2 web app using a session cookie (login + `switch-user` per member). Pure functions parse the returned HTML into dataclasses (`parser.py`) and derive dates/selections/view-models (`logic.py`). A `DataUpdateCoordinator` polls each member; `calendar`, `sensor` and `button` platforms are thin entity wrappers over the coordinator; a service provides arbitrary participation changes.

**Tech Stack:** Python 3.13, Home Assistant 2026.10 (custom integration API), `aiohttp`, `beautifulsoup4==4.12.3`, `pytest` + `pytest-asyncio` + `aioresponses`.

**Spec:** `docs/superpowers/specs/2026-10-17-spielerplus-integration-design.md`

## Global Constraints

- Domain: `spielerplus`. Manifest: `config_flow: true`, `integration_type: hub`, `iot_class: cloud_polling`, `version: 0.1.0`, `requirements: ["beautifulsoup4==4.12.3"]`, `codeowners: ["@christophmertins"]`.
- Base URL `https://www.spielerplus.de`. Endpoints exactly as in spec §3.
- Participation values: `zusage` → `"1"`, `unsicher` → `"2"`, `absage` → `"0"`.
- Default poll interval: 15 minutes; options-flow choices 5/10/15/30/60 minutes.
- Entity id pattern: device `SpielerPlus <Mitglied>`, entities `calendar.spielerplus_<mitglied>`, `sensor.spielerplus_<mitglied>_naechstes_training`, `sensor.spielerplus_<mitglied>_naechster_termin`, `button.spielerplus_<mitglied>_zusagen`, `button.spielerplus_<mitglied>_absagen`.
- Service name: `spielerplus.set_participation` (platform domain `spielerplus`).
- **Never** commit credentials, real member names/IDs, or real event data. Fixtures and tests use placeholders only.
- All HA-dependent modules (`coordinator.py`, `calendar.py`, `sensor.py`, `button.py`, `services.py`, `config_flow.py`, `__init__.py`) import `homeassistant`; they are verified with `python -m py_compile` plus live verification at deployment (repo convention, see `ha-ngs-amm-portal`). Pure modules (`models.py`, `const.py`, `parser.py`, `logic.py`, `api.py`) are unit-tested and must stay importable without Home Assistant installed.

## Review Focus

Failure modes the spec implies but no unit test can reach; each is pinned to a task below.

1. **SpielerPlus HTML changes** (panel id, `.participation-widget`, `.select-team-item`, login CSRF) → parser returns empty/short results. Owning task: 3 (parser) + 7 (coordinator must raise `UpdateFailed`, not silently show nothing).
2. **Year boundary** — an event listed as `05.01` while today is December must resolve to the next year, and an event listed a day in the past must not become next year. Owning task: 4.
3. **Zu-/Absage deadline passed** — buttons are `disabled` and the panel shows a countdown; the button must be `unavailable` and the service must raise a clear error instead of pretending success. Owning task: 4 + 10 + 11.
4. **Session expiry mid-operation** — `/events` returns the login page (`<title>Einloggen</title>`) instead of events; must trigger reauth, not an unavailable loop. Owning task: 5 + 7.
5. **Concurrent `switch-user`** — an overlapping poll and a button press must not read/act on the wrong member; the client serializes all requests with one lock. Owning task: 5 + 6 + 7.

---

### Task 1: Scaffolding, models, constants

**Files:**
- Create: `custom_components/spielerplus/__init__.py` (empty for now), `custom_components/spielerplus/manifest.json`, `custom_components/spielerplus/const.py`, `custom_components/spielerplus/models.py`
- Create: `hacs.json`, `pytest.ini`, `requirements_test.txt`, `tests/__init__.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `const.DOMAIN: str`, `const.BASE_URL`, `const.LOGIN_URL`, `const.SELECT_TEAM_URL`, `const.SWITCH_USER_URL`, `const.EVENTS_URL`, `const.AJAX_EVENTS_URL`, `const.PARTICIPATION_URL`, `const.DEFAULT_SCAN_INTERVAL: timedelta`, `const.CONF_MEMBERS = "members"`, `const.CONF_SCAN_INTERVAL = "scan_interval"`, `const.PARTICIPATION_VALUES: dict[Participation, str]`
  - `models.Participation(StrEnum)` with members `ZUSAGE="zusage"`, `UNSICHER="unsicher"`, `ABSAGE="absage"`, `OFFEN="offen"`
  - `models.SpMember` frozen dataclass `(id: str, name: str, team: str)` → `label` property `f"{name} ({team})"`
  - `models.SpEvent` frozen dataclass `(id: str, type: str, title: str, day: int, month: int, start_time: time | None, end_time: time | None, meeting_time: time | None, location: str | None, participation: Participation, deadline_passed: bool, url: str | None)`
  - `models.ResolvedEvent` frozen dataclass `(event: SpEvent, start: datetime, end: datetime, meeting: datetime | None)`

- [ ] **Step 1: Write the failing test** — `tests/test_models.py`

```python
from datetime import time
from custom_components.spielerplus.const import PARTICIPATION_VALUES
from custom_components.spielerplus.models import Participation, SpEvent, SpMember

def test_participation_values():
    assert PARTICIPATION_VALUES == {
        Participation.ZUSAGE: "1", Participation.UNSICHER: "2", Participation.ABSAGE: "0"
    }

def test_member_label():
    assert SpMember(id="101", name="Kind Eins", team="Team A").label == "Kind Eins (Team A)"

def test_event_default_participation_is_offen():
    e = SpEvent(id="111", type="training", title="Training", day=19, month=10,
                start_time=time(18, 30), end_time=time(20, 30), meeting_time=time(18, 0),
                location=None, participation=Participation.OFFEN, deadline_passed=False,
                url="/training/view?id=111")
    assert e.participation is Participation.OFFEN and e.type == "training"
```

- [ ] **Step 2: Run test to verify it fails** — `python -m pytest tests/test_models.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** `manifest.json`, `const.py`, `models.py` per the Interfaces block. `manifest.json` exact keys from Global Constraints. `hacs.json` = `{"name": "SpielerPlus", "render_readme": true}`. `pytest.ini` = `[pytest]\ntestpaths = tests\nasyncio_mode = auto`. `requirements_test.txt` = `pytest`, `pytest-asyncio`, `aiohttp`, `beautifulsoup4==4.12.3`, `aioresponses`.

- [ ] **Step 4: Run test to verify it passes** — `python -m pytest tests/test_models.py -v` → PASS.

- [ ] **Step 5: Commit** — `git add custom_components hacs.json pytest.ini requirements_test.txt tests && git commit -m "feat: scaffold spielerplus integration (models, constants)"`

---

### Task 2: Parser — member list

**Files:**
- Create: `custom_components/spielerplus/parser.py`, `tests/fixtures/select_team.html`
- Test: `tests/test_parser_members.py`

**Interfaces:**
- Consumes: `models.SpMember`.
- Produces: `parser.parse_members(html: str) -> list[SpMember]` — deduplicated by `id`, order of first appearance.

- [ ] **Step 1: Write the failing test + fixture** — `tests/fixtures/select_team.html` (trimmed from the real page; the desktop layout is `a[href*="switch-user?id="]` followed by `h4.dark` (team) and `small` (name) inside the item; the mobile layout repeats the same under `.list-item` with `.list-label`/`.list-sublabel`):

```html
<div class="select-team-item"><div class="select-team-item-height">
  <a href="/site/switch-user?id=101"><div class="logo"></div></a>
  <div class="select-team-item-meta"><h4 class="dark">Team A</h4><small>Kind Eins</small></div>
</div></div>
<div class="select-team-item"><div class="select-team-item-height">
  <a href="/site/switch-user?id=202"><div class="logo"></div></a>
  <div class="select-team-item-meta"><h4 class="dark">Team B</h4><small>Kind Zwei</small></div>
</div></div>
<div class="select-team visible-xs"><div class="card">
  <div class="list-item"><a class="list-item-link" href="/site/switch-user?id=101"></a>
    <div class="list-body"><div class="list-label-section">
      <div class="list-label">Team A</div><div class="list-sublabel">Kind Eins</div>
    </div></div></div>
</div></div>
```

`tests/test_parser_members.py`:

```python
from pathlib import Path
from custom_components.spielerplus.models import SpMember
from custom_components.spielerplus.parser import parse_members

FIX = Path(__file__).parent / "fixtures" / "select_team.html"

def test_parse_members_deduplicates_desktop_and_mobile():
    members = parse_members(FIX.read_text())
    assert members == [SpMember(id="101", name="Kind Eins", team="Team A"),
                       SpMember(id="202", name="Kind Zwei", team="Team B")]

def test_parse_members_on_garbage_returns_empty():
    assert parse_members("<html><body>nope</body></html>") == []
```

- [ ] **Step 2: Run test to verify it fails** — `python -m pytest tests/test_parser_members.py -v` → FAIL.

- [ ] **Step 3: Implement `parse_members`** in `parser.py` with BeautifulSoup: select `a[href*="switch-user?id="]`, take the id from the query, find the enclosing `.select-team-item` or `.list-item`, read team from `h4.dark`/`.list-label` and name from `small`/`.list-sublabel`; skip entries missing id/name; keep first occurrence per id.

- [ ] **Step 4: Run test to verify it passes** — PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(parser): parse member list from select-team page"`

---

### Task 3: Parser — events

**Files:**
- Create: `tests/fixtures/events.html`
- Modify: `custom_components/spielerplus/parser.py`
- Test: `tests/test_parser_events.py`

**Interfaces:**
- Consumes: `models.SpEvent`, `models.Participation`.
- Produces: `parser.parse_events(html: str) -> list[SpEvent]`.
- Status mapping from the selected button's `title`: `"Zugesagt"`→`ZUSAGE`, `"Unsicher"`→`UNSICHER`, `"Absagen / Abwesend"`→`ABSAGE`, none selected→`OFFEN`. `deadline_passed` = True when the participation buttons carry `disabled` **or** a `.countdown` element exists in the panel.

- [ ] **Step 1: Write the failing test + fixture** — `tests/fixtures/events.html` with three panels: `event-training-111` (Zugesagt), `event-training-222` (nothing selected), `event-game-333` (disabled + countdown), using the verified structure (`.panel-heading-info .panel-title`=weekday, `.panel-subtitle`=dd.mm; `.panel-heading-text .panel-title`=title; `.event-time-item` label/value; `.participation-widget-buttons button.selected`; `a.event-header-border[href]`):

```html
<div class="list event">
<div class="panel" id="event-training-111">
  <div class="panel-heading"><a class="event-header-border" href="/training/view?id=111"></a>
    <div class="panel-heading-info"><div class="panel-title">Mo.</div><div class="panel-subtitle">19.10</div></div>
    <div class="panel-heading-text"><div class="panel-title">Training</div></div></div>
  <div class="panel-content"><div class="event-time">
    <div class="event-time-item"><div class="event-time-label">Treffen</div><div class="event-time-value">18:00</div></div>
    <div class="event-time-item"><div class="event-time-label">Beginn</div><div class="event-time-value">18:30</div></div>
    <div class="event-time-item"><div class="event-time-label">Ende</div><div class="event-time-value">20:30 </div></div>
  </div></div>
  <div class="participation-flex"><div class="participation-widget participation-widget-training-111-101">
    <div class="btn-group participation-widget-buttons">
      <button class="participation-button selected" title="Zugesagt" onClick="showParticipationForm(&quot;training&quot;, 111, 1, 101)"></button>
      <button class="participation-button" title="Unsicher" onClick="showParticipationForm(&quot;training&quot;, 111, 2, 101)"></button>
      <button class="participation-button" title="Absagen / Abwesend" onClick="showParticipationForm(&quot;training&quot;, 111, 0, 101)"></button>
    </div></div></div>
</div>
<div class="panel" id="event-training-222">
  <div class="panel-heading"><a class="event-header-border" href="/training/view?id=222"></a>
    <div class="panel-heading-info"><div class="panel-title">Di.</div><div class="panel-subtitle">20.10</div></div>
    <div class="panel-heading-text"><div class="panel-title">Training</div></div></div>
  <div class="panel-content"><div class="event-time">
    <div class="event-time-item"><div class="event-time-label">Beginn</div><div class="event-time-value">18:00</div></div>
  </div></div>
  <div class="participation-flex"><div class="participation-widget participation-widget-training-222-101">
    <div class="btn-group participation-widget-buttons">
      <button class="participation-button" title="Zugesagt"></button>
      <button class="participation-button" title="Unsicher"></button>
      <button class="participation-button" title="Absagen / Abwesend"></button>
    </div></div></div>
</div>
<div class="panel" id="event-game-333">
  <div class="panel-heading"><a class="event-header-border" href="/game/view?id=333"></a>
    <div class="panel-heading-info"><div class="panel-title">Sa.</div><div class="panel-subtitle">24.10</div></div>
    <div class="panel-heading-text"><div class="panel-title">Spiel</div></div></div>
  <div class="panel-content"><div class="event-time">
    <div class="event-time-item"><div class="event-time-label">Beginn</div><div class="event-time-value">14:00</div></div>
  </div>
  <div class="list-item small countdown red"><span id="sp-event-countdown-333">Zeit zum Zu-/Absagen abgelaufen</span></div></div>
  <div class="participation-flex"><div class="participation-widget participation-widget-game-333-101">
    <div class="btn-group participation-widget-buttons">
      <button class="participation-button" disabled="disabled" title="Zugesagt"></button>
      <button class="participation-button" disabled="disabled" title="Unsicher"></button>
      <button class="participation-button" disabled="disabled" title="Absagen / Abwesend"></button>
    </div></div></div>
</div>
</div>
```

`tests/test_parser_events.py`:

```python
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
    assert (e.meeting_time, e.start_time, e.end_time) == (time(18, 0), time(18, 30), time(20, 30))
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
```

- [ ] **Step 2: Run test to verify it fails** — FAIL.

- [ ] **Step 3: Implement `parse_events`** in `parser.py`: iterate `div.panel[id^="event-"]`, parse `event-<type>-<id>` from the id, read weekday/subtitle, title, times, selected button status, deadline flags and the detail href. Skip panels where id or title cannot be parsed.

- [ ] **Step 4: Run test to verify it passes** — `python -m pytest tests/test_parser_events.py -v` → PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(parser): parse event panels"`

---

### Task 4: Logic — date resolution, selection, view-models

**Files:**
- Create: `custom_components/spielerplus/logic.py`
- Test: `tests/test_logic.py`

**Interfaces:**
- Consumes: `models.SpEvent`, `models.SpMember`, `models.Participation`, `models.ResolvedEvent`, `const.PARTICIPATION_VALUES`.
- Produces:
  - `logic.participation_value(status: Participation) -> str`
  - `logic.resolve_year(day: int, month: int, today: date) -> int`
  - `logic.resolve_event(event: SpEvent, today: date) -> ResolvedEvent` (`start = combine(date, start_time or 00:00)`, `end = combine(date, end_time)` or `start + 1h`, `meeting = combine(date, meeting_time)` or `None`)
  - `logic.resolve_events(events: list[SpEvent], today: date) -> list[ResolvedEvent]` (sorted by `start`)
  - `logic.upcoming(events: list[ResolvedEvent], now: datetime) -> list[ResolvedEvent]` (`start >= now`)
  - `logic.next_event(events: list[ResolvedEvent], now: datetime, type_: str | None = None) -> ResolvedEvent | None`
  - `logic.sensor_state(event: ResolvedEvent | None, upcoming: list[ResolvedEvent]) -> tuple[datetime | None, dict[str, object]]` (attributes: `event_id`, `event_type`, `title`, `start`, `end`, `meeting_time`, `location`, `participation`, `deadline_passed`, `events`)
  - `logic.calendar_range(events: list[ResolvedEvent], start: date, end: date) -> list[ResolvedEvent]`
  - `logic.event_summary(event: SpEvent) -> str` (`"Training"` for training, else `f"{title}"`)

- [ ] **Step 1: Write the failing test** — `tests/test_logic.py`:

```python
from datetime import date, datetime, time
from custom_components.spielerplus.models import Participation, SpEvent
from custom_components.spielerplus import logic

def ev(eid, t="training", d=19, m=10, st=time(18, 30)):
    return SpEvent(id=eid, type=t, title="Training", day=d, month=m, start_time=st,
                   end_time=time(20, 30), meeting_time=None, location=None,
                   participation=Participation.OFFEN, deadline_passed=False, url=None)

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
    events = logic.resolve_events([ev("a"), ev("b", t="game", st=time(14, 0))], date(2026, 10, 18))
    now = datetime(2026, 10, 18, 8, 0)
    assert logic.next_event(events, now).event.id == "b"
    assert logic.next_event(events, now, type_="training").event.id == "a"

def test_upcoming_excludes_past():
    events = logic.resolve_events([ev("a", d=1)], date(2026, 10, 18))
    assert logic.upcoming(events, datetime(2026, 10, 18, 8, 0)) == []

def test_sensor_state_attributes_and_none():
    assert logic.sensor_state(None, []) == (None, {})
    state, attrs = logic.sensor_state(logic.resolve_event(ev("a"), date(2026, 10, 18)), [])
    assert state == datetime(2026, 10, 19, 18, 30)
    assert attrs["event_id"] == "a" and attrs["participation"] == "offen"
```

- [ ] **Step 2: Run test to verify it fails** — FAIL.

- [ ] **Step 3: Implement `logic.py`** per Interfaces. `resolve_year`: build `date(today.year, month, day)`; if it is more than one day before `today`, use `today.year + 1`; guard `ValueError` (e.g. Feb 29) by falling back to `today.year`. `resolve_events` sorts by `start`. `sensor_state(None, ...)` returns `(None, {})`.

- [ ] **Step 4: Run test to verify it passes** — `python -m pytest tests/test_logic.py -v` → PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(logic): date resolution, event selection, sensor view-model"`

---

### Task 5: API client — session, login, members, member switch

**Files:**
- Create: `custom_components/spielerplus/api.py`
- Test: `tests/test_api_auth.py`

**Interfaces:**
- Consumes: `const.*`, `models.*`, `parser.parse_members`.
- Produces:
  - `api.SpielerplusError(Exception)`, `api.SpielerplusAuthError(SpielerplusError)`
  - `api.SpielerplusClient(session: aiohttp.ClientSession, email: str, password: str)`
  - `async api.SpielerplusClient.async_login() -> None` — GET `LOGIN_URL`, extract CSRF from `<meta name="csrf-token">` or `<input name="_csrf">`, POST `LOGIN_URL` with `_csrf`, `LoginForm[email]`, `LoginForm[password]`; on failure (non-200, or a returned page whose `<title>` is still `Einloggen`) raise `SpielerplusAuthError`.
  - `async api.SpielerplusClient.async_get_members() -> list[SpMember]` — GET `SELECT_TEAM_URL`, `parse_members`; if the title is `Einloggen` raise `SpielerplusAuthError`.
  - `async api.SpielerplusClient.async_select_member(member_id: str) -> None` — GET `SWITCH_USER_URL` with `params={"id": member_id}`.
  - `api.SpielerplusClient.lock: asyncio.Lock` — every public method acquires it (serializes reads/writes / `switch-user`).

- [ ] **Step 1: Write the failing test** — `tests/test_api_auth.py` using `aioresponses`:

```python
import re
import pytest
from aioresponses import aioresponses
import aiohttp
from custom_components.spielerplus.api import SpielerplusAuthError, SpielerplusClient
from custom_components.spielerplus import const
from custom_components.spielerplus.models import SpMember

LOGIN_PAGE = '<html><head><meta name="csrf-token" content="TOK"></head></html>'
TEAM_PAGE = ('<html><title>Team auswählen</title>'
             '<div class="select-team-item"><a href="/site/switch-user?id=101"></a>'
             '<h4 class="dark">Team A</h4><small>Kind Eins</small></div></html>')

@pytest.mark.asyncio
async def test_login_and_members():
    with aioresponses() as m:
        m.get(const.LOGIN_URL, body=LOGIN_PAGE)
        m.post(const.LOGIN_URL, body='<html><title>Team auswählen</title></html>')
        m.get(const.SELECT_TEAM_URL, body=TEAM_PAGE)
        m.get(re.compile(re.escape(const.SWITCH_USER_URL)), status=200, body="<html></html>")
        async with aiohttp.ClientSession() as session:
            client = SpielerplusClient(session, "a@b.c", "secret")
            await client.async_login()
            assert await client.async_get_members() == [SpMember(id="101", name="Kind Eins", team="Team A")]
            await client.async_select_member("101")

@pytest.mark.asyncio
async def test_login_failure_raises_auth_error():
    with aioresponses() as m:
        m.get(const.LOGIN_URL, body=LOGIN_PAGE)
        m.post(const.LOGIN_URL, body='<html><title>Einloggen</title></html>')
        async with aiohttp.ClientSession() as session:
            with pytest.raises(SpielerplusAuthError):
                await SpielerplusClient(session, "a@b.c", "bad").async_login()
```

- [ ] **Step 2: Run test to verify it fails** — `python -m pytest tests/test_api_auth.py -v` → FAIL.

- [ ] **Step 3: Implement `api.py`** per Interfaces. Use `page.text()` and a small `_title(html)` helper; raise `SpielerplusAuthError` when the login/select-team page title is `Einloggen`/`Login`. Wrap `aiohttp` errors into `SpielerplusError`.

- [ ] **Step 4: Run test to verify it passes** — PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(api): login, member list and member switch"`

---

### Task 6: API client — events (pagination) and participation

**Files:**
- Modify: `custom_components/spielerplus/api.py`
- Test: `tests/test_api_events.py`

**Interfaces:**
- Consumes: Task 5 client, `parser.parse_events`, `logic.participation_value`.
- Produces:
  - `async api.SpielerplusClient.async_get_events() -> list[SpEvent]` — GET `EVENTS_URL`; if title is `Einloggen` raise `SpielerplusAuthError`; then loop `POST AJAX_EVENTS_URL` with `{"offset": n}` starting at `5`, step `5`, parsing `response.json()["html"]`, merging by event id, stopping when `html` is empty or `count` is absent/`-1`.
  - `async api.SpielerplusClient.async_set_participation(member_id: str, event_type: str, event_id: str, status: Participation, reason: str = "") -> None` — POST `PARTICIPATION_URL` with `Participation[type]`, `Participation[typeid]`, `Participation[participation]` (= `participation_value(status)`), `Participation[user_id]`, `Participation[reason]`; raise `SpielerplusError` on non-200.

- [ ] **Step 1: Write the failing test** — `tests/test_api_events.py`: mock `EVENTS_URL` returning the two-panel fixture, then `AJAX_EVENTS_URL` returning `{"html": <one-panel>, "count": 2}` and then `{"html": "", "count": -1}`; assert `async_get_events()` returns the merged, de-duplicated events. Separate test asserts the participation POST receives `Participation[participation]=="0"` for `Participation.ABSAGE` (inspect the recorded request body).

- [ ] **Step 2: Run test to verify it fails** — FAIL.

- [ ] **Step 3: Implement** the two methods per Interfaces, reusing the Task 5 lock and auth-title check.

- [ ] **Step 4: Run test to verify it passes** — `python -m pytest tests/test_api_events.py -v` → PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(api): fetch events with pagination and set participation"`

---

### Task 7: Coordinator and integration setup

**Files:**
- Create: `custom_components/spielerplus/coordinator.py`
- Modify: `custom_components/spielerplus/__init__.py`
- Test: none (HA import — verified by `py_compile` + live run in Task 13). Pure derivation it relies on is covered by Task 4.

**Interfaces:**
- Consumes: `SpielerplusClient`, `logic.resolve_events`/`upcoming`, `const.*`, `models.SpMember`.
- Produces:
  - `coordinator.MemberData` dataclass `(member: SpMember, events: list[ResolvedEvent])`
  - `coordinator.SpielerplusCoordinator(DataUpdateCoordinator[dict[str, MemberData]])` with `__init__(hass, entry, client)`; `_async_update_data` iterates `entry.data[CONF_MEMBERS]`, and for each member id calls `async_select_member`, `async_get_events`, `resolve_events(..., date.today())`, `upcoming(..., datetime.now())`, and builds `MemberData`. Raises `ConfigEntryAuthFailed` on `SpielerplusAuthError` and `UpdateFailed` on `SpielerplusError` or when a member yields zero parsed events while the page title was `Termine`.
  - `__init__.async_setup_entry(hass, entry) -> bool`, `async_unload_entry`; stores `hass.data[DOMAIN][entry.entry_id] = {"client", "coordinator", "members"}` and forwards `calendar`, `sensor`, `button`.

- [ ] **Step 1: Implement `coordinator.py`** per Interfaces (subclass HA `DataUpdateCoordinator`, `update_interval` from `entry.options.get(CONF_SCAN_INTERVAL, 15)` minutes).

- [ ] **Step 2: Implement `__init__.py`**: create session via `async_create_clientsession(hass)`, build `SpielerplusClient`, log in, create coordinator with `await coordinator.async_config_entry_first_refresh()`, register `PLATFORMS = [Platform.CALENDAR, Platform.SENSOR, Platform.BUTTON]`, and implement unload/reload.

- [ ] **Step 3: Verify it compiles** — `python -m py_compile custom_components/spielerplus/coordinator.py custom_components/spielerplus/__init__.py` → no output (success). (`homeassistant` is not installed locally; py_compile checks syntax only.)

- [ ] **Step 4: Commit** — `git commit -am "feat: coordinator and integration setup"`

---

### Task 8: Calendar platform

**Files:**
- Create: `custom_components/spielerplus/calendar.py`
- Test: none (HA import) — pure derivation covered by `logic.calendar_range`.

**Interfaces:**
- Consumes: `coordinator.SpielerplusCoordinator`, `logic.calendar_range`/`event_summary`, `models.*`.
- Produces: `calendar.async_setup_entry(hass, entry, async_add_entities)` creating one `SpielerplusCalendar(CoordinatorEntity, CalendarEntity)` per member; `unique_id = f"{entry.entry_id}:{member_id}:calendar"`; `device_info` from the member; `async_get_events(hass, start_date, end_date)` returns `CalendarEvent` objects (summary `event_summary`, `start`/`end` from the resolved event, `location`, description `f"{type} · {participation}"`, `uid = event.id`) for the events in range.

- [ ] **Step 1: Implement `calendar.py`** per Interfaces, pulling events from `coordinator.data[member_id].events`.
- [ ] **Step 2: Verify it compiles** — `python -m py_compile custom_components/spielerplus/calendar.py`.
- [ ] **Step 3: Commit** — `git commit -am "feat(calendar): per-member calendar entity"`

---

### Task 9: Sensor platform

**Files:**
- Create: `custom_components/spielerplus/sensor.py`
- Test: none (HA import) — `logic.sensor_state` is covered in Task 4.

**Interfaces:**
- Consumes: `coordinator.SpielerplusCoordinator`, `logic.next_event`/`sensor_state`.
- Produces: `sensor.async_setup_entry` creating, per member, two `SpielerplusNextEventSensor(CoordinatorEntity, SensorEntity)` instances: one with `type_filter="training"` (`_attr_translation_key = "next_training"`, suffix `naechstes_training`) and one with `type_filter=None` (`next_event` / `naechster_termin`). `native_value` = `logic.next_event(...).start` or `None`; `_attr_device_class = SensorEntityDescription` `device_class=timestamp`; `extra_state_attributes = logic.sensor_state(...)[1]`; `unique_id = f"{entry.entry_id}:{member_id}:sensor:{type_filter or 'any'}"`.

- [ ] **Step 1: Implement `sensor.py`** per Interfaces.
- [ ] **Step 2: Verify it compiles** — `python -m py_compile custom_components/spielerplus/sensor.py`.
- [ ] **Step 3: Commit** — `git commit -am "feat(sensor): next training and next event sensors"`

---

### Task 10: Button platform

**Files:**
- Create: `custom_components/spielerplus/button.py`
- Test: none (HA import) — deadline/selection behavior is covered by `logic` (Task 4) and the service error handling (Task 11).

**Interfaces:**
- Consumes: `SpielerplusClient`, `coordinator.SpielerplusCoordinator`, `logic.next_event`, `models.Participation`.
- Produces: `button.async_setup_entry` creating, per member, two `SpielerplusParticipationButton(CoordinatorEntity, ButtonEntity)`: `status=Participation.ZUSAGE` (`_attr_translation_key="accept"`) and `status=Participation.ABSAGE` (`decline`). `available` is `False` when the next upcoming event is `None` or its `deadline_passed` is `True`. `async_press()` calls `client.async_set_participation(member_id, event.type, event.id, self._status)` then `await coordinator.async_request_refresh()`.

- [ ] **Step 1: Implement `button.py`** per Interfaces.
- [ ] **Step 2: Verify it compiles** — `python -m py_compile custom_components/spielerplus/button.py`.
- [ ] **Step 3: Commit** — `git commit -am "feat(button): accept/decline buttons for the next event"`

---

### Task 11: Service `spielerplus.set_participation`

**Files:**
- Create: `custom_components/spielerplus/services.py`
- Modify: `custom_components/spielerplus/__init__.py` (register/unregister in setup/unload)
- Test: none (HA import) — command construction is covered by Task 6.

**Interfaces:**
- Consumes: `const.DOMAIN`, `hass.data[DOMAIN][entry_id]`, entity registry `unique_id` format `f"{entry_id}:{member_id}:{kind}"`, `logic.participation_value`.
- Produces: `services.async_setup_services(hass)` / `async_unload_services(hass)` registering `set_participation` with `supports_response=SupportsResponse.OPTIONAL`. Schema: target `entity` (one of the member's entities), `event_id: str` (required), `status: str` (required, choices `zusage|unsicher|absage`), `reason: str` (optional). Handler: resolve the target's registry entry → parse `entry_id`/`member_id` from `unique_id` → get `coordinator`+`client` from `hass.data` → find the event by `event_id` in `coordinator.data[member_id].events` for its `type` (fallback `"training"`) → call `client.async_set_participation(...)` → `async_request_refresh()`. Raise `ServiceValidationError` when the target is unknown, the event is not found, or `deadline_passed` is `True`; raise `HomeAssistantError` for transport errors.

- [ ] **Step 1: Implement `services.py`** per Interfaces.
- [ ] **Step 2: Wire into `__init__.py`**: call `async_setup_services(hass)` once (guard with a flag) in `async_setup_entry`, and `async_unload_services` in `async_unload_entry` when the last entry is removed.
- [ ] **Step 3: Verify it compiles** — `python -m py_compile custom_components/spielerplus/services.py custom_components/spielerplus/__init__.py`.
- [ ] **Step 4: Commit** — `git commit -am "feat: add spielerplus.set_participation service"`

---

### Task 12: Config flow, options flow, strings

**Files:**
- Create: `custom_components/spielerplus/config_flow.py`, `custom_components/spielerplus/strings.json`, `custom_components/spielerplus/translations/de.json`
- Test: none (HA import) — `parse_members` (Task 2) and `logic.member_options` (Task 4) cover the parsing/mapping.

**Interfaces:**
- Consumes: `SpielerplusClient`, `parse_members`, `logic.member_options`, `const.*`.
- Produces: `config_flow.SpielerplusConfigFlow(ConfigFlow, domain=DOMAIN)` with `VERSION = 1`, `async_step_user` (email + password; on submit create client, `async_login`, `async_get_members`; store in `self._members`, go to `async_step_members`), `async_step_members` (multi-select of `member_options(self._members)`, `SelectSelector` with `multiple=True`; create entry `data={"email", "password", CONF_MEMBERS: {id: label}}`), and `async_step_reauth`/`async_step_reauth_confirm` (re-enter password, validate, `async_update_reload_and_abort`). Plus `SpielerplusOptionsFlow(OptionsFlow)` with a scan-interval `SelectSelector` (5/10/15/30/60). Error keys: `invalid_auth`, `cannot_connect`, `no_members`. `logic.member_options(members)` returns `{m.id: m.label}`.

- [ ] **Step 1: Add `logic.member_options`** with the Task 4 test file (`tests/test_logic.py`): `assert logic.member_options([SpMember("101","Kind Eins","Team A")]) == {"101": "Kind Eins (Team A)"}`. Run `python -m pytest tests/test_logic.py -v` → PASS; commit.
- [ ] **Step 2: Implement `config_flow.py`**, `strings.json`, `translations/de.json` per Interfaces (German labels, e.g. „E-Mail", „Passwort", „Mitglieder").
- [ ] **Step 3: Verify it compiles** — `python -m py_compile custom_components/spielerplus/config_flow.py`.
- [ ] **Step 4: Commit** — `git commit -am "feat(config_flow): UI setup, member selection, options and reauth"`

---

### Task 13: README, deployment and live verification

**Files:**
- Modify: `README.md`
- Deploy: `192.168.1.156:/config/custom_components/spielerplus/`

**Interfaces:**
- Consumes: everything above.
- Produces: a deployed, working integration.

- [ ] **Step 1: Write `README.md`** (Installation via HACS / manual, Einrichtung, Entitäten-Tabelle, Service-Beispiel, Testhinweis). No credentials or personal data.
- [ ] **Step 2: Run the full test suite** — `python -m pytest -v` → all tests PASS.
- [ ] **Step 3: Deploy** — `rsync -a --delete custom_components/spielerplus/ root@192.168.1.156:/config/custom_components/spielerplus/ && ssh root@192.168.1.156 'ha core restart'`; then wait for `ha core info` to report running.
- [ ] **Step 4: Verify read path live** — via SSH check `home-assistant.log` for `spielerplus` errors; via the HA REST/WebSocket API confirm the member devices and entities exist and that `sensor.*_naechstes_training` shows a plausible future timestamp. Compare the next training against the SpielerPlus app.
- [ ] **Step 5: Verify the write path (ONLY after explicit user approval)** — press one member's „Zusagen" button for the farthest-future event, confirm the change in the app and that the entity state flips, then set it back. Record the outcome.
- [ ] **Step 6: Commit** — `git commit -am "docs: usage, deployment notes and verified entity overview"` (README only; no personal data).
- [ ] **Step 7: Push** — `git push -u origin main`.

---

## Self-Review

- **Spec coverage:** §1 goal → Tasks 7–13; §2 non-goals respected (no create/delete events, no treasury/chat); §3 endpoints/values → Tasks 1,5,6; §4 architecture → Tasks 1–12 (added `logic.py`, consistent with `ha-ngs-amm-portal`); §5 data flow → Tasks 7,11,12; §6 entities/service → Tasks 8,9,10,11; §7 polling/errors/reauth → Tasks 5,7,12; §8 tests → Tasks 1–6,12; §9 deployment → Task 13; §10 security → Global Constraints + Task 13.
- **Step scan:** each step is one action; no "handle edge cases" placeholders.
- **Type consistency:** `MemberData`, `ResolvedEvent`, `resolve_events`, `upcoming`, `next_event`, `sensor_state`, `unique_id = f"{entry_id}:{member_id}:{kind}"` and `PARTICIPATION_VALUES` are used identically across tasks.
- **Review Focus:** each of the five lines is pinned to a task (1→3/7, 2→4, 3→4/10/11, 4→5/7, 5→5/6/7).
- **Proportion:** implementer-facing signatures and assertions only; bodies are left to the implementer.
