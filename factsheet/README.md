# S7 Baierbrunn - Monatsdatenblatt & Schulweg-Datenblatt

Erzeugt monatlich zwei einseitige DIN-A4-PDFs zur Betriebsqualitaet der S-Bahn
**S7** am Bahnhof **Baierbrunn**: Verfuegbarkeit, Puenktlichkeit, Zielbahnhof-
Erreichbarkeit und der Effekt, wenn Ausfaelle als Verspaetung gewertet werden -
einmal fuer den Gesamtmonat (`generate.py`) und einmal fuer den Morgenverkehr
Mo-Fr 06:30-08:30 (`schulweg.py`).

Datenquelle: [github.com/s7bb/s7bb-data](https://github.com/s7bb/s7bb-data).

## Struktur

Im Repo unter `factsheet/`, der Workflow liegt an der Repo-Wurzel
(GitHub Actions erkennt Workflows nur unter `.github/workflows/`):

```
<repo-root>/
├── .github/workflows/monthly-factsheet.yml   # Workflow (arbeitet in factsheet/)
└── factsheet/
    ├── CLAUDE.md                              # Betriebsanleitung fuer Claude Code
    ├── generate.py                            # deterministischer PDF-Generator (Monatsdatenblatt)
    ├── schulweg.py                            # deterministischer PDF-Generator (Schulweg-Datenblatt)
    ├── tools/refresh_ferien.py                # erneuert die FERIEN-Tabelle aus der OpenHolidays-API
    ├── requirements.txt
    ├── requirements-dev.txt                   # zusaetzlich: pytest, fuer die Tests
    ├── pytest.ini
    ├── tests/                                 # Offline-Tests (Kalender, Slots, Kennzahlen, HTML)
    ├── README.md
    └── output/                               # erzeugte PDFs (vom Workflow committet)
```

## Lokal ausfuehren

Aus dem Verzeichnis `factsheet/`:

```bash
cd factsheet
pip install -r requirements.txt
python -m playwright install --with-deps chromium

python generate.py                 # Monatsdatenblatt, Vormonat
python generate.py --month 2026-06 # bestimmter Monat (Backfill)

python schulweg.py                 # Schulweg-Datenblatt, Vormonat
python schulweg.py --month 2026-06 # bestimmter Monat (Backfill)
```

Ergebnis:
- `output/S7_Baierbrunn_<Monat><Jahr>_Datenblatt.pdf` (Monatsdatenblatt)
- `output/S7_Baierbrunn_<Monat><Jahr>_Schulweg.pdf` (Schulweg-Datenblatt)

Beide Skripte sind eigenstaendig und benoetigen kein LLM; `schulweg.py`
importiert seine Datengrundlage aus `generate.py` und laeuft immer nach ihm.
Der CI-Lauf ruft die Skripte direkt auf; es gibt keine KI/Model-Abhaengigkeit
im Erzeugungspfad.

## Automatischer Monatslauf

Der Workflow `.github/workflows/monthly-factsheet.yml` (an der Repo-Wurzel):

- laeuft am **1. jedes Monats um 12:00 UTC** (Cron `0 12 1 * *`) fuer den
  Vormonat und laesst sich ueber **"Run workflow"** manuell mit optionalem Monat
  starten;
- installiert Python-Abhaengigkeiten und Chromium;
- fuehrt `python generate.py` gefolgt von `python schulweg.py` im Verzeichnis
  `factsheet/` aus (leerer Monat = Vormonat, sonst der angegebene Monat fuer
  beide Skripte);
- veroeffentlicht die beiden erzeugten PDFs (Monatsdatenblatt und
  Schulweg-Datenblatt) gemeinsam als ein **GitHub-Release** mit Tag `MM.YYYY`
  (z. B. `07.2026`). Bei erneutem Lauf fuer denselben Monat werden die PDFs im
  bestehenden Release ersetzt.

### Einrichtung

1. Sicherstellen, dass Actions Schreibrechte haben
   (Settings → Actions → General → Workflow permissions → *Read and write*).
   Der Workflow setzt dazu bereits `permissions: contents: write`.

Kein API-Key noetig - der Workflow verwendet kein LLM.

### Hinweise

- Der Erzeugungspfad ist rein deterministisch (pandas + Playwright/Chromium).
  Externe Netzwerkquellen: `raw.githubusercontent.com/s7bb/s7bb-data`
  (statische Monats-JSON, beide Skripte) und `openholidaysapi.org`
  (bayerische Schulferien, nur `schulweg.py`). Ist Letztere nicht erreichbar,
  faellt `schulweg.py` auf die im Skript hinterlegte `FERIEN`-Tabelle zurueck -
  das ist kein Fehler, sondern das vorgesehene Verhalten; die Fusszeile des
  PDFs nennt die tatsaechlich verwendete Quelle.
- Das Release wird ueber `gh release` mit dem automatisch bereitgestellten
  `GITHUB_TOKEN` angelegt; kein zusaetzliches Secret noetig.
- **Finalisierungs-Guard:** Ist der Berichtsmonat upstream noch nicht als
  `finalized` markiert (oder ueberschreitet der Inhalt eine A4-Seite), bricht der
  Lauf mit Fehler ab und veroeffentlicht **kein** Release. Bei Bedarf spaeter
  erneut anstossen, sobald der Vormonat finalisiert ist.

## Tests

```bash
cd factsheet
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

Die Tests decken Kalender, Slot-Zuordnung, Kennzahlen und HTML-Aufbau ab; sie
gehen nicht ins Netz. Das PDF-Rendering wird ueber die Seitenhoehenpruefung in
`render_pdf` verifiziert.

Details zu Definitionen, Konventionen und Sonderfaellen: siehe `CLAUDE.md`.
