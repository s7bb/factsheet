# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo does

Generates two one-page DIN-A4 PDF factsheets (German) each month on the
operational quality of the S-Bahn **S7** at station **Baierbrunn**: the
Monatsdatenblatt (whole month: availability, punctuality,
destination-reachability, and the effect of counting cancellations as delay)
and the Schulweg-Datenblatt (morning commute Mon-Fri 06:30-08:30, both
directions, per departure).

All output is in German. Number formatting is German (thousands `.`, decimal `,`).

## Layout

```
<repo-root>/
├── .github/workflows/monthly-factsheet.yml   # monthly cron + manual dispatch (runs inside factsheet/)
└── factsheet/
    ├── CLAUDE.md          # detailed operational rules - READ THIS before generating a factsheet
    ├── generate.py        # deterministic PDF generator, Monatsdatenblatt (single file, no LLM)
    ├── schulweg.py        # deterministic PDF generator, Schulweg-Datenblatt (reuses generate.py)
    ├── tools/
    │   └── refresh_ferien.py   # regenerates the FERIEN table from the OpenHolidays API
    ├── requirements.txt
    ├── requirements-dev.txt    # requirements.txt plus pytest
    ├── pytest.ini
    ├── tests/             # offline pytest suite (calendar, slots, metrics, HTML)
    └── output/            # generated PDFs (gitignored, published as release assets)
```

The workflow lives at the repo root because GitHub Actions only detects
workflows under `.github/workflows/`. Everything else lives in `factsheet/`.

## Commands

Run from `factsheet/`:

```bash
cd factsheet
pip install -r requirements.txt
python -m playwright install --with-deps chromium   # one-time: Chromium for PDF render

python generate.py                  # Monatsdatenblatt, previous month (default)
python generate.py --month 2026-06  # specific month (backfill)
python generate.py --outdir output  # output dir (default: output)

python schulweg.py                  # Schulweg-Datenblatt, previous month (default)
python schulweg.py --month 2026-06  # specific month (backfill)

pip install -r requirements-dev.txt
python -m pytest tests/ -v          # test suite; 1 test is marked "network"
                                     # (hits openholidaysapi.org) - skip it with
                                     # -m "not network" for an offline run
```

Output: `output/S7_Baierbrunn_<Monat><Jahr>_Datenblatt.pdf` (Monatsdatenblatt)
and `output/S7_Baierbrunn_<Monat><Jahr>_Schulweg.pdf` (Schulweg-Datenblatt).

## Architecture

`generate.py` is a self-contained pipeline, no LLM in the compute path:

1. **`load_month`** - fetches `archive/<YYYY-MM>.json` from the `s7bb/s7bb-data`
   repo via `raw.githubusercontent.com`, into a pandas DataFrame. Times UTC →
   `Europe/Berlin`. Defensively backfills columns older months lack
   (`terminus_status`, `direction_bucket`, `delay_minutes`, `cancelled`).
2. **`compute_stats`** - all business metrics (availability, punctuality
   buckets, per-direction, delay histogram, daily averages, and three
   "cancellation-as-delay" variants). `service_aware_avg` is the recommended
   variant: penalty per cancellation = timetable gap to next same-direction train.
3. **SVG builders** (`donut`, `histogram`, `sparkline`, `calc_bars`, `dircard`) +
   **`render_html`** - assemble a fixed HTML/CSS template.
4. **`render_pdf`** - Playwright/Chromium renders HTML → A4 PDF, warns if content
   exceeds one page (1123px @ 96dpi).

`dth()` (integer, thousands dot) and `dn()` (decimal comma) are the German
number formatters - always use them, never format numbers inline.

`schulweg.py` is a second, independent pipeline for the Schulweg-Datenblatt.
It imports `MONATE`, `MONATE_DATEI`, `TZ`, `dn`, `load_month`, `prev_month`,
and `render_pdf` from `generate.py` and reuses them unchanged, but adds its
own: a Bavarian public/school-holiday calendar (`easter`, `feiertage`,
`ferien_api`/`ferien_ranges` against the OpenHolidays API with a committed
`FERIEN` table as fallback, `tage_im_monat`), data-derived slot bucketing for
the 06:30-08:30 morning window (`slot_centres`, `assign_slot`), its own
metrics (`kennzahlen`, `compute_schulweg`), and its own HTML/CSS template
(`kpi_strip`, `slot_grid`, `school_spark`, `render_html_schulweg`). It does
not read or write anything else in `generate.py`.

## Critical constraint: the templates are frozen

**Only the data changes month to month.** This now covers *two* templates -
`generate.py`'s Monatsdatenblatt and `schulweg.py`'s Schulweg-Datenblatt -
each frozen independently. Element position, type, and color are fixed for
each: every month must render the identical layout. Do **not** edit:

- `generate.py`'s presentation functions (`render_html`, `donut`,
  `histogram`, `sparkline`, `calc_bars`, `dircard`), its `css` block, its
  color values/palettes, or the order/count/type of its cards and charts;
- `schulweg.py`'s presentation functions (`kpi_strip`, `slot_grid`,
  `school_spark`, `render_html_schulweg`), its `CSS` block, its color
  values, or the order/count/type of its three cards.

The **only** permitted code change in either file is to its data layer
(`load_month`/`compute_stats` in `generate.py`; `tage_im_monat`/
`compute_schulweg`/`kennzahlen` in `schulweg.py`) - and only on a real
upstream schema change, to keep the *same* metrics populated. A
"content > one A4 page" warning is an anomaly (bad/non-finalized month),
never a reason to touch layout - investigate the data and do not commit.

**Schulweg work must not modify `generate.py` at all.** `schulweg.py` only
imports from it; any change to `generate.py`'s behavior is out of scope for
the Schulweg-Datenblatt and must be justified purely by the Monatsdatenblatt's
own rules above.

**Before generating or committing a factsheet, read `factsheet/CLAUDE.md`** -
it holds the full operational rules, field definitions, verification steps,
and conventions for both datasheets.
