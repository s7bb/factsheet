# CLAUDE.md - S7 Baierbrunn Monatsdatenblatt

Dieses Repo erzeugt jeden Monat ein einseitiges DIN-A4-PDF-Datenblatt zur
Betriebsqualitaet der S-Bahn-Linie **S7** am Bahnhof **Baierbrunn**.

## Aufgabe

Wenn du (Claude Code) in diesem Repo laeufst, ist dein Ziel:

1. Das Datenblatt fuer den **zuletzt abgeschlossenen Kalendermonat** (Vormonat)
   erzeugen.
2. Pruefen, dass das Ergebnis korrekt und einseitig ist.
3. Das PDF nach `output/` committen.

Der eigentliche Aufbau ist **deterministisch** und steckt in `generate.py`.
Du sollst die Zahlen **nicht selbst berechnen oder schaetzen** - immer das
Skript laufen lassen.

## Standardablauf

```bash
# Vormonat automatisch:
python generate.py

# oder expliziter Monat (Backfill):
python generate.py --month 2026-06
```

Das erzeugt `output/S7_Baierbrunn_<Monat><Jahr>_Datenblatt.pdf`
(z. B. `output/S7_Baierbrunn_Juni2026_Datenblatt.pdf`).

Danach:

```bash
git add output/
git commit -m "Datenblatt <Monat> <Jahr>"
git push
```

## Feste Vorlage (unveraenderlich)

**Position der Elemente, Art der Elemente und Farbgebung sind fix. Von Monat zu
Monat aendern sich ausschliesslich die Daten (Zahlen, Monatsname).**

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
- **Dateiname:** `S7_Baierbrunn_<Monat><Jahr>_Datenblatt.pdf`, Monat
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

## Was du NICHT tun sollst

- Keine Kennzahlen frei erfinden, runden oder aus dem Gedaechtnis ergaenzen.
- **Layout, Positionen, Elementtypen oder Farben nicht veraendern** (siehe
  "Feste Vorlage"). Praesentationsfunktionen, `css`-Block und Farbwerte sind tabu.
- Nur `output/` und - ausschliesslich bei Schema-Aenderungen - die
  Datenaufbereitung in `generate.py` aendern.
- Keine externen Netzwerkziele ausser `raw.githubusercontent.com/s7bb/...`
  ansprechen.
