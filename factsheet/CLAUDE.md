# CLAUDE.md - S7 Baierbrunn Monatsdatenblatt & Schulweg-Datenblatt

Dieses Repo erzeugt jeden Monat zwei einseitige DIN-A4-PDF-Datenblaetter zur
Betriebsqualitaet der S-Bahn-Linie **S7** am Bahnhof **Baierbrunn**: das
Monatsdatenblatt (`generate.py`, Gesamtmonat) und das Schulweg-Datenblatt
(`schulweg.py`, Morgenverkehr Mo-Fr 06:30-08:30).

## Aufgabe

Wenn du (Claude Code) in diesem Repo laeufst, ist dein Ziel:

1. Das Monatsdatenblatt **und** das Schulweg-Datenblatt fuer den zuletzt
   abgeschlossenen Kalendermonat erzeugen.
2. Pruefen, dass beide Ergebnisse korrekt und je einseitig sind.
3. Beide PDFs nach `output/` committen.

Der eigentliche Aufbau ist **deterministisch** und steckt in `generate.py`
(Monatsdatenblatt) und `schulweg.py` (Schulweg-Datenblatt). Du sollst die
Zahlen **nicht selbst berechnen oder schaetzen** - immer die Skripte laufen
lassen.

## Standardablauf

```bash
# Vormonat automatisch:
python generate.py
python schulweg.py

# oder expliziter Monat (Backfill):
python generate.py --month 2026-06
python schulweg.py --month 2026-06
```

Das erzeugt:
- `output/S7_Baierbrunn_<Monat><Jahr>_Datenblatt.pdf`
  (z. B. `output/S7_Baierbrunn_Juni2026_Datenblatt.pdf`)
- `output/S7_Baierbrunn_<Monat><Jahr>_Schulweg.pdf`
  (z. B. `output/S7_Baierbrunn_Juni2026_Schulweg.pdf`)

`schulweg.py` laeuft im Standardablauf und im Workflow immer **nach**
`generate.py`, nie davor.

Danach:

```bash
git add output/
git commit -m "Datenblaetter <Monat> <Jahr>"
git push
```

## Feste Vorlage: Monatsdatenblatt (unveraenderlich)

**Position der Elemente, Art der Elemente und Farbgebung sind fix. Von Monat zu
Monat aendern sich ausschliesslich die Daten (Zahlen, Monatsname).** Das
Schulweg-Datenblatt hat eine eigene, ebenso feste Vorlage - siehe Abschnitt
"Schulweg-Datenblatt" weiter unten.

Das Layout ist datenunabhaengig: Jeder Monat rendert mit exakt derselben
Elementanordnung, denselben Element-Typen (Donut, Balkenhistogramm, Richtungs-
Kacheln, Zielbahnhof-Balken, Vergleichsbalken, Sparkline) und denselben Farben.
Bestaetigt: Mai/Juni/Juli 2026 ergeben alle die identische Layouthoehe.

Du darfst daher **nicht** veraendern:
- die Praesentationsfunktionen `render_html`, `donut`, `histogram`,
  `sparkline`, `calc_bars`, `dircard`,
- den `css`-Block (Positionen, Groessen, Abstaende),
- die Farbwerte / Farbpaletten (z. B. `#2e9e5b`, `#f0902f`, `#1b4f8a`,
  `palette` im Histogramm, die Ampelfarben der Zielbahnhof-Kacheln),
- Reihenfolge, Anzahl oder Typ der Kacheln/Diagramme.

Erlaubt ist nur, **die Daten** einzusetzen (macht `generate.py` automatisch) und
- ausschliesslich bei einer echten Upstream-Schema-Aenderung - die
Datenaufbereitung (`load_month`, `compute_stats`) anzupassen, damit die
**gleichen** Kennzahlen wie bisher befuellt werden. Die Darstellung bleibt dabei
unangetastet.

## Verifikation vor dem Commit

- Das Skript gibt eine Zusammenfassung aus (Verfuegbarkeit, Puenktlichkeit,
  Ø Verspaetung, Ziel erreicht). Diese Werte muessen plausibel sein
  (Verfuegbarkeit typischerweise 94-98 %, Ø Verspaetung ~3-5 Min.).
- Das Ergebnis muss **eine A4-Seite** sein. Das ist durch die feste Vorlage
  gewaehrleistet.
- Sollte wider Erwarten die Warnung `Inhalt ...px > eine A4-Seite` erscheinen,
  ist das **kein** Anlass, das Layout, Abstaende oder Farben zu aendern - das
  wuerde die feste Vorlage verletzen. Behandle es als Anomalie: pruefe, ob die
  Daten ungewoehnlich sind (z. B. falscher/ nicht finalisierter Monat), und
  **committe nicht**. Melde den Fall, statt das Design anzupassen.
