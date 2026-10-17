# ha-spielerplus

Home-Assistant-Custom-Integration für **SpielerPlus / TeamPlus** (`https://www.spielerplus.de`).
Sie zeigt die kommenden **Trainings und Spiele** der im Account verwalteten Mitglieder
als Kalender und Sensoren an und erlaubt die **Zu-/Absage** direkt aus Home Assistant.

> **Inoffiziell.** Es gibt keine öffentliche Termin-/Teilnahme-API. Die Integration nutzt
> die normale Web-Session (Login + `switch-user`) und liest die HTML-Seiten aus. Ändert
> SpielerPlus seine Oberfläche, kann das Parsen brechen — dann meldet die Integration
> „unavailable" statt still falsche Daten anzuzeigen.

## Funktionen

- Pro Mitglied ein **Gerät** mit Kalender, Sensoren und Buttons.
- **Kalender** mit allen kommenden Terminen (Training, Spiel, sonstige).
- **Sensoren** „Nächstes Training" und „Nächster Termin" (Zeitpunkt + Details als Attribute).
- **Buttons** „Zusagen" / „Absagen" für den jeweils nächsten kommenden Termin.
- **Service** `spielerplus.set_participation` für beliebige Termine (Automationen/Dashboards).
- Aktualisierungsintervall über die Optionen einstellbar (Standard 15 Minuten).

## Installation

### Über HACS (empfohlen)

1. HACS → Integrationen → Drei-Punkte-Menü → **Benutzerdefinierte Repositories**
2. URL `https://github.com/christophmertins/ha-spielerplus` hinzufügen, Kategorie **Integration**
3. „SpielerPlus" installieren und Home Assistant neu starten.

### Manuell

Ordner `custom_components/spielerplus/` nach `<config>/custom_components/` kopieren und
Home Assistant neu starten. HA installiert die Abhängigkeit `beautifulsoup4` selbst.

## Einrichtung

**Einstellungen → Geräte & Dienste → Integration hinzufügen → „SpielerPlus"**, dann
E-Mail und Passwort des SpielerPlus-Accounts eingeben. Im zweiten Schritt werden die im
Account gefundenen Mitglieder/Teams angezeigt; wähle die Mitglieder, deren Termine
angezeigt werden sollen. Die Zugangsdaten werden nur im Config-Entry gespeichert (nicht in YAML).

Der Account muss mehrere Mitglieder über „Team auswählen" verwalten können (Elternaccount);
die Integration liest diese Liste automatisch aus.

## Entitäten

Beispiel für ein Mitglied „Kind Eins" (Gerät „SpielerPlus Kind Eins"):

| Entity | Bedeutung |
|---|---|
| `calendar.spielerplus_kind_eins` | kommende Termine (Training und Spiele) |
| `sensor.spielerplus_kind_eins_naechstes_training` | Beginn des nächsten Trainings |
| `sensor.spielerplus_kind_eins_naechster_termin` | Beginn des nächsten Termins (jeder Typ) |
| `button.spielerplus_kind_eins_zusagen` | nächsten Termin zusagen |
| `button.spielerplus_kind_eins_absagen` | nächsten Termin absagen |

Sensor-Attribute: `event_id`, `event_type`, `title`, `start`, `end`, `meeting_time`,
`location` (best-effort; die Terminliste enthält keinen Ort), `participation`
(`zusage`/`unsicher`/`absage`/`offen`), `deadline_passed`, `events` (Liste der kommenden Termine).

Die Buttons sind `unavailable`, wenn kein kommender Termin existiert oder die Zu-/Absagefrist
abgelaufen ist.

## Service `spielerplus.set_participation`

```yaml
service: spielerplus.set_participation
target:
  entity_id: sensor.spielerplus_kind_eins_naechster_termin
data:
  event_id: "12345678"
  status: absage          # zusage | unsicher | absage
  reason: krank           # optional
```

`event_id` steht in den Attributen der Sensoren. `event_type` ist optional und wird sonst
aus den bekannten Terminen ermittelt.

## Tests

Reine Logik-, Parser- und API-Tests ohne Home-Assistant-Abhängigkeit:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
```

## Technischer Hintergrund

- Anmeldung über `POST /site/login` (CSRF-Token aus dem Formular), danach Mitgliedswechsel
  über `GET /site/switch-user?id=<id>`.
- Terminliste aus `GET /events` plus Pagination über `POST /events/ajaxgetevents`.
- Zu-/Absage über `POST /events/ajax-participation-form` (`1` Zusage, `2` Unsicher, `0` Absage).
- Session-Ablauf führt in den Reauth-Flow; Netz-/Parse-Fehler setzen die Entitäten auf
  `unavailable`, ohne den letzten Wert zu verwerfen.

## Lizenz

GPL-2.0 (siehe `LICENSE`).
