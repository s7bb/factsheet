# S7 Baierbrunn - Monatsdatenblatt

Erzeugt monatlich ein einseitiges DIN-A4-PDF zur Betriebsqualitaet der S-Bahn
**S7** am Bahnhof **Baierbrunn**: Verfuegbarkeit, Puenktlichkeit, Zielbahnhof-
Erreichbarkeit und der Effekt, wenn Ausfaelle als Verspaetung gewertet werden.

Datenquelle: [github.com/s7bb/s7bb-data](https://github.com/s7bb/s7bb-data).

## Struktur

Im Repo unter `factsheet/`, der Workflow liegt an der Repo-Wurzel
(GitHub Actions erkennt Workflows nur unter `.github/workflows/`):

```
<repo-root>/
├── .github/workflows/monthly-factsheet.yml   # Workflow (arbeitet in factsheet/)
└── factsheet/
    ├── CLAUDE.md                              # Betriebsanleitung fuer Claude Code
    ├── generate.py                           # deterministischer PDF-Generator
    ├── requirements.txt
    ├── README.md
    └── output/                               # erzeugte PDFs (vom Workflow committet)
```

## Lokal ausfuehren

Aus dem Verzeichnis `factsheet/`:

```bash
cd factsheet
pip install -r requirements.txt
python -m playwright install --with-deps chromium

python generate.py                 # Vormonat
python generate.py --month 2026-06 # bestimmter Monat (Backfill)
```

Ergebnis: `output/S7_Baierbrunn_<Monat><Jahr>_Datenblatt.pdf`.

`generate.py` ist eigenstaendig und benoetigt kein LLM. Der CI-Lauf ruft das
Skript direkt auf; es gibt keine KI/Model-Abhaengigkeit im Erzeugungspfad.

## Automatischer Monatslauf

Der Workflow `.github/workflows/monthly-factsheet.yml` (an der Repo-Wurzel):

- laeuft am **1. jedes Monats um 12:00 UTC** (Cron `0 12 1 * *`) fuer den
  Vormonat und laesst sich ueber **"Run workflow"** manuell mit optionalem Monat
  starten;
- installiert Python-Abhaengigkeiten und Chromium;
- fuehrt `python generate.py` im Verzeichnis `factsheet/` aus (leerer Monat =
  Vormonat, sonst der angegebene Monat);
- veroeffentlicht das erzeugte PDF als **GitHub-Release** mit Tag `MM.YYYY`
  (z. B. `07.2026`). Bei erneutem Lauf fuer denselben Monat wird das PDF im
  bestehenden Release ersetzt.

### Einrichtung

1. Sicherstellen, dass Actions Schreibrechte haben
   (Settings → Actions → General → Workflow permissions → *Read and write*).
   Der Workflow setzt dazu bereits `permissions: contents: write`.

Kein API-Key noetig - der Workflow verwendet kein LLM.

### Hinweise

- Der Erzeugungspfad ist rein deterministisch (pandas + Playwright/Chromium).
  Einzige externe Netzwerkquelle: `raw.githubusercontent.com/s7bb/s7bb-data`
  (statische Monats-JSON).
- Das Release wird ueber `gh release` mit dem automatisch bereitgestellten
  `GITHUB_TOKEN` angelegt; kein zusaetzliches Secret noetig.

Details zu Definitionen, Konventionen und Sonderfaellen: siehe `CLAUDE.md`.
