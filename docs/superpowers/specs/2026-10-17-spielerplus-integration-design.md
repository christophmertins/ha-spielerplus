# Design: Home-Assistant-Integration `spielerplus`

**Datum:** 2026-10-17
**Status:** Entwurf — zur Freigabe
**Zielsystem:** Home Assistant 2026.10.1 auf HA Yellow (`192.168.1.156`, `/config`)
**Repo:** https://github.com/christophmertins/ha-spielerplus

## 1. Ziel & Nutzen

Die Termine (Trainings und Spiele) aus **SpielerPlus** (TeamPlus) sollen in der eigenen
Home-Assistant-Instanz sichtbar werden, und die **Zu-/Absage** soll direkt aus HA möglich
sein. Ein SpielerPlus-Account verwaltet mehrere Mitglieder/Teams (Elternaccount); die
Integration bildet **je Mitglied** ein Gerät mit Kalender, Sensoren und Buttons ab.

Erfolgskriterien:
- Zugangsdaten werden ausschließlich über die HA-UI eingegeben und **nicht** im Repo oder in YAML gespeichert.
- Je gewähltem Mitglied gibt es einen Kalender mit den kommenden Terminen (Training, Spiel, sonstige).
- Der nächste Termin ist als Sensor mit Details (Typ, Zeiten, Ort, Teilnahmestatus) verfügbar.
- Zu- und Absagen funktionieren per Ein-Klick-Button und per Service; der Status aktualisiert sich danach in HA.
- Nach einem HA-Neustart läuft alles ohne manuelles Eingreifen weiter; eine abgelaufene Session wird automatisch neu aufgebaut.

## 2. Nicht-Ziele (YAGNI)

- Keine automatische Dauerzusage (bewusst nicht gewählt).
- Kein Anlegen/Bearbeiten/Löschen von Terminen (nur Teilnahme-Status ändern).
- Keine Teamkasse, kein Chat, keine News, keine Dokumente, keine Statistik.
- Keine Mehrfach-Accounts, keine HACS-Releases-Automatik.
- Keine Historien-/Statistik-Funktionen.

## 3. Verifizierte Fakten über SpielerPlus

Read-only gegen die Live-Seite geprüft (nur lesend; kein Schreibzugriff im Rahmen der
Recherche). Es handelt sich um eine klassische Yii2-Webanwendung mit Session-Cookies und
HTML-AJAX-Endpunkten; es gibt keine dokumentierte öffentliche Termin-/Teilnahme-API.

**Basis:** `https://www.spielerplus.de`

| Zweck | Methode & Pfad | Wesentliche Felder |
|---|---|---|
| Login-Seite | `GET /site/login` | enthält CSRF-Token (`<meta name="csrf-token">` bzw. `<input name="_csrf">`) |
| Anmelden | `POST /site/login` | `_csrf`, `LoginForm[email]`, `LoginForm[password]` |
| Team-/Mitgliederwahl | `GET /site/select-team` | je Eintrag: `switch-user?id=<id>`, Teamname (`h4`/`list-label`) und Mitgliedsname (`small`/`list-sublabel`) |
| Mitglied/Team wechseln | `GET /site/switch-user?id=<id>` | setzt den aktiven Kontext (Session-Cookie) |
| Terminliste | `GET /events` | Panels `div.panel#event-<type>-<id>` |
| Termin-Pagination | `POST /events/ajaxgetevents` | `offset` (Schrittweite 5); Antwort JSON `{ "html": "...", "count": n }` |
| Teilnahme-Popup | `POST /events/ajaxgetparticipation` | `eventid`, `eventtype` → JSON `{ "html": "..." }` (nicht benötigt, nur informativ) |
| Zu-/Absage | `POST /events/ajax-participation-form` | `Participation[type]`, `Participation[typeid]`, `Participation[participation]`, `Participation[user_id]`, `Participation[reason]` |

