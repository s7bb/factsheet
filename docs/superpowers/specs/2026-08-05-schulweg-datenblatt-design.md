# Schulweg-Datenblatt — Design

Date: 2026-08-05
Issue: [#1 — Detailed information for students in direction Wolfratshausen](https://github.com/s7bb/factsheet/issues/1)
Status: approved, ready for implementation planning

## Problem

Issue #1 asks for a data point covering the morning commute:

> Besonders kritisch ist die Verfügbarkeit und Pünktlichkeit der S-Bahn am
> Morgen für den Weg zur Schule / Arbeit. Ist es möglich, die Daten für die Zeit
> von 6:30 Uhr bis 8:30 Uhr zu extrahieren?

The existing monthly one-pager reports whole-month, all-hours, both-directions
figures. A parent deciding which train their child should take cannot answer
"which morning train is unreliable?" from it.

The window carries real signal. July 2026, → Wolfratshausen, Mo–Fr 06:30–08:30:
the 08:00 train averaged 9,50 minutes late and was cancelled on 3 of 23 school
days, while the 07:00 train averaged 2,91 minutes with 1 cancellation. That
spread is invisible in the monthly aggregate.

## Constraint that shapes the solution

`factsheet/CLAUDE.md` freezes the page-1 template: element position, type,
count, order and colour are fixed, and the sheet must always be exactly one A4
page. Adding a card to it would require unfreezing and re-freezing the template
and re-verifying every month.

**Decision: the morning data lives in a separate PDF.** `generate.py` and its
output are not touched at all. The new sheet gets its own layout, its own freeze
declaration, and full room for the per-departure detail.

## Scope

- Scheduled **arrival** at Baierbrunn between 06:30 and 08:30 local time.
- **Mon–Fri only.** Weekends are not school days and their better figures would
  dilute the signal.
- **Both directions** (`wolfratshausen` and `muenchen`). The original request
  names "Schule / Arbeit": the school run goes south toward Icking and
  Wolfratshausen, the work run goes north toward München. Both are commutes.
- Sample size: 6 trains per direction per school day, ~138 arrivals per
  direction per month, ~23 per departure slot.

### Wording: arrival, not departure

`s7bb-data` records arrivals at Baierbrunn. For a passenger boarding there the
two differ by seconds, but the sheet must describe what it measures. All labels
say *Ankunft*; the grid heading is
`Je Fahrt · planmäßige Ankunft in Baierbrunn`. Do not label these "Abfahrt".

### Comparison must stay neutral

Page 1 hardcodes an interpretive sentence ("Züge Richtung Wolfratshausen sind im
Schnitt später und seltener pünktlich als Richtung München"). The Schulweg sheet
must **not** do this. July 2026 shows why: → Wolfratshausen in the morning window
is worse than the month on availability (90,6% vs 95,1%) but *better* on average
delay (5,39 vs 6,24 Min.). The direction of the peak-vs-month gap changes by
metric and by month. The sheet presents both numbers and lets the reader compare;
it carries no fixed claim about which is worse.

## Metrics

Computed per direction, once for the window and once as a month-wide reference:

| Metric | Definition |
| --- | --- |
| Verfügbarkeit | durchgeführte / geplante Fahrten |
| pünktlich | Ankunftsverspätung ≤ 0 Min. |
| Ø Verspätung | Mittel über durchgeführte Fahrten, Ausfälle ausgeschlossen |
| Anteil > 5 Min. | Anteil der durchgeführten Fahrten mit Verspätung > 5 Min. |
| p90 | 90. Perzentil der Verspätung, durchgeführte Fahrten |

**Reference values are whole-month, all days, all hours, per direction** — the
same basis as the page-1 "Nach Richtung" card. This is deliberate, so a reader
can hold the two PDFs side by side and cross-check:

- `pünktlich` and `Ø Verspätung` must match the page-1 dircard values exactly.
- `Verfügbarkeit` is 100 % minus the dircard's `ausgefallen` value.
- `> 5 Min.` and `p90` have no per-direction counterpart on page 1; they are new
  and cannot be cross-checked. That is acceptable — they are the metrics that
  move most between months.

`schulweg.py` computes everything from the raw DataFrame. It does **not** call
`compute_stats`, so page-1 metric logic has no new caller and cannot be
destabilised by this change.

### Dropped: Zielbahnhof-Erreichbarkeit

`terminus_status` short-turns are near-zero inside the morning window: 6 in June
2026 (all → München), 0 in July 2026. A card that always reads ~100% is dead
weight. Excluded.

## Slot bucketing

This is the load-bearing part of the design.

Grouping on the raw `HH:MM` string is not stable. May 2026 splits a single train
across three scheduled times:

```
06:39  n= 2      06:59  n= 3      07:19  n= 3
06:40  n=12      07:00  n=14      07:20  n=13
06:41  n= 1      07:01  n= 1      07:21  n= 1
```

May would render 18 rows where June and July render 6. A fixed-layout sheet
cannot survive that.

**Six fixed 20-minute buckets anchored at 06:30:**

```
0: [06:30, 06:50)    3: [07:30, 07:50)
1: [06:50, 07:10)    4: [07:50, 08:10)
2: [07:10, 07:30)    5: [08:10, 08:30]
```

The last bucket is closed so an 08:30 arrival is included.

**Row label** = the modal scheduled `HH:MM` within the bucket, taken across both
directions combined. In every month inspected (May, June, July 2026) the two
directions cross at Baierbrunn on the same minute, so one label per row is
correct. Ties resolve to the earlier time for determinism.

**Empty bucket** renders as a normal row with a `–` label, zero-width bar and
`0` counts. The row count is always exactly 6, whatever the data does.

## Layout

One A4 page. Colours and type reuse `generate.py`'s palette (`#1b4f8a`,
`#2e9e5b`, `#f0902f`, `#c8371f`) so the two sheets read as one family.

```
┌──────────────────────────────────────────────────────────┐
│ S7 │ S-Bahn S7 · Baierbrunn · Schulweg      Juli 2026    │
│    │ Mo–Fr 06:30–08:30 · Ankünfte           23 Schultage │
├──────────────────────────────────────────────────────────┤
│ MORGENVERKEHR IM VERGLEICH ZUM GESAMTMONAT               │
│                    → Wolfratshausen      → München       │
│  Verfügbarkeit       90,6%  (95,1)      94,2%  (94,9)    │
│  pünktlich            5,6%   (6,0)      12,3%  (14,2)    │
│  Ø Verspätung         5,39   (6,24)      3,32   (3,60)   │
│  > 5 Min.            33,6%  (35,3)      16,9%  (17,1)    │
│  p90                    12     (15)         7      (8)   │
├──────────────────────────────────────────────────────────┤
│ JE FAHRT · PLANMÄSSIGE ANKUNFT IN BAIERBRUNN             │
│              → Wolfratshausen        → München           │
│  06:40   ████░░░░░░  4,05  1 Ausf.  ███░░░░░░░  2,52     │
│  07:00   ███░░░░░░░  2,91  1 Ausf.  ███░░░░░░░  2,48 2 A.│
│  07:20   ████░░░░░░  3,75  3 Ausf.  ████░░░░░░  3,45 1 A.│
│  07:40   ██████░░░░  5,86  2 Ausf.  ████░░░░░░  3,48 2 A.│
│  08:00   ██████████  9,50  3 Ausf.  ████░░░░░░  3,95 1 A.│
│  08:20   ███████░░░  6,65  3 Ausf.  ████░░░░░░  4,10 2 A.│
├──────────────────────────────────────────────────────────┤
│ Ø VERSPÄTUNG JE SCHULTAG (MIN.)                          │
│   (weekday-only line, 22–23 points)                      │
└──────────────────────────────────────────────────────────┘
```

Numbers shown are the real July 2026 values.

Three blocks:

1. **KPI strip** — two direction columns, five metric rows, month-wide reference
   in parentheses after each window value.
2. **Slot grid** — 6 rows × 2 directions. Each cell: a horizontal bar scaled to
   Ø Verspätung (shared scale across both directions so they are comparable),
   the value, and a cancellation count. Bar scale is normalised to the largest
   value in the grid.
3. **Ø Verspätung je Schultag** — weekday-only line across the month. Reuses
   `sparkline()` imported unchanged from `generate.py`.

Footnote states the per-slot sample size (~23 arrivals per slot per month) so a
single bad slot is not over-read, plus the standard source line.

## Code structure

```
factsheet/
  generate.py    UNCHANGED — frozen page-1 sheet
  schulweg.py    new, ~250 lines
```

`schulweg.py` imports from `generate.py` and edits nothing:

```python
from generate import (load_month, dth, dn, render_pdf, sparkline,
                      MONATE, MONATE_DATEI, TZ)
```

Own functions:

| Function | Responsibility |
| --- | --- |
| `bucket_of(local_dt)` | minute-of-day → slot index 0–5, or `None` |
| `compute_schulweg(df)` | window + month-wide stats per direction, slot table, daily series |
| `kpi_strip(s)` | HTML for block 1 |
| `slot_grid(s)` | HTML/SVG for block 2 |
| `render_html_schulweg(s, ...)` | assembles the page |
| `main()` | CLI: `--month YYYY-MM`, `--outdir output` |

Importing frozen presentation functions is read-only use and does not violate
the template freeze. `generate.py` guards its entry point with
`if __name__ == "__main__"`, so importing it has no side effects.

Output: `output/S7_Baierbrunn_<Monat><Jahr>_Schulweg.pdf`, using `MONATE_DATEI`
so March is `Maerz`.

Conventions inherited from `factsheet/CLAUDE.md`: German throughout, `dth()` and
`dn()` for all numbers, no em dashes (`–` is fine for ranges), exactly one A4
page.

## Workflow and documentation

`.github/workflows/monthly-factsheet.yml`:

- Add a second generate step, `python schulweg.py [--month ...]`, appending to
  the same `gen.log`. Both existing guards then cover the new sheet with no
  change to their logic: the not-finalized guard greps
  `noch nicht finalisiert`, the layout guard greps `> eine A4-Seite`, and
  `render_pdf` already emits the latter.
- The `PDF=$(grep -oE 'output/[^ ]+\.pdf' gen.log | head -n1)` line currently
  takes the first match only. It must collect both paths and pass both to
  `gh release create` / `gh release upload` on the same `MM.YYYY` tag.

Docs:

- `factsheet/CLAUDE.md` gains a Schulweg section with its own freeze
  declaration, mirroring the page-1 rules.
- Root `README.md` notes that each release now carries two PDFs.

## Verification

1. Generate for **2026-05**, **2026-06** and **2026-07**.
2. Each must render exactly one A4 page — no `> eine A4-Seite` warning.
3. **2026-05 must produce exactly 6 slot rows** despite its ±1 minute schedule
   drift. This is the regression test for the bucketing and the reason May is in
   the list.
4. Spot-check July against the values in this document: → Wolfratshausen window
   availability 90,6%, Ø 5,39 Min., 08:00 slot Ø 9,50 Min. with 3 cancellations.
5. Confirm `generate.py` output is byte-identical before and after the change.

## Out of scope

- Any change to the page-1 template or to `generate.py`.
- Zielbahnhof-Erreichbarkeit for the window (see above).
- Named worst-morning callouts.
- An afternoon / return-journey window.
