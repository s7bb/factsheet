# Schulweg-Datenblatt — Design

Date: 2026-08-05
Issue: [#1 — Detailed information for students in direction Wolfratshausen](https://github.com/s7bb/factsheet/issues/1)
Status: approved, revised after spec review, ready for implementation planning

## Problem

Issue #1 asks for a data point covering the morning commute:

> Besonders kritisch ist die Verfügbarkeit und Pünktlichkeit der S-Bahn am
> Morgen für den Weg zur Schule / Arbeit. Ist es möglich, die Daten für die Zeit
> von 6:30 Uhr bis 8:30 Uhr zu extrahieren?

The existing monthly one-pager reports whole-month, all-hours, both-directions
figures. A parent deciding which train their child should take cannot answer
"which morning train is unreliable?" from it.

The window carries real signal. July 2026, → Wolfratshausen: the 08:00 train
averaged 9,50 minutes late and was cancelled on 3 of 23 school days, while the
07:00 train averaged 2,91 minutes with 1 cancellation. That spread is invisible
in the monthly aggregate.

## Constraint that shapes the solution

`factsheet/CLAUDE.md` freezes the page-1 template: element position, type,
count, order and colour are fixed, and the sheet must always be exactly one A4
page. Adding a card to it would require unfreezing and re-freezing the template
and re-verifying every month.

**Decision: the morning data lives in a separate PDF.** `generate.py` and its
output are not touched. The new sheet gets its own layout, its own freeze
declaration, and full room for the per-departure detail.

Note that the presentation freeze is not the only rule in the way.
`factsheet/CLAUDE.md:136-137` says *"Nur `output/` und — ausschliesslich bei
Schema-Aenderungen — die Datenaufbereitung in `generate.py` aendern."* Read
literally that forbids adding `schulweg.py` at all. Amending that rule is part
of this change (see "Documentation").

## Scope

- Scheduled **arrival** at Baierbrunn between 06:30 and 08:30 local time.
- **School days only** — see "Schultag definition" below.
- **Both directions** (`wolfratshausen` and `muenchen`). The original request
  names "Schule / Arbeit": the school run goes south toward Icking and
  Wolfratshausen, the work run goes north toward München.
- 6 trains per direction per school day. Sample size varies by month and must
  never be hardcoded — July 2026 had 138 arrivals per direction (23 per slot),
  May 2026 had 103/105 (15–18 per slot).

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
metric and by month. The sheet presents both numbers and carries no fixed claim.

## Schultag definition

The sheet is called *Schulweg* and its day count is labelled *Schultage*, so the
count must mean what it says. Excluding weekends alone is not enough: Bavarian
summer holidays 2026 run 03.08.–14.09., so an August sheet filtered only by
weekday would report ~21 "Schultage" across a period with no school at all.

A school day is a date that is **Mon–Fri**, **not a Bavarian public holiday**,
and **not inside a Bavarian school-holiday period**.

### Public holidays — computed, no dependency

Fixed: 01.01 Neujahr, 06.01 Heilige Drei Könige, 01.05 Tag der Arbeit,
15.08 Mariä Himmelfahrt (Baierbrunn is in Landkreis München, a predominantly
Catholic community, so this applies), 03.10 Tag der Deutschen Einheit,
01.11 Allerheiligen, 25.12 and 26.12 Weihnachten.

Movable, derived from Easter via the Anonymous Gregorian algorithm: Karfreitag
(−2), Ostermontag (+1), Christi Himmelfahrt (+39), Pfingstmontag (+50),
Fronleichnam (+60). Verified for 2026: Ostersonntag 05.04, Karfreitag 03.04,
Ostermontag 06.04, Himmelfahrt 14.05, Pfingstmontag 25.05, Fronleichnam 04.06.

Augsburger Friedensfest (08.08) is city-of-Augsburg only and does not apply.

### School holidays — OpenHolidays API with a committed table as fallback

Bavarian school-holiday dates cannot be derived. They come from the
[OpenHolidays API](https://www.openholidaysapi.org/) at runtime:

```
GET https://openholidaysapi.org/SchoolHolidays
    ?countryIsoCode=DE&subdivisionCode=DE-BY&languageIsoCode=DE
    &validFrom=<YYYY>-01-01&validTo=<YYYY>-12-31
```

No API key, no registration. Query windows are capped at three years, which one
calendar year comfortably satisfies. Querying a full calendar year also returns
the Weihnachtsferien that start in December and run into January, because the
API returns every period *overlapping* the window.

If the API is unreachable **or returns an implausible result**, `schulweg.py`
falls back to a committed `FERIEN` table and says so on the sheet.

#### Why the plausibility check matters more than the error handling

A network error is easy — it raises, and the fallback takes over. The dangerous
case is a successful `200` carrying an empty or truncated array: an endpoint
rename, a changed parameter name or a silent upstream data gap would then make
*every weekday a Schultag*, and the sheet would look completely normal while
being wrong. So a response is accepted only if it contains at least five School
periods for the year; Bavaria has seven. Anything less is treated as a failure.

#### Data-quality gotcha

Querying `subdivisionCode=DE-BY` also returns entries scoped to sub-regions of
Bavaria. `Friedensfest` on 08.08. comes back tagged `DE-BY-AU` — Augsburg only.
Consumers must filter on each entry's own subdivision list rather than trusting
the query parameter. This bites the public-holiday endpoint rather than the
school one, but the same rule applies to both.

#### Public holidays stay computed

Public holidays are **not** fetched. The Easter-derived computation above is
exact, needs no network, and was verified against the API's DE-BY response for
2026: all 13 entries match. Fetching them would add a failure mode for no gain.

#### The fallback table

`FERIEN` is a committed list of `("YYYY-MM-DD", "YYYY-MM-DD")` ranges plus
`FERIEN_ABGEDECKT`, its coverage window. It is **generated from the same API**
by a maintenance script, never hand-typed — hand transcription is precisely what
produced a wrong Weihnachtsferien 2026/27 start date (23.12. instead of 24.12.)
during design.

Buß- und Bettag arrives from the API as an ordinary single-day School period and
is stored as such, so both code paths produce the identical data shape: a sorted
list of inclusive date-string pairs.

The coverage window is load-bearing **on the fallback path only**: if the API
fails and the requested month is not fully inside `FERIEN_ABGEDECKT`,
`schulweg.py` exits with a clear error rather than silently labelling holiday
weekdays as Schultage. When the API answers, the guard is not consulted.

#### Keeping the two paths honest

Two code paths that can disagree are a real cost of this design. Three things
contain it:

1. The table is generated from the API, so they cannot drift arbitrarily.
2. A test compares the live API against the committed table across the coverage
   window and fails on any difference, so drift surfaces in development rather
   than in a published PDF.
3. **The sheet states which source it used**, with the table's vintage —
   `Ferien: OpenHolidays API` or
   `Ferien: hinterlegte Tabelle (Stand 2026-08-05)`. A fallback is never silent.

#### Reproducibility caveat

Re-rendering an old month can produce a different result from the original run
if the upstream data changed in between. That is inherent to fetching at runtime
and is accepted; the source line on the sheet is what makes it detectable.

#### Network rule

`factsheet/CLAUDE.md:138-139` currently permits exactly one external target,
`raw.githubusercontent.com/s7bb/...`. It must be amended to name
`openholidaysapi.org` as the second, and to state that failure there is
non-fatal by design.

### Zero-school-day months

August 2026 has zero school days. The sheet must not emit a blank page or fail
the workflow. In that case it renders over **all Werktage** instead, with the
day count labelled `21 Werktage (keine Schultage im Berichtsmonat)` and a banner
in the header explaining the fallback. Every other element is unchanged.

This also keeps the sheet useful for the *Arbeit* half of issue #1 — people
commute to work during school holidays. The tradeoff is deliberate: school days
are the primary basis, Werktage the fallback, and the sheet always says which
one it used.

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
same basis as the page-1 "Nach Richtung" card, so the two PDFs can be held side
by side:

- `pünktlich` and `Ø Verspätung` agree with the page-1 dircard **to the
  precision page 1 displays**. Page 1 renders `pünktlich` via
  `dn(d["ontime"], 0)` (`generate.py:223`), i.e. "14%" where the Schulweg strip
  shows "(14,2)". They are the same number at different precision, not a
  mismatch.
- `Verfügbarkeit` is 100 % minus the dircard's `ausgefallen`. Because that value
  is already rounded for display, the subtraction agrees at display precision
  but is not an exact identity.
- `> 5 Min.` and `p90` have no per-direction counterpart on page 1. They are new
  and cannot be cross-checked — accepted, because they are the metrics that move
  most between months.

Note that the reference basis (all days, all hours) differs from the window
basis (school days, 06:30–08:30). That is the point of the comparison, but the
sheet must label both bases explicitly so the contrast is not misread.

`schulweg.py` computes everything from the raw DataFrame. It does **not** call
`compute_stats`, so page-1 metric logic gains no new caller.

### Dropped: Zielbahnhof-Erreichbarkeit

Not because the value is uninteresting — May 2026 has 12 `short_turn` in the
window, all → München — but because `terminus_status` is **not comparable across
months**. In May 2026 it is absent on 74 of 103 → Wolfratshausen rows and 75 of
105 → München rows (the older-schema caveat at `factsheet/CLAUDE.md:120-124`),
present on nearly all June rows, and absent again on 13/8 July rows. A metric
whose denominator swings between 29 % and 98 % of the sample would show
month-to-month movement that is an artefact of schema coverage, not of
operations. Excluded until upstream coverage is stable.

## Slot bucketing

This is the load-bearing part of the design.

Grouping on the raw `HH:MM` string is not stable. May 2026 splits a single train
across three scheduled times (counts below are → Wolfratshausen; the → München
pattern is the same, and the combined distinct-`HH:MM` count for the window is
18):

```
06:39  n= 2      06:59  n= 3      07:19  n= 3
06:40  n=12      07:00  n=14      07:20  n=13
06:41  n= 1      07:01  n= 1      07:21  n= 1
```

May would render 18 rows where June and July render 6.

### Data-derived slot centres

A fixed anchor at 06:30 with 20-minute buckets puts edges at :30/:50/:10. That
works today only because the current timetable arrives at :40/:00/:20 —
precisely the bucket midpoints, giving a 10-minute drift margin. That is a
property of this timetable, not of the scheme. After an annual timetable change
to :30/:50/:10 the trains would sit *on* the boundaries and a ±1 minute drift
would split one train across two buckets — exactly the failure the bucketing
exists to prevent.

So the centres are derived from the data, not hardcoded:

1. Take all window arrivals in the month, both directions.
2. Cluster their minute-of-day, keeping the six most frequent centres at least
   10 minutes apart, ordered by time.
3. Each arrival joins the nearest centre; ties resolve to the earlier centre.
4. Row label = that centre formatted `HH:MM`.

This absorbs ±1 minute drift regardless of where in the hour the trains sit.

### Invariants and their failure modes

- **Exactly 6 rows, always.** If fewer than six centres are found, the missing
  rows render with a `–` label, zero-width bars and `0` counts.
- **One train per (day, direction, slot).** Verified to hold for May, June and
  July 2026. If it is ever violated — a timetable with two same-direction trains
  in one 20-minute window — the values are silently averaged under a label
  naming only one of them. `schulweg.py` must emit a warning to stderr when any
  `(day, direction, slot)` count exceeds 1. It must not fail the run; the
  warning makes the anomaly visible without blocking publication.
- **Shared row label across directions.** Verified: in May, June and July 2026
  the per-direction modal minute is identical in all six slots and no ties
  occur. If the two directions ever diverge, the label follows the combined
  modal and the row is still correct in time, just less precise.

### Empty and half-empty cells

A slot may have data for one direction and not the other — this already occurs
per-day (14.05. and 25.05.2026 slot 0 has only → München) and would occur at
month level after a partial-month outage.

Every empty sample renders as `–` for all five metrics, a zero-width bar and a
count of `0`. This must be enforced at the formatter boundary: `dn(nan)` renders
the literal string `nan` into the PDF and `dth(nan)` raises
`ValueError: cannot convert float NaN to integer`. Every `dn()` / `dth()` call
site guards for an empty sample first. The same rule applies to the KPI strip if
a direction has zero window rows.

## Layout

One A4 page. Colours and type match `generate.py`'s palette (`#1b4f8a`,
`#2e9e5b`, `#f0902f`, `#c8371f`) so the two sheets read as one family. There is
no shared palette constant — those hex values are inlined in `histogram`
(`generate.py:171-172`) and in the css literal, and extracting them would mean
editing the frozen file. `schulweg.py` therefore **copies** the values, and the
two sheets can drift if page 1 is ever recoloured. Accepted; noted here so the
drift is not a surprise.

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
│   (weekday line, one point per school day)               │
└──────────────────────────────────────────────────────────┘
```

Values shown are the real July 2026 figures.

Three blocks:

1. **KPI strip** — two direction columns, five metric rows, month-wide reference
   in parentheses after each window value.
2. **Slot grid** — 6 rows × 2 directions. Each cell: a horizontal bar scaled to
   Ø Verspätung on a scale shared across both directions so they are directly
   comparable, normalised to the largest value in the grid; the value; the
   cancellation count.
3. **Ø Verspätung je Schultag** — one point per school day.

The footnote states the per-slot sample size **computed for the month being
rendered**, so a single bad slot is not over-read. It must not hardcode a
number: that figure is 23 for July 2026 but 15–18 for May 2026.

### Two hard requirements from `render_pdf`

`render_pdf` is imported unchanged and the workflow's one-page guard depends on
it, so schulweg's HTML must satisfy its assumptions:

- The root wrapper **must** be `<div class="page">`. `generate.py:401` runs
  `document.querySelector(".page").scrollHeight` and will throw inside Playwright
  if it is absent.
- Schulweg's css **must** carry the same page model as `generate.py:234-236` —
  `@page { size: A4; margin: 0 }` and `body { width: 210mm }`. The 1123px
  threshold is only meaningful against that model.

## Code structure

```
factsheet/
  generate.py    UNCHANGED — frozen page-1 sheet
  schulweg.py    new, ~300 lines
```

`schulweg.py` imports from `generate.py` and edits nothing:

```python
from generate import (load_month, dth, dn, render_pdf,
                      MONATE, MONATE_DATEI, TZ)
```

All seven names verified to exist with the assumed shapes: `load_month:52`,
`dth:33`, `dn:38`, `render_pdf(html, pdf_path):392`, `MONATE:24`,
`MONATE_DATEI:28`, `TZ:21`. Importing is safe: `generate.py`'s only module-level
work is `import pandas` and three constant definitions, and `main()` is behind
`if __name__ == "__main__"` (`generate.py:442`).

Two inherited behaviours to handle explicitly:

- `load_month` returns a **tuple** `(df, data)`. `schulweg.py` needs `df`; the
  `finalized` flag in `data` is already reported by `load_month` itself.
- `load_month` calls `sys.exit()` on fetch failure (`generate.py:58`) and on
  empty data (`:64`). `schulweg.py` inherits a hard exit it cannot intercept.
  Acceptable — the same failure would stop `generate.py` too — but it means
  `schulweg.py` must run *after* `generate.py` in the workflow, never before.

### `sparkline` is copied, not imported

The earlier draft imported `sparkline`. That is wrong on three counts:

- **Its CSS is not exported.** The SVG uses classes `spark` and `spark-lab`,
  defined only inside `render_html`'s css literal (`generate.py:287-288`).
  Without replicating those rules the labels render at browser-default 16px,
  which is exactly what would blow the one-page budget.
- **Its x-axis logic is wrong for a gapped series.** `generate.py:199` labels
  only days where `d % 5 == 0 or d == 1`. Against a school-day-only series that
  yields 3 labels for 18 points in May, 6 in June, 5 in July — arbitrary and
  inconsistent month to month.
- **It could never be fixed.** `factsheet/CLAUDE.md:50-52` freezes `sparkline`
  permanently, so `schulweg.py` would be locked to a heuristic built for a
  contiguous 1..31 series.

So `schulweg.py` carries its own copy with corrected label selection, and its
own `.spark` / `.spark-lab` rules in its own css block. Copying is permitted —
the freeze forbids *modifying* `generate.py`, not writing new code elsewhere.

Note that the copy, like the original, spaces points by list index, so a
Fri→Mon gap looks the same as Mon→Tue. That is correct for a "je Schultag"
series and is a deliberate choice, not an oversight.

### Functions

| Function | Responsibility |
| --- | --- |
| `easter(year)` | Anonymous Gregorian algorithm |
| `feiertage(year)` | Bavarian public holidays for a year |
| `ferien_api(von, bis)` | OpenHolidays query; `None` on failure or implausible response |
| `ferien_ranges(year)` | `(ranges, quelle)` — API first, committed table second |
| `tage_im_monat(month)` | `(days, fallback, quelle)`; Werktage when no school days |
| `slot_centres(df)` | derive the six slot centres from the data |
| `compute_schulweg(df)` | window + month-wide stats per direction, slot table, daily series |
| `kpi_strip(s)` | HTML for block 1 |
| `slot_grid(s)` | HTML/SVG for block 2 |
| `school_spark(daily)` | copied sparkline with corrected labels |
| `render_html_schulweg(s, ...)` | assembles the page, root `<div class="page">` |
| `main()` | CLI: `--month YYYY-MM`, `--outdir output` |

Output: `output/S7_Baierbrunn_<Monat><Jahr>_Schulweg.pdf`, using `MONATE_DATEI`
so March is `Maerz`.

`main()` prints `Berichtsmonat: <YYYY-MM>` and the output path, mirroring
`generate.py:424` — see the workflow section for why that stdout contract
matters.

Conventions inherited from `factsheet/CLAUDE.md`: German throughout, `dth()` and
`dn()` for all numbers, no em dashes (`–` is fine for ranges), exactly one A4
page.

## Workflow

`.github/workflows/monthly-factsheet.yml` needs four changes. The earlier draft
claimed the existing guards would cover the new sheet automatically. They do
not.

**1. Same step, `tee -a`.** The guards live at lines 56-65 *inside* the
"Datenblatt erzeugen" step, before the PDF extraction. A separate second step
would run after them and never be checked. And lines 52/54 use `tee gen.log`,
which **truncates** — a second `| tee gen.log` would wipe generate.py's output
and disable the not-finalized guard for the Datenblatt as well.

So `schulweg.py` runs inside the same step, immediately after `generate.py` and
above line 56, as `2>&1 | tee -a gen.log`.

**2. `head -n1` on both greps.** Line 67 (`PDF=`) is the known one. Line 68
(`YM=`) has the same defect and a worse consequence: with two
`Berichtsmonat: 2026-07` lines in the log, `YM` becomes `"2026-07\n2026-07"`,
and `echo "REPORT_YM=$YM" >> "$GITHUB_ENV"` (line 77) emits a bare `2026-07`
line, which Actions rejects as invalid format. `TAG` still computes correctly,
which would mask the real cause.

**3. Collect both PDFs.** The current line does not error with two PDFs — it
silently publishes only the Datenblatt, which is worse. `$GITHUB_ENV` is
line-oriented `KEY=VALUE`, so the list goes in space-separated on one line:

```bash
PDFS=$(grep -oE 'output/[^ ]+\.pdf' gen.log | sort -u | sed 's#^#factsheet/#' | tr '\n' ' ')
echo "PDF_PATHS=$PDFS" >> "$GITHUB_ENV"
```

and the release step's quoted `"$PDF_PATH"` (lines 90, 92) becomes **unquoted**
`$PDF_PATHS` so it word-splits into two arguments.

**4. `TITLE` / `NOTES`** (lines 86-87) currently say only "Datenblatt" and must
mention both sheets.

Pre-existing issue, worth noting but not fixed here: under `set -euo pipefail`
(line 50) a no-match `grep` inside a command substitution aborts the step, so
the friendly `if [ -z "$PDF" ]` message at lines 69-72 is already unreachable.

## Documentation

- **`factsheet/CLAUDE.md`** — three amendments, not just a new section:
  - "Aufgabe" (lines 8-17) and "Standardablauf" (lines 19-38) define the monthly
    run as `python generate.py` alone. Both must name `schulweg.py` too.
  - "Was du NICHT tun sollst" (lines 136-137) restricts changes to `output/` and
    `generate.py`'s data layer. It must permit `schulweg.py`.
  - A new Schulweg section with its own freeze declaration mirroring the page-1
    rules, plus the `FERIEN` maintenance note.
- **`factsheet/Dockerfile`** — line 13 copies only `generate.py`, so
  `from generate import ...` would fail in the container; line 20 hardcodes
  `ENTRYPOINT ["python", "generate.py"]`, so the new sheet cannot be invoked.
  Both need updating.
- **`factsheet/README.md`** — file tree, run commands and workflow description
  (lines 14-23, 34-38, 51-55) all go stale.
- **Root `CLAUDE.md`** — "Layout", "Commands" and "Architecture" sections.
- **Root `README.md`** — each release now carries two PDFs.

## Verification

1. Generate for **2026-05**, **2026-06** and **2026-07**.
2. Each must render exactly one A4 page — no `> eine A4-Seite` warning.
3. **2026-05 must produce exactly 6 slot rows** despite its ±1 minute drift.
   This is the regression test for the bucketing and the reason May is in the
   list.
4. **2026-08 must render the Werktage fallback**, not a blank page or a crash.
   It is the next month the workflow will actually run.
5. Spot-check July against this document: → Wolfratshausen window availability
   90,6 %, Ø 5,39 Min., 08:00 slot Ø 9,50 Min. with 3 cancellations.
6. Confirm the committed `FERIEN` table still matches the live API across the
   coverage window, that an implausible API response falls back rather than
   producing a holiday-free month, and that a month outside `FERIEN_ABGEDECKT`
   exits with a clear error **only** when the API is also unavailable.
7. Confirm the sheet footer names the Ferien source that was actually used.
8. Confirm `generate.py`'s output PDF is byte-identical before and after the
   change.
9. Dry-run the workflow's log parsing against a two-PDF `gen.log` to confirm
   `REPORT_YM` is single-valued and both PDFs are collected.

## Out of scope

- Any change to the page-1 template or to `generate.py`.
- Zielbahnhof-Erreichbarkeit for the window (see above).
- Named worst-morning callouts.
- An afternoon / return-journey window.
- School-holiday tables for federal states other than Bavaria.
