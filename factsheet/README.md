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

`generate.py` ist eigenstaendig und benoetigt kein LLM. Claude Code wird nur
verwendet, um den Lauf zu orchestrieren, das Ergebnis zu pruefen und zu
committen - und um sich anzupassen, falls sich das Upstream-Datenschema aendert.

## Automatischer Monatslauf

Der Workflow `.github/workflows/monthly-factsheet.yml` (an der Repo-Wurzel):

- laeuft am **2. jedes Monats** (Cron `0 6 2 * *`), wenn der Vormonat finalisiert
  ist, und laesst sich ueber **"Run workflow"** manuell mit optionalem Monat
  starten;
- installiert Python-Abhaengigkeiten, Chromium und Claude Code;
- fuehrt Claude Code headless im Verzeichnis `factsheet/` aus (`claude -p ...`),
  das gemaess `CLAUDE.md` `generate.py` startet, das Ergebnis prueft und nach
  `factsheet/output/` committet;
- sichert das PDF zusaetzlich als Build-Artefakt.

### Einrichtung

1. Repository-Secret **`ANTHROPIC_API_KEY`** hinterlegen
   (Settings → Secrets and variables → Actions), z. B.:
   ```bash
   gh secret set ANTHROPIC_API_KEY --body "sk-ant-..."
   ```
2. Sicherstellen, dass Actions Schreibrechte haben
   (Settings → Actions → General → Workflow permissions → *Read and write*).
   Der Workflow setzt dazu bereits `permissions: contents: write`.

### Hinweise

- In CI laeuft Claude Code mit `--dangerously-skip-permissions` (nicht-interaktiv)
  und `--max-turns 25` als Sicherheitsgrenze. Die Toolauswahl ist auf
  `Bash,Read,Write,Edit,Glob,Grep` eingeschraenkt.
- Alternativ zum CLI-Aufruf gibt es die offizielle Action
  `anthropics/claude-code-action@v1`; das obige Setup nutzt bewusst den bare-CLI
  fuer maximale Transparenz und Nachvollziehbarkeit im Cron-Kontext.
- Ein Commit-Fallback-Schritt committet das PDF auch dann, wenn Claude Code es
  selbst nicht getan hat.

Details zu Definitionen, Konventionen und Sonderfaellen: siehe `CLAUDE.md`.
