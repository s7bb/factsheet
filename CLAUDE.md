# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo does

Generates a one-page DIN-A4 PDF factsheet (German) on the operational quality of
the S-Bahn **S7** at station **Baierbrunn**: availability, punctuality,
destination-reachability, and the effect of counting cancellations as delay.

All output is in German. Number formatting is German (thousands `.`, decimal `,`).

## Layout

```
<repo-root>/
├── .github/workflows/monthly-factsheet.yml   # monthly cron + manual dispatch (runs inside factsheet/)
└── factsheet/
    ├── CLAUDE.md        # detailed operational rules — READ THIS before generating a factsheet
    ├── generate.py      # deterministic PDF generator (single file, no LLM)
    ├── requirements.txt
    └── output/          # generated PDFs (committed by the workflow)
```

The workflow lives at the repo root because GitHub Actions only detects
workflows under `.github/workflows/`. Everything else lives in `factsheet/`.

## Commands

Run from `factsheet/`:

```bash
cd factsheet
pip install -r requirements.txt
python -m playwright install --with-deps chromium   # one-time: Chromium for PDF render

python generate.py                  # previous month (default)
python generate.py --month 2026-06  # specific month (backfill)
python generate.py --outdir output  # output dir (default: output)
```

Output: `output/S7_Baierbrunn_<Monat><Jahr>_Datenblatt.pdf`. No test suite.

## Architecture

`generate.py` is a self-contained pipeline, no LLM in the compute path:

1. **`load_month`** — fetches `archive/<YYYY-MM>.json` from the `s7bb/s7bb-data`
   repo via `raw.githubusercontent.com`, into a pandas DataFrame. Times UTC →
   `Europe/Berlin`. Defensively backfills columns older months lack
   (`terminus_status`, `direction_bucket`, `delay_minutes`, `cancelled`).
2. **`compute_stats`** — all business metrics (availability, punctuality
   buckets, per-direction, delay histogram, daily averages, and three
   "cancellation-as-delay" variants). `service_aware_avg` is the recommended
   variant: penalty per cancellation = timetable gap to next same-direction train.
3. **SVG builders** (`donut`, `histogram`, `sparkline`, `calc_bars`, `dircard`) +
   **`render_html`** — assemble a fixed HTML/CSS template.
4. **`render_pdf`** — Playwright/Chromium renders HTML → A4 PDF, warns if content
   exceeds one page (1123px @ 96dpi).

`dth()` (integer, thousands dot) and `dn()` (decimal comma) are the German
number formatters — always use them, never format numbers inline.

## Critical constraint: the template is frozen

**Only the data changes month to month.** Element position, type, and color are
fixed — every month must render the identical layout. Do **not** edit the
presentation functions (`render_html`, `donut`, `histogram`, `sparkline`,
`calc_bars`, `dircard`), the `css` block, the color values/palettes, or the
order/count/type of the cards and charts.

The **only** permitted code change is to the data layer (`load_month`,
`compute_stats`) — and only on a real upstream schema change, to keep the *same*
metrics populated. A "content > one A4 page" warning is an anomaly (bad/
non-finalized month), never a reason to touch layout — investigate the data and
do not commit.

**Before generating or committing a factsheet, read `factsheet/CLAUDE.md`** —
it holds the full operational rules, field definitions, verification steps, and
conventions.