- Wenn `WARNUNG: <Monat> ist noch nicht finalisiert` erscheint, wurde ein
  laufender Monat gewaehlt. Fuer den regulaeren Monatslauf ist das ein Fehler -
  pruefe, ob wirklich der Vormonat verarbeitet wird.

## Datenquelle & Schema

- Quelle: `https://github.com/s7bb/s7bb-data`, Datei
  `archive/<YYYY-MM>.json` (roh ueber `raw.githubusercontent.com`).
- Relevante Felder je Ankunft:
  - `cancelled` (bool) - Fahrt am Bahnhof Baierbrunn ausgefallen.
  - `delay_minutes` (float) - Ankunftsverspaetung in Minuten (leer bei Ausfall).
  - `direction_bucket` - `muenchen` | `wolfratshausen` | `unknown`.
  - `terminus_status` - `arrived` | `short_turn` | `cancelled` | `pending`
    (fehlt in aelteren Monaten).
  - `scheduled_time` (ISO, UTC) - wird nach `Europe/Berlin` umgerechnet.

## Fachliche Definitionen (in `generate.py` umgesetzt - nicht abweichen)

- **Verfuegbarkeit** = durchgefuehrte Fahrten / geplante Fahrten.
- **Puenktlich** = Ankunftsverspaetung ≤ 0 Min. Zusaetzlich ausgewiesen:
  Anteile < 5 / > 5 / > 15 Min. sowie p90.
- **Zielbahnhof erreicht** = `terminus_status == arrived`. Nicht erreicht =
  `short_turn` (vorzeitig gewendet) + `cancelled` (unterwegs ausgefallen).
- **Ausfaelle als Verspaetung** - drei Varianten nebeneinander:
  1. *Basiswert*: Ausfaelle ausgeschlossen.
  2. *Pauschal 20 Min.* je Ausfall.
  3. *Fahrplanbasierte Luecke*: tatsaechliche Luecke bis zur naechsten S-Bahn
     gleicher Richtung; fuer die **letzte Fahrt des Betriebstags** eine Taktluecke
     (20 Min.) statt des leeren Nachtfensters 02:00-04:40. Dies ist der
     empfohlene Wert.

## Konventionen (verbindlich)

- **Sprache: Deutsch.** Alle Beschriftungen, Ueberschriften und Fliesstexte.
- **Deutsche Zahlen:** Tausenderpunkt (`2.913`), Dezimalkomma (`3,18`). Dafuer
  die Helfer `dth()` und `dn()` in `generate.py` verwenden.
- **Keine Geviertstriche (em-dash `—`).** Fuer Bereiche ist der Halbgeviertstrich
  (`–`, z. B. Zeitspannen) in Ordnung.
- **Eine A4-Seite.** Nie mehrseitig.
- **Dateiname:** `S7_Baierbrunn_<Monat><Jahr>_Datenblatt.pdf` (Monatsdatenblatt)
  bzw. `S7_Baierbrunn_<Monat><Jahr>_Schulweg.pdf` (Schulweg-Datenblatt), Monat
  ausgeschrieben, `Maerz` statt `März` im Dateinamen.

## Caveats

- **Aeltere Monate (vor Juni 2026)** koennen ein schlankeres Schema ohne
  `terminus_status` haben. Dann ist die Zielbahnhof-Kachel nicht aussagekraeftig
  (viele `arrived`-Werte fehlen und wandern in "kein Zielergebnis erfasst").
  Fuer den laufenden Monatsbetrieb ist das unkritisch, da aktuelle Monate das
  vollstaendige Schema haben.
- Aendert sich das Upstream-Schema (neue/umbenannte Felder), passe **nur die
  Datenaufbereitung** (`load_month`, `compute_stats`) in `generate.py` an, damit
  dieselben Kennzahlen wie bisher entstehen. Die Darstellung (Layout, Positionen,
  Elementtypen, Farben) bleibt unveraendert. Keine Zahlen im PDF haendisch
  korrigieren.

## Schulweg-Datenblatt

Zusaetzlich zum Monatsdatenblatt erzeugt `schulweg.py` ein zweites,
eigenstaendiges DIN-A4-PDF: den Morgenverkehr **Mo-Fr 06:30-08:30**, beide
Richtungen (Muenchen und Wolfratshausen), aufgeschluesselt je einzelner Fahrt
(Slot). Es beantwortet, wie zuverlaessig die S7 in dem Zeitfenster ist, in dem
Schulkinder typischerweise unterwegs sind - getrennt von der Gesamtmonats-
Kennzahl, die auch verkehrsarme Naechte und Wochenenden mittelt.