**Termin-Panel (HTML-Struktur):**
- `div.panel#event-<type>-<id>` — `type` ist z. B. `training` (Spiele analog, generisch zu behandeln).
- Kopf: `.panel-heading-info > .panel-title` (Wochentag, z. B. „Mo.") und `.panel-subtitle` (Datum, z. B. „19.10").
- Titel: `.panel-heading-text > .panel-title` (z. B. „Training").
- Zeiten: `.event-time .event-time-item` → `.event-time-label` (Treffen/Beginn/Ende) + `.event-time-value`.
- Teilnahme-Widget: `.participation-widget.participation-widget-<type>-<eventid>-<userid>` mit drei Buttons
  (`.participation-button`, `onClick="showParticipationForm('<type>', <eventid>, <status>, <userid>')`).
  Der aktuelle Status ist die Schaltfläche mit Klasse `selected` (`title` = „Zugesagt" / „Unsicher" / „Absagen / Abwesend").
- Details-Link: `a.event-header-border[href="/<type>/view?id=<id>"]`.
- Ist die Zu-/Absagefrist vorbei: Buttons tragen `disabled` und es gibt `.countdown` („Zeit zum Zu-/Absagen abgelaufen").

**Teilnahmewerte** (`Participation[participation]`): `1` = Zusage, `2` = Unsicher, `0` = Absage.

**Ablauf laut Frontend-JS:** `showParticipationForm()` öffnet ein Modal; der eigentliche
Zu-/Absage-Vorgang ist ein `POST /events/ajax-participation-form` mit den o. g. Feldern.
Auf der Terminseite ist **kein** CSRF-Token vorhanden; maßgeblich ist das Session-Cookie.

**Mitgliederstruktur:** Der Account hat mehrere `switch-user`-Einträge (mehrere Teams bzw.
mehrere Mitglieder), u. a. zwei Kinder im Junior-Team. Nach `switch-user` liefert `/events`
die Termine des jeweils aktiven Mitglieds. Konkrete Namen und IDs gehören **nicht** ins Repo.

## 4. Architektur & Komponenten

Custom-Integration unter `custom_components/spielerplus/`:

```
custom_components/spielerplus/
├── manifest.json      # domain=spielerplus, requirements=["beautifulsoup4==4.12.3"], config_flow=true
├── const.py           # DOMAIN, URLs, Poll-Intervall, Participation-Werte, Attributnamen
├── api.py             # SpielerplusClient: Session, Login (CSRF), switch-user, events, ajax-participation-form
├── parser.py          # reine Funktionen: HTML -> SpEvent / Member (ohne Netz & HA)
├── coordinator.py     # DataUpdateCoordinator: je Mitglied Termine holen, filtern, nächsten bestimmen
├── config_flow.py     # UI-Einrichtung (E-Mail/Passwort), Mitgliederauswahl, Reauth, Options
├── calendar.py        # CalendarEntity je Mitglied
├── sensor.py          # Sensor „nächstes Training" + „nächster Termin" je Mitglied
├── button.py          # Button „Zusagen" / „Absagen" je Mitglied
├── services.py        # Service spielerplus.set_participation
├── strings.json + translations/de.json
└── __init__.py        # async_setup_entry / unload / reload, Session-Lebenszyklus
```

Verantwortlichkeiten:
- **`api.py` / `SpielerplusClient`**: einzige Stelle mit Netzwerkzugriff. Kapselt aiohttp-Session
  (eigene `ClientSession` mit Cookie-Jar, im Setup erzeugt, beim Unload geschlossen), CSRF-Beschaffung,
  Login, Mitgliederwechsel, Terminliste inkl. Pagination und die Teilnahme-POSTs. Liefert geparste,
  typisierte Strukturen; kennt keine HA-Entities.
- **`parser.py`**: reine Funktionen auf HTML-Strings (`parse_members(html)`, `parse_events(html)`,
  `parse_participation(html)`), vollständig isoliert und ohne Netz testbar. Nutzt BeautifulSoup.
- **`coordinator.py`**: orchestriert einen Zyklus — je gewähltem Mitglied `switch-user` + Termine
  laden, Ergebnis je Mitglied zusammenfassen (kommende Termine, nächster Termin, aktueller Status).
- **`config_flow.py`**: `async_step_user` (Login testen, Mitgliederliste laden),
  `async_step_members` (Mehrfachauswahl), Reauth-Step, Options-Flow (Poll-Intervall).
- **Entities** (`calendar`/`sensor`/`button`): lesen nur aus `coordinator.data`; Schreibaktionen
  rufen den `SpielerplusClient` auf und lösen danach einen Coordinator-Refresh aus.

## 5. Datenfluss

1. **Einrichtung:** Nutzer gibt E-Mail + Passwort ein. Die Integration loggt ein, lädt
   `/site/select-team`, parst die Mitglieder (Name + Team + switch-user-ID) und zeigt sie zur
   **Mehrfachauswahl**. Auswahl + Zugangsdaten landen im Config-Entry (Passwort via
   `vol.Required`/`vol.Optional` als Passwort-Selektor, nur im Entry gespeichert).
2. **Setup:** `__init__` erzeugt Client + `DataUpdateCoordinator`, startet ihn und lädt die
   Platforms `calendar`, `sensor`, `button`.
3. **Aktualisierung** (Standard 15 min, im Options-Flow einstellbar): je Mitglied
   `GET /site/switch-user?id=<id>` → `GET /events` → ggf. `POST /events/ajaxgetevents`
   (Pagination) → parsen → auf kommende Termine filtern → nächsten Termin + Status bestimmen.
4. **Zu-/Absage:** Button/Service → `POST /events/ajax-participation-form` mit den o. g. Feldern →
   bei Erfolg sofortiger `async_request_refresh()`, damit die Entitäten den neuen Status zeigen.
5. **Reauth:** Läuft die Session ab (Login-Seite statt Termine), wirft der Client ein
   Auth-Signal → `ConfigEntryAuthFailed` → HA startet den Reauth-Flow. Der Client versucht
   vorher einen erneuten Login mit den gespeicherten Zugangsdaten.

## 6. Entitäten & Service

Gerät je Mitglied (`identifiers = {(DOMAIN, <switch-user-id>)}`, Name „SpielerPlus <Mitglied>"),
Gerätename aus dem in der Mitgliederliste gefundenen Namen. Beispiel (Mitglied „X"):

| Entity | Typ | Inhalt |
|---|---|---|
| `calendar.spielerplus_x` | `CalendarEntity` | alle kommenden Termine (Training, Spiel, sonstige) im gefragten Zeitraum |
| `sensor.spielerplus_x_naechstes_training` | Sensor, `device_class=timestamp` | Beginn des nächsten **Trainings** |
| `sensor.spielerplus_x_naechster_termin` | Sensor, `device_class=timestamp` | Beginn des nächsten Termins **beliebigen** Typs |
| `button.spielerplus_x_zusagen` | Button | setzt den nächsten kommenden Termin auf Zusage (1) |
| `button.spielerplus_x_absagen` | Button | setzt den nächsten kommenden Termin auf Absage (0) |

Sensor-Attribute (beide Sensoren): `event_id`, `event_type` (`training`/`game`/…), `title`,
`start`, `end`, `meeting_time`, `location`, `participation` (`zusage`/`unsicher`/`absage`/`offen`),
`deadline_passed` (bool), `events` (Liste der kommenden Termine mit denselben Feldern).

Buttons sind `unavailable`, wenn es keinen kommenden Termin gibt oder die Zu-/Absagefrist
abgelaufen ist. Der Kalender-Eintrag (`summary`) nutzt den Termintitel, `location` den Ort und
beschreibt in der Beschreibung Typ + Teilnahmestatus.

**Service `spielerplus.set_participation`**
- `target`: `entity_id` (Kalender, Sensor oder Button eines Mitglieds; die Zuordnung erfolgt
  über die Entität → Config-Entry/Mitglied).
- Parameter: `event_id` (String, Pflicht), `status` (`zusage`|`unsicher`|`absage`, Pflicht),
  `event_type` (String, optional; sonst aus dem Coordinator-Cache), `reason` (String, optional).
- Wirkung: `POST /events/ajax-participation-form`; danach Refresh. Fehler werden als
  `ServiceValidationError`/`HomeAssistantError` mit klarer Meldung zurückgegeben.

## 7. Aktualisierung, Fehlerbehandlung, Reauth

- Standard-Polling: **15 Minuten**; im Options-Flow wählbar (5/10/15/30/60 min).
- Auth-Fehler (Login schlägt fehl / Session abgelaufen und Re-Login erfolglos):
  `ConfigEntryAuthFailed` → HA startet den Reauth-Flow.
- Netzwerkfehler, Timeouts, unerwartetes HTML (Parser findet keine Panels auf einer als
  „Termine" betitelten Seite): `UpdateFailed` → Entities `unavailable`, letzter Wert bleibt
  (`RestoreSensor`), HA-`DataUpdateCoordinator` übernimmt Backoff.
- Überlappende Schreib- und Lesevorgänge je Account werden serialisiert (Lock im Client),
  damit der `switch-user`-Kontext nicht durcheinander gerät.
- Alle HTTP-Aufrufe mit Timeout; Nicht-200-Antworten werden als Fehler behandelt.

## 8. Tests

Pytest, reine Logiktests mit gemockter HTTP-Schicht (keine echten Zugangsdaten):
- `parser.py`: Fixtures echter HTML-Ausschnitte — Trainings-Panel, Nicht-Training-Panel,
  Panel mit abgelaufener Frist (`disabled` + `.countdown`), Mitgliederliste mit mehreren
  Einträgen (Team + Name), leere/defekte Ausschnitte.
- Terminlogik: „nächster Termin" / „nächstes Training" inkl. Randfälle (keine kommenden
  Termine, nur Spiele übrig, gleicher Tag, Termin in der Vergangenheit).
- `api.py`: Login inkl. CSRF-Extraktion, `switch-user`, Pagination über `ajaxgetevents`,
  Teilnahme-POST mit korrekten Feldern (1/2/0), Fehler-/Auth-Signale — alles gegen eine
  gemockte aiohttp-Schicht.
- `config_flow.py`: Login ok/fehlschlag, Mitgliederauswahl, Reauth, Options.
- Vollständiger HA-Testharness (`pytest-homeassistant-custom-component`) ist optional und
  kann in einem Folgeschritt ergänzt werden.

## 9. Deployment

1. Repo `ha-spielerplus` enthält `custom_components/spielerplus/`, `hacs.json`, `README.md`,
   `tests/`, `pytest.ini`, `requirements_test.txt`.
2. `rsync`/`scp` `custom_components/spielerplus/` nach `192.168.1.156:/config/custom_components/`.
3. `ha core restart` (per SSH; key-basierter Zugang vorhanden).
4. Einrichtung über **Einstellungen → Geräte & Dienste → Integration hinzufügen → SpielerPlus**.
5. Verifikation: Geräte/Entitäten vorhanden, Termine plausibel, `home-assistant.log` ohne Fehler.
6. Der Schreibpfad (Zu-/Absage) wird **einmal** an einem unkritischen, weit entfernten Termin
   getestet — nur nach ausdrücklicher Freigabe.

HACS: Das Repo kann als benutzerdefiniertes Repository (Kategorie „Integration") hinzugefügt werden.

## 10. Sicherheit

- Passwort wird nur im HA-Config-Entry (`/config/.storage`) gespeichert, **nie** im Git-Repo.
- Repo ist öffentlich: Doku, Tests und Fixtures enthalten ausschließlich Platzhalter —
  keine echten Namen, Mitglied-IDs, Zugangsdaten oder Termindaten.
- Das Passwort wurde in der Konversation geteilt; ein Wechsel nach der Einrichtung wird empfohlen.
- Die Integration führt Schreibaktionen (Zu-/Absagen) im Namen des Nutzers aus; es gibt keine
  automatischen Schreibaktionen ohne Nutzerauslösung.