`schulweg.py` laeuft im Standardablauf und im Workflow immer **nach**
`generate.py`, nie davor.

### Feste Vorlage: Schulweg-Datenblatt (unveraenderlich)

Seit Abschluss von Task 6 des Implementierungsplans gilt hier dasselbe
Prinzip wie beim Monatsdatenblatt: **Position der Elemente, Art der Elemente
und Farbgebung sind fix. Von Monat zu Monat aendern sich ausschliesslich die
Daten.**

Du darfst daher **nicht** veraendern:
- die Praesentationsfunktionen `kpi_strip`, `slot_grid`, `school_spark`,
  `render_html_schulweg`,
- den `CSS`-Block in `schulweg.py` (Positionen, Groessen, Abstaende),
- die Farbwerte (z. B. `#2e9e5b`, `#f0902f`, `#c8371f`, `#1b4f8a`),
- Reihenfolge, Anzahl oder Typ der drei Karten (Kennzahlen-Vergleich
  Fenster/Monat, Slot-Raster je Fahrt, Tages-Sparkline).

Erlaubt ist nur, **die Daten** einzusetzen (macht `schulweg.py` automatisch)
und - ausschliesslich bei einer echten Upstream-Schema-Aenderung - die
Datenaufbereitung (`tage_im_monat`, `compute_schulweg`, `kennzahlen`)
anzupassen, damit die **gleichen** Kennzahlen wie bisher befuellt werden. Die
Darstellung bleibt dabei unangetastet.

### Ferien-Quellen

Schultage werden aus den bayerischen Schulferien abgeleitet:
1. **OpenHolidays API** (`openholidaysapi.org`) wird zuerst abgefragt.
2. Schlaegt die Abfrage fehl oder liefert sie eine unplausible Antwort
   (weniger als `MIN_FERIEN_PRO_JAHR` Zeitraeume), faellt das Skript auf die
   in `schulweg.py` hinterlegte `FERIEN`-Tabelle zurueck.

Die Fusszeile des PDFs nennt immer, welche der beiden Quellen tatsaechlich
verwendet wurde. Die Tabelle wird **nie von Hand bearbeitet**, sondern mit
`python tools/refresh_ferien.py --von <YYYY-MM-DD> --bis <YYYY-MM-DD>` neu
erzeugt; deren Ausgabe ersetzt den `FERIEN`-Block in `schulweg.py`.

### `FERIEN`-Wartung

`FERIEN_ABGEDECKT` markiert den Zeitraum, den die hinterlegte Tabelle
abdeckt (aktuell bis **2028-01-31**). Erneuere die Tabelle mit
`tools/refresh_ferien.py`, bevor dieses Datum erreicht wird. Liegt der
Berichtsmonat ausserhalb von `FERIEN_ABGEDECKT`, bricht der Lauf **nur dann**
ab, wenn zusaetzlich die OpenHolidays-API nicht erreichbar ist - diese
Kombination ist beabsichtigt: Solange die API antwortet, braucht es die
Tabelle gar nicht.

### Werktage-Fallback

Enthaelt ein Berichtsmonat keine Schultage (reiner Ferienmonat), verwendet
`schulweg.py` ersatzweise alle Werktage (Mo-Fr) des Monats und weist das im
PDF sichtbar aus (Kopfzeile und Kartentext).

## Was du NICHT tun sollst

- Keine Kennzahlen frei erfinden, runden oder aus dem Gedaechtnis ergaenzen.
- **Layout, Positionen, Elementtypen oder Farben nicht veraendern** (siehe
  "Feste Vorlage: Monatsdatenblatt" und "Feste Vorlage: Schulweg-Datenblatt").
  Praesentationsfunktionen, `css`/`CSS`-Bloecke und Farbwerte sind in beiden
  Datenblaettern tabu.
- Nur `output/`, `schulweg.py` und - ausschliesslich bei
  Schema-Aenderungen - die Datenaufbereitung in `generate.py` aendern.
- Keine externen Netzwerkziele ausser `raw.githubusercontent.com/s7bb/...`
  und `openholidaysapi.org` ansprechen. Ein Ausfall von `openholidaysapi.org`
  ist **absichtlich unkritisch**: `schulweg.py` faellt automatisch auf die
  hinterlegte `FERIEN`-Tabelle zurueck, und die Fusszeile des PDFs nennt
  immer, welche Quelle tatsaechlich verwendet wurde.
