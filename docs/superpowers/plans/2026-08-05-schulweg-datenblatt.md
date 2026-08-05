# Schulweg-Datenblatt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second monthly PDF reporting S7 Baierbrunn morning-commute quality (Mo–Fr school days, 06:30–08:30, both directions, per departure slot), without touching the frozen page-1 sheet.

**Architecture:** A new self-contained `factsheet/schulweg.py` imports pure helpers from `generate.py` (`load_month`, `dth`, `dn`, `render_pdf`, `MONATE`, `MONATE_DATEI`, `TZ`) and adds its own calendar logic, metric computation, SVG builders and HTML template. `generate.py` is not modified. A new pytest suite covers everything except PDF rendering, which is verified by the existing one-A4-page height check.

**Tech Stack:** Python 3.12+, pandas, Playwright/Chromium, pytest. No new packages;
the only new runtime dependency is the OpenHolidays REST API, which is optional by
design (a committed table covers its absence).

**Spec:** `docs/superpowers/specs/2026-08-05-schulweg-datenblatt-design.md`

## Global Constraints

- **`factsheet/generate.py` must not be modified.** Its output PDF must stay byte-identical. Importing from it is allowed; editing it is not.
- **German output only.** All labels, headings and body text in the PDF.
- **German number formatting.** Always via `dth()` (thousands dot) and `dn()` (decimal comma) imported from `generate.py`. Never format a number inline.
- **No em dashes (`—`) in PDF output.** `–` is permitted for ranges.
- **Exactly one A4 page.** `render_pdf` warns at `> 1123px`; that warning is a build failure, never a reason to change the layout.
- **Filename:** `output/S7_Baierbrunn_<Monat><Jahr>_Schulweg.pdf`, month spelled out, `Maerz` not `März` (use `MONATE_DATEI`).
- **Root wrapper must be `<div class="page">`** — `generate.py:401` runs `document.querySelector(".page").scrollHeight`.
- **CSS must carry** `@page { size: A4; margin: 0 }` and `body { width: 210mm }`, matching `generate.py:234-236`.
- **Network targets:** `raw.githubusercontent.com/s7bb/...` (required) and
  `openholidaysapi.org` (optional; failure must fall back to the committed table,
  never abort). Unit tests must not hit the network - the drift test is marked
  `network` and excluded with `-m "not network"`.
- **Window:** scheduled arrival at Baierbrunn, local minute-of-day 390–510 inclusive (06:30–08:30).
- **Directions:** only `direction_bucket` in `("wolfratshausen", "muenchen")`.
- **Palette (copied, not imported):** `#1b4f8a` primary, `#2e9e5b` green, `#f0902f` orange, `#c8371f` red, `#e2e8ef` border, `#6a7684` muted, `#fbfcfd` card background.

---

### Task 1: Test scaffolding and Bavarian public holidays

**Files:**
- Create: `factsheet/requirements-dev.txt`
- Create: `factsheet/tests/conftest.py`
- Create: `factsheet/tests/test_kalender.py`
- Create: `factsheet/schulweg.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `easter(year: int) -> datetime.date` — Ostersonntag.
  - `feiertage(year: int) -> set[datetime.date]` — Bavarian public holidays.

- [ ] **Step 1: Create the dev requirements file**

`factsheet/requirements-dev.txt`:

```
-r requirements.txt
pytest>=8.0
```

- [ ] **Step 2: Create the pytest path shim**

The tests import `schulweg`, which lives in `factsheet/`, not on `sys.path` by default.

`factsheet/tests/conftest.py`:

```python
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
```

- [ ] **Step 3: Write the failing test**

`factsheet/tests/test_kalender.py`:

```python
import datetime as dt

from schulweg import easter, feiertage


def test_easter_known_years():
    assert easter(2025) == dt.date(2025, 4, 20)
    assert easter(2026) == dt.date(2026, 4, 5)
    assert easter(2027) == dt.date(2027, 3, 28)


def test_feiertage_movable_2026():
    f = feiertage(2026)
    assert dt.date(2026, 4, 3) in f      # Karfreitag
    assert dt.date(2026, 4, 6) in f      # Ostermontag
    assert dt.date(2026, 5, 14) in f     # Christi Himmelfahrt
    assert dt.date(2026, 5, 25) in f     # Pfingstmontag
    assert dt.date(2026, 6, 4) in f      # Fronleichnam


def test_feiertage_fixed_2026():
    f = feiertage(2026)
    for month, day in [(1, 1), (1, 6), (5, 1), (8, 15), (10, 3), (11, 1), (12, 25), (12, 26)]:
        assert dt.date(2026, month, day) in f


def test_feiertage_excludes_non_bavarian():
    f = feiertage(2026)
    assert dt.date(2026, 8, 8) not in f    # Augsburger Friedensfest, Augsburg only
    assert dt.date(2026, 10, 31) not in f  # Reformationstag, not Bavarian
    assert dt.date(2026, 11, 18) not in f  # Buss- und Bettag is not a public holiday in BY
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd factsheet && python -m pytest tests/test_kalender.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'schulweg'`

- [ ] **Step 5: Write the minimal implementation**

Create `factsheet/schulweg.py`:

```python
#!/usr/bin/env python3
"""
Erzeugt das monatliche S7-Baierbrunn-Schulweg-Datenblatt (DIN A4, eine Seite,
deutsch) als PDF: Morgenverkehr Mo-Fr 06:30-08:30, beide Richtungen, je Fahrt.

Datenquelle:  https://github.com/s7bb/s7bb-data  ->  archive/<YYYY-MM>.json
Aufruf:       python schulweg.py [--month YYYY-MM] [--outdir output]

Ohne --month wird der zuletzt abgeschlossene Kalendermonat verwendet.
Das Skript ist deterministisch und benoetigt kein LLM. Die Praesentation von
generate.py wird nicht veraendert, nur wiederverwendet.
"""
import datetime as dt

# Feste gesetzliche Feiertage in Bayern (Monat, Tag).
# Mariae Himmelfahrt gilt in ueberwiegend katholischen Gemeinden; Baierbrunn
# (Landkreis Muenchen) gehoert dazu.
FEIERTAGE_FEST = [(1, 1), (1, 6), (5, 1), (8, 15), (10, 3), (11, 1), (12, 25), (12, 26)]

# Bewegliche Feiertage als Abstand in Tagen zum Ostersonntag.
FEIERTAGE_OSTERN = [-2, 1, 39, 50, 60]  # Karfreitag, Ostermontag, Himmelfahrt,
                                        # Pfingstmontag, Fronleichnam


def easter(year):
    """Ostersonntag nach dem anonymen gregorianischen Algorithmus."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def feiertage(year):
    """Gesetzliche Feiertage in Bayern fuer ein Kalenderjahr."""
    days = {dt.date(year, mo, da) for mo, da in FEIERTAGE_FEST}
    ostern = easter(year)
    days |= {ostern + dt.timedelta(days=off) for off in FEIERTAGE_OSTERN}
    return days
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd factsheet && python -m pytest tests/test_kalender.py -v`
Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add factsheet/requirements-dev.txt factsheet/tests/conftest.py \
        factsheet/tests/test_kalender.py factsheet/schulweg.py
git commit -m "feat: add Bavarian public holiday calculation for Schulweg sheet"
```

---

### Task 2: School holidays from OpenHolidays, with a committed fallback table

**Files:**
- Create: `factsheet/tools/refresh_ferien.py`
- Create: `factsheet/pytest.ini`
- Modify: `factsheet/schulweg.py`
- Modify: `factsheet/tests/test_kalender.py`

**Interfaces:**
- Consumes: `feiertage(year)` from Task 1.
- Produces:
  - `FERIEN: list[tuple[str, str]]` — inclusive `("YYYY-MM-DD", "YYYY-MM-DD")` ranges, generated, never hand-typed.
  - `FERIEN_ABGEDECKT: tuple[str, str]` — inclusive coverage window for the fallback path.
  - `ferien_api(von: str, bis: str) -> list[tuple[str, str]] | None` — `None` on failure *or* implausible response.
  - `ferien_ranges(year: int) -> tuple[list[tuple[str, str]], str]` — `(ranges, quelle)`.
  - `ist_ferientag(day: datetime.date, ranges) -> bool`
  - `pruefe_abdeckung(month: str) -> None` — raises `SystemExit` if `month` is not fully covered.
  - `tage_im_monat(month: str) -> tuple[list[datetime.date], bool, str]` — `(days, fallback, quelle)`.

**Note for Tasks 4 and 6:** `tage_im_monat` returns **three** values. `quelle` is
a human-readable source label that must reach the rendered sheet.

- [ ] **Step 1: Understand where these dates came from**

The table in Step 3 is **not** a guess — it was extracted on 2026-08-05 from
<https://www.schulferien.org/deutschland/ferien/bayern/> and its per-holiday
subpages (`/ferien/ostern/bayern/`, `/pfingsten/`, `/winter/`, `/sommer/`,
`/herbst/`, `/weihnachten/`). Every range below was read from **two** separate
pages and agreed on both.

Two things worth knowing before you touch it:

- **`schulferien.org` is a secondary source.** The official publisher is the
  Bayerisches Staatsministerium für Unterricht und Kultus.
  `https://www.km.bayern.de/schulferien` returned HTTP 404 on 2026-08-05, so the
  official page was not reachable for cross-checking. If you can reach an
  official StMUK page, re-confirm the table against it.
- **Extraction from that site is not perfectly reliable.** Two pages disagreed
  about dates in early 2025 (Osterferien reported as 25.03.–06.04.2025, which
  cannot be right — Easter 2025 was 20 April). Those years fall outside the
  coverage window and are not in the table, but it is why every used value was
  confirmed twice.

Every one of those values was then confirmed a third time against the
OpenHolidays API, which returned the identical 18 periods — including
Buß- und Bettag as ordinary single-day School periods (19.11.2025, 18.11.2026,
17.11.2027) and the corrected Weihnachtsferien start.

`Buß- und Bettag` therefore needs no special handling: it arrives from the API
like any other period and is stored the same way, so the API path and the
fallback path produce the identical data shape.

Bayern is the only state handled.

- [ ] **Step 2: Create the table generator and the pytest marker config**

`factsheet/tools/refresh_ferien.py`:

```python
#!/usr/bin/env python3
"""Erzeugt den FERIEN-Block fuer schulweg.py aus der OpenHolidays-API.

Aufruf:  python tools/refresh_ferien.py --von 2025-08-01 --bis 2028-01-31

Gibt den Block auf stdout aus. Inhalt in schulweg.py ersetzen und committen.
Die Tabelle wird nie von Hand getippt: genau das hat beim Entwurf ein falsches
Startdatum der Weihnachtsferien 2026/27 erzeugt (23.12. statt 24.12.).

Das Abfragefenster der API ist auf drei Jahre begrenzt.
"""
import argparse
import json
import urllib.parse
import urllib.request

API = "https://openholidaysapi.org/SchoolHolidays"


def _name(eintrag):
    for n in eintrag.get("name", []):
        if n.get("language") == "DE":
            return n["text"]
    return "?"


def hole(von, bis):
    query = urllib.parse.urlencode({
        "countryIsoCode": "DE",
        "subdivisionCode": "DE-BY",
        "languageIsoCode": "DE",
        "validFrom": von,
        "validTo": bis,
    })
    with urllib.request.urlopen(f"{API}?{query}", timeout=30) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser(
        description="FERIEN-Block fuer schulweg.py erzeugen.")
    ap.add_argument("--von", required=True, help="YYYY-MM-DD")
    ap.add_argument("--bis", required=True, help="YYYY-MM-DD (max. 3 Jahre)")
    args = ap.parse_args()

    eintraege = sorted(
        (e["startDate"], e["endDate"], _name(e))
        for e in hole(args.von, args.bis) if e.get("type") == "School")

    print("# Erzeugt mit tools/refresh_ferien.py aus der OpenHolidays-API.")
    print("# Nicht von Hand bearbeiten - Skript erneut laufen lassen.")
    print("FERIEN = [")
    for start, ende, name in eintraege:
        print(f'    ("{start}", "{ende}"),   # {name}')
    print("]")
    print(f'FERIEN_ABGEDECKT = ("{args.von}", "{args.bis}")')


if __name__ == "__main__":
    main()
```

`factsheet/pytest.ini`:

```ini
[pytest]
markers =
    network: geht ins Netz (OpenHolidays-API); mit -m "not network" ueberspringen.
```

- [ ] **Step 3: Generate the table**

```bash
cd factsheet
python tools/refresh_ferien.py --von 2025-08-01 --bis 2028-01-31
```

Expected output — paste this verbatim into `schulweg.py` in Step 6. It was
captured on 2026-08-05 and matches `schulferien.org` on every entry:

```python
# Erzeugt mit tools/refresh_ferien.py aus der OpenHolidays-API.
# Nicht von Hand bearbeiten - Skript erneut laufen lassen.
FERIEN = [
    ("2025-08-01", "2025-09-15"),   # Sommerferien
    ("2025-11-03", "2025-11-07"),   # Herbstferien
    ("2025-11-19", "2025-11-19"),   # Buß- und Bettag
    ("2025-12-22", "2026-01-05"),   # Weihnachtsferien
    ("2026-02-16", "2026-02-20"),   # Frühjahrsferien
    ("2026-03-30", "2026-04-10"),   # Osterferien
    ("2026-05-26", "2026-06-05"),   # Pfingstferien
    ("2026-08-03", "2026-09-14"),   # Sommerferien
    ("2026-11-02", "2026-11-06"),   # Herbstferien
    ("2026-11-18", "2026-11-18"),   # Buß- und Bettag
    ("2026-12-24", "2027-01-08"),   # Weihnachtsferien
    ("2027-02-08", "2027-02-12"),   # Frühjahrsferien
    ("2027-03-22", "2027-04-02"),   # Osterferien
    ("2027-05-18", "2027-05-28"),   # Pfingstferien
    ("2027-08-02", "2027-09-13"),   # Sommerferien
    ("2027-11-02", "2027-11-05"),   # Herbstferien
    ("2027-11-17", "2027-11-17"),   # Buß- und Bettag
    ("2027-12-24", "2028-01-07"),   # Weihnachtsferien
]
FERIEN_ABGEDECKT = ("2025-08-01", "2028-01-31")
```

If the generated output differs, **use the freshly generated version** and note
the difference in the commit message — upstream data changed.

The coverage window stops at 2028-01-31 on purpose: Frühjahrsferien 2028 and
everything after it are not in this range, so February 2028 onwards must not be
rendered from the table.

- [ ] **Step 4: Write the failing test**

Append to `factsheet/tests/test_kalender.py`:

```python
import json

import pytest

import schulweg
from schulweg import (FERIEN, FERIEN_ABGEDECKT, MIN_FERIEN_PRO_JAHR,
                      QUELLE_API, ferien_api, ferien_ranges, ist_ferientag,
                      pruefe_abdeckung, tage_im_monat)


class FakeResponse:
    """Minimales Stand-in fuer urllib.request.urlopen."""

    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_api(payload):
    return lambda url, timeout=None: FakeResponse(payload)


def school_entries(count):
    return [{"type": "School",
             "startDate": f"2026-01-{i + 1:02d}",
             "endDate": f"2026-01-{i + 1:02d}"}
            for i in range(count)]


def kein_netz(monkeypatch):
    """Erzwingt den Tabellen-Pfad, damit Tests offline deterministisch sind."""
    monkeypatch.setattr(schulweg, "ferien_api", lambda von, bis: None)


def test_ferien_table_is_sorted_and_disjoint():
    ranges = [(dt.date.fromisoformat(a), dt.date.fromisoformat(b)) for a, b in FERIEN]
    for start, end in ranges:
        assert start <= end
    for (_, prev_end), (next_start, _) in zip(ranges, ranges[1:]):
        assert prev_end < next_start


def test_ferien_table_within_coverage():
    lo, hi = (dt.date.fromisoformat(x) for x in FERIEN_ABGEDECKT)
    for a, b in FERIEN:
        assert lo <= dt.date.fromisoformat(a)


def test_weihnachtsferien_2026_start_on_the_24th():
    """Beim Entwurf stand hier faelschlich der 23.12. - festgenagelt."""
    assert ("2026-12-24", "2027-01-08") in FERIEN


def test_api_returns_none_on_network_error(monkeypatch):
    def boom(url, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(schulweg.urllib.request, "urlopen", boom)
    assert ferien_api("2026-01-01", "2026-12-31") is None


def test_api_returns_none_on_empty_response(monkeypatch):
    """HTTP 200 mit leerer Liste ist gefaehrlicher als ein Netzfehler:
    ohne diese Pruefung waere jeder Werktag ein Schultag."""
    monkeypatch.setattr(schulweg.urllib.request, "urlopen", fake_api([]))
    assert ferien_api("2026-01-01", "2026-12-31") is None


def test_api_returns_none_on_truncated_response(monkeypatch):
    monkeypatch.setattr(schulweg.urllib.request, "urlopen",
                        fake_api(school_entries(MIN_FERIEN_PRO_JAHR - 1)))
    assert ferien_api("2026-01-01", "2026-12-31") is None


def test_api_returns_none_on_malformed_entries(monkeypatch):
    monkeypatch.setattr(schulweg.urllib.request, "urlopen",
                        fake_api([{"type": "School"}] * 7))
    assert ferien_api("2026-01-01", "2026-12-31") is None


def test_api_accepts_a_plausible_response(monkeypatch):
    monkeypatch.setattr(schulweg.urllib.request, "urlopen",
                        fake_api(school_entries(MIN_FERIEN_PRO_JAHR)))
    result = ferien_api("2026-01-01", "2026-12-31")
    assert result is not None
    assert len(result) == MIN_FERIEN_PRO_JAHR
    assert result == sorted(result)


def test_api_ignores_non_school_entries(monkeypatch):
    payload = school_entries(MIN_FERIEN_PRO_JAHR) + [
        {"type": "Public", "startDate": "2026-05-01", "endDate": "2026-05-01"}]
    monkeypatch.setattr(schulweg.urllib.request, "urlopen", fake_api(payload))
    assert len(ferien_api("2026-01-01", "2026-12-31")) == MIN_FERIEN_PRO_JAHR


def test_ferien_ranges_labels_the_api_source(monkeypatch):
    monkeypatch.setattr(schulweg, "ferien_api",
                        lambda von, bis: [("2026-08-03", "2026-09-14")])
    ranges, quelle = ferien_ranges(2026)
    assert quelle == QUELLE_API
    assert ranges == [("2026-08-03", "2026-09-14")]


def test_ferien_ranges_labels_the_fallback_source(monkeypatch):
    kein_netz(monkeypatch)
    ranges, quelle = ferien_ranges(2026)
    assert quelle != QUELLE_API
    assert "Tabelle" in quelle
    assert ranges == [tuple(r) for r in FERIEN]


def test_sommerferien_2026_anchor(monkeypatch):
    kein_netz(monkeypatch)
    ranges, _ = ferien_ranges(2026)
    assert ist_ferientag(dt.date(2026, 8, 3), ranges)
    assert ist_ferientag(dt.date(2026, 9, 14), ranges)
    assert not ist_ferientag(dt.date(2026, 7, 31), ranges)
    assert not ist_ferientag(dt.date(2026, 9, 15), ranges)


def test_coverage_guard_rejects_uncovered_month():
    with pytest.raises(SystemExit):
        pruefe_abdeckung("2035-01")
    pruefe_abdeckung("2026-07")  # must not raise


def test_coverage_guard_is_skipped_when_the_api_answers(monkeypatch):
    """Ausserhalb der Tabelle, aber die API antwortet - kein Abbruch."""
    monkeypatch.setattr(schulweg, "ferien_api",
                        lambda von, bis: [("2035-08-01", "2035-09-10")])
    days, fallback, quelle = tage_im_monat("2035-01")
    assert quelle == QUELLE_API
    assert len(days) > 0


def test_uncovered_month_without_api_aborts(monkeypatch):
    kein_netz(monkeypatch)
    with pytest.raises(SystemExit):
        tage_im_monat("2035-01")


def test_july_2026_has_23_school_days(monkeypatch):
    kein_netz(monkeypatch)
    days, fallback, _ = tage_im_monat("2026-07")
    assert fallback is False
    assert len(days) == 23
    assert all(d.weekday() < 5 for d in days)


def test_august_2026_falls_back_to_werktage(monkeypatch):
    kein_netz(monkeypatch)
    days, fallback, _ = tage_im_monat("2026-08")
    assert fallback is True
    assert len(days) == 21          # Mon-Fri in August 2026
    assert dt.date(2026, 8, 17) in days


def test_school_days_exclude_public_holidays(monkeypatch):
    kein_netz(monkeypatch)
    days, fallback, _ = tage_im_monat("2026-06")
    assert fallback is False
    assert dt.date(2026, 6, 4) not in days     # Fronleichnam
    assert dt.date(2026, 6, 8) in days         # first day after Pfingstferien


def test_buss_und_bettag_is_not_a_school_day(monkeypatch):
    kein_netz(monkeypatch)
    days, _, _ = tage_im_monat("2026-11")
    assert dt.date(2026, 11, 18) not in days   # Buss- und Bettag
    assert dt.date(2026, 11, 19) in days       # Donnerstag danach


@pytest.mark.network
def test_live_api_matches_the_committed_table():
    """Faengt Drift zwischen beiden Pfaden ab, bevor sie in ein PDF geraet."""
    von, bis = FERIEN_ABGEDECKT
    live = ferien_api(von, bis)
    assert live is not None, "OpenHolidays nicht erreichbar"
    assert live == [tuple(r) for r in FERIEN]
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `cd factsheet && python -m pytest tests/test_kalender.py -v -m "not network"`
Expected: FAIL — `ImportError: cannot import name 'FERIEN'`

- [ ] **Step 6: Write the minimal implementation**

Add to the imports at the top of `factsheet/schulweg.py`:

```python
import json
import sys
import urllib.parse
import urllib.request
```

Then append, pasting the `FERIEN` block generated in Step 3:

```python
API_SCHULFERIEN = "https://openholidaysapi.org/SchoolHolidays"

# Bayern hat sieben Ferienzeitraeume pro Jahr (inkl. Buss- und Bettag). Eine
# Antwort mit weniger als fuenf gilt als unplausibel: ein HTTP 200 mit leerer
# Liste wuerde sonst jeden Werktag zum Schultag machen, und das PDF saehe dabei
# voellig normal aus.
MIN_FERIEN_PRO_JAHR = 5

QUELLE_API = "OpenHolidays API"
FERIEN_STAND = "2026-08-05"
QUELLE_TABELLE = f"hinterlegte Tabelle (Stand {FERIEN_STAND})"

# <<< FERIEN-Block aus Schritt 3 hier einfuegen >>>


def ferien_api(von, bis, timeout=15):
    """Bayerische Schulferien von OpenHolidays.

    Gibt None zurueck, wenn die Abfrage fehlschlaegt ODER die Antwort
    unplausibel ist. Beides fuehrt zum Tabellen-Fallback."""
    query = urllib.parse.urlencode({
        "countryIsoCode": "DE",
        "subdivisionCode": "DE-BY",
        "languageIsoCode": "DE",
        "validFrom": von,
        "validTo": bis,
    })
    try:
        with urllib.request.urlopen(f"{API_SCHULFERIEN}?{query}", timeout=timeout) as r:
            data = json.load(r)
    except Exception as e:
        print(f"WARNUNG: OpenHolidays nicht erreichbar ({e}) - "
              f"{QUELLE_TABELLE} wird verwendet.", file=sys.stderr)
        return None

    try:
        ranges = sorted((e["startDate"], e["endDate"]) for e in data
                        if e.get("type") == "School")
    except (AttributeError, KeyError, TypeError) as e:
        print(f"WARNUNG: Unerwartete Antwort von OpenHolidays ({e}) - "
              f"{QUELLE_TABELLE} wird verwendet.", file=sys.stderr)
        return None

    if len(ranges) < MIN_FERIEN_PRO_JAHR:
        print(f"WARNUNG: OpenHolidays liefert nur {len(ranges)} Ferienzeitraeume "
              f"fuer {von}..{bis} (mindestens {MIN_FERIEN_PRO_JAHR} erwartet) - "
              f"{QUELLE_TABELLE} wird verwendet.", file=sys.stderr)
        return None
    return ranges


def ferien_ranges(year):
    """(Zeitraeume, Quellenbezeichnung) fuer ein Kalenderjahr.

    Eine Jahresabfrage liefert auch die Weihnachtsferien, die im Dezember
    beginnen und ins Folgejahr laufen - die API gibt jeden Zeitraum zurueck,
    der das Fenster ueberschneidet."""
    aus_api = ferien_api(f"{year}-01-01", f"{year}-12-31")
    if aus_api is not None:
        return aus_api, QUELLE_API
    return [tuple(r) for r in FERIEN], QUELLE_TABELLE


def ist_ferientag(day, ranges):
    """True, wenn der Tag in einem der Ferienzeitraeume liegt."""
    return any(dt.date.fromisoformat(a) <= day <= dt.date.fromisoformat(b)
               for a, b in ranges)


def _monatsgrenzen(month):
    year, mo = (int(x) for x in month.split("-"))
    first = dt.date(year, mo, 1)
    last = dt.date(year + (mo == 12), mo % 12 + 1, 1) - dt.timedelta(days=1)
    return first, last


def pruefe_abdeckung(month):
    """Bricht ab, wenn der Monat nicht vollstaendig von FERIEN abgedeckt ist.
    Gilt nur fuer den Tabellen-Fallback; antwortet die API, ist die Tabelle
    nicht im Spiel."""
    first, last = _monatsgrenzen(month)
    lo, hi = (dt.date.fromisoformat(x) for x in FERIEN_ABGEDECKT)
    if first < lo or last > hi:
        raise SystemExit(
            f"FEHLER: OpenHolidays nicht verfuegbar und {month} liegt "
            f"ausserhalb der hinterlegten Ferientabelle "
            f"({FERIEN_ABGEDECKT[0]}..{FERIEN_ABGEDECKT[1]}). "
            f"Tabelle mit tools/refresh_ferien.py erneuern."
        )


def tage_im_monat(month):
    """Schultage des Monats plus Quellenangabe.

    Gibt es keine Schultage (reiner Ferienmonat), werden alle Werktage
    zurueckgegeben; das zweite Element zeigt diesen Fallback an. Ein
    Kalendermonat liegt immer in genau einem Jahr, daher genuegt ein
    Jahresaufruf."""
    first, last = _monatsgrenzen(month)
    ranges, quelle = ferien_ranges(first.year)
    if quelle != QUELLE_API:
        pruefe_abdeckung(month)

    werktage = []
    day = first
    while day <= last:
        if day.weekday() < 5:
            werktage.append(day)
        day += dt.timedelta(days=1)

    frei = feiertage(first.year)
    schultage = [d for d in werktage
                 if d not in frei and not ist_ferientag(d, ranges)]
    if schultage:
        return schultage, False, quelle
    return werktage, True, quelle
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd factsheet && python -m pytest tests/test_kalender.py -v -m "not network"`
Expected: 23 passed

If `test_july_2026_has_23_school_days` or `test_august_2026_falls_back_to_werktage`
fails, the `FERIEN` block was pasted wrong — re-run Step 3, do not edit the test.

- [ ] **Step 8: Run the drift test against the live API**

Run: `cd factsheet && python -m pytest tests/test_kalender.py -v -m network`
Expected: 1 passed.

A failure here means upstream changed since 2026-08-05. Re-run Step 3, paste the
new block, bump `FERIEN_STAND`, and say so in the commit message. Never edit the
table by hand to make this pass.

- [ ] **Step 9: Commit**

```bash
git add factsheet/schulweg.py factsheet/tests/test_kalender.py \
        factsheet/tools/refresh_ferien.py factsheet/pytest.ini
git commit -m "feat: resolve school days from OpenHolidays with a committed fallback table"
```

---

### Task 3: Data-derived slot centres

**Files:**
- Modify: `factsheet/schulweg.py`
- Create: `factsheet/tests/test_slots.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `WINDOW_VON = 390`, `WINDOW_BIS = 510` — inclusive minute-of-day bounds.
  - `slot_centres(minutes: list[int]) -> list[int]` — up to 6 centres, ascending.
  - `assign_slot(minute: int, centres: list[int]) -> int | None` — index of nearest centre.
  - `hhmm(minute: int) -> str` — `400 -> "06:40"`.

- [ ] **Step 1: Write the failing test**

`factsheet/tests/test_slots.py`:

```python
from schulweg import assign_slot, hhmm, slot_centres


def test_hhmm_formats_minute_of_day():
    assert hhmm(390) == "06:30"
    assert hhmm(400) == "06:40"
    assert hhmm(500) == "08:20"


def test_centres_from_clean_timetable():
    minutes = [m for m in (400, 420, 440, 460, 480, 500) for _ in range(20)]
    assert slot_centres(minutes) == [400, 420, 440, 460, 480, 500]


def test_centres_absorb_one_minute_drift():
    """May 2026 splits one train across 06:39/06:40/06:41."""
    minutes = []
    for base in (400, 420, 440, 460, 480, 500):
        minutes += [base] * 13 + [base - 1] * 3 + [base + 1] * 1
    assert slot_centres(minutes) == [400, 420, 440, 460, 480, 500]


def test_centres_work_off_the_midpoint():
    """A timetable at :30/:50/:10 must behave the same as one at :40/:00/:20."""
    minutes = []
    for base in (390, 410, 430, 450, 470, 490):
        minutes += [base] * 13 + [base - 1] * 3 + [base + 1] * 1
    assert slot_centres(minutes) == [390, 410, 430, 450, 470, 490]


def test_centres_tie_breaks_to_earlier_minute():
    minutes = [400] * 5 + [460] * 5
    assert slot_centres(minutes) == [400, 460]


def test_fewer_than_six_centres_is_allowed():
    assert slot_centres([400] * 10 + [420] * 10) == [400, 420]
    assert slot_centres([]) == []


def test_assign_slot_picks_nearest_centre():
    centres = [400, 420, 440]
    assert assign_slot(399, centres) == 0
    assert assign_slot(401, centres) == 0
    assert assign_slot(419, centres) == 1
    assert assign_slot(441, centres) == 2


def test_assign_slot_tie_goes_to_earlier_centre():
    centres = [400, 420]
    assert assign_slot(410, centres) == 0


def test_assign_slot_without_centres():
    assert assign_slot(400, []) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd factsheet && python -m pytest tests/test_slots.py -v`
Expected: FAIL — `ImportError: cannot import name 'slot_centres'`

- [ ] **Step 3: Write the minimal implementation**

Append to `factsheet/schulweg.py`:

```python
from collections import Counter

# Zeitfenster Morgenverkehr als Minute des Tages, Ortszeit, beide Grenzen
# eingeschlossen: 06:30 bis 08:30.
WINDOW_VON, WINDOW_BIS = 390, 510

SLOTS = 6          # feste Zeilenzahl im Raster
SLOT_ABSTAND = 10  # Mindestabstand zweier Slot-Mitten in Minuten


def hhmm(minute):
    """Minute des Tages -> 'HH:MM'."""
    return f"{minute // 60:02d}:{minute % 60:02d}"


def slot_centres(minutes):
    """Slot-Mitten aus den Daten ableiten statt sie fest zu verdrahten.

    Haeufigste Ankunftsminuten zuerst, jede neue Mitte muss mindestens
    SLOT_ABSTAND Minuten von allen bisherigen entfernt sein. Damit werden
    Fahrplan-Abweichungen von +/-1 Minute eingesammelt, unabhaengig davon, wo
    in der Stunde die Zuege liegen."""
    counts = Counter(minutes)
    centres = []
    for minute, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if all(abs(minute - c) >= SLOT_ABSTAND for c in centres):
            centres.append(minute)
        if len(centres) == SLOTS:
            break
    return sorted(centres)


def assign_slot(minute, centres):
    """Index der naechstgelegenen Slot-Mitte; bei Gleichstand die fruehere."""
    if not centres:
        return None
    return min(range(len(centres)),
               key=lambda i: (abs(minute - centres[i]), centres[i]))
```

Move the `from collections import Counter` line up to the other imports at the
top of the file rather than leaving it mid-module.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd factsheet && python -m pytest tests/test_slots.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add factsheet/schulweg.py factsheet/tests/test_slots.py
git commit -m "feat: derive morning slot centres from data instead of a fixed anchor"
```

---

### Task 4: Metric computation

**Files:**
- Modify: `factsheet/schulweg.py`
- Create: `factsheet/tests/test_stats.py`

**Interfaces:**
- Consumes: `tage_im_monat`, `slot_centres`, `assign_slot`, `hhmm`, `WINDOW_VON`, `WINDOW_BIS`.
- Produces:
  - `RICHTUNGEN = ("wolfratshausen", "muenchen")`
  - `kennzahlen(rows: pandas.DataFrame) -> dict` with keys `n, canc, avail, ontime, avg, gt5, p90`; every value except `n` and `canc` is `None` when the sample is empty.
  - `compute_schulweg(df: pandas.DataFrame, month: str) -> dict` with keys
    `days, fallback, quelle, centres, win, mon, slots, daily, warnungen`.
  - `slots` is a list of exactly 6 dicts: `{"label": str, "dirs": {richtung: kennzahlen}}`.

- [ ] **Step 1: Write the failing test**

`factsheet/tests/test_stats.py`:

```python
import datetime as dt
import zoneinfo

import pandas as pd
import pytest

import schulweg
from schulweg import compute_schulweg, kennzahlen

TZ = zoneinfo.ZoneInfo("Europe/Berlin")


@pytest.fixture(autouse=True)
def kein_netz(monkeypatch):
    """compute_schulweg ruft tage_im_monat, das sonst OpenHolidays abfragen
    wuerde. Unit-Tests bleiben offline und deterministisch."""
    monkeypatch.setattr(schulweg, "ferien_api", lambda von, bis: None)


SPALTEN = ["scheduled_time", "local", "date", "direction_bucket",
           "delay_minutes", "cancelled"]


def make_df(records):
    """records: (date, minute_of_day, richtung, delay_or_None_for_cancelled)"""
    if not records:
        # Leeres DataFrame braucht die Spalten trotzdem - pd.DataFrame([])
        # haette keine, und kennzahlen() greift sonst ins Leere.
        df = pd.DataFrame({c: [] for c in SPALTEN})
        df["cancelled"] = df["cancelled"].astype(bool)
        return df
    rows = []
    for day, minute, richtung, delay in records:
        local = dt.datetime.combine(day, dt.time(minute // 60, minute % 60), TZ)
        rows.append({
            "scheduled_time": local.astimezone(dt.timezone.utc),
            "local": local,
            "date": day,
            "direction_bucket": richtung,
            "delay_minutes": delay,
            "cancelled": delay is None,
        })
    df = pd.DataFrame(rows)
    df["scheduled_time"] = pd.to_datetime(df["scheduled_time"], utc=True)
    df["local"] = pd.to_datetime(df["local"]).dt.tz_convert(TZ)
    return df


def test_kennzahlen_basic():
    df = make_df([
        (dt.date(2026, 7, 1), 400, "muenchen", 0.0),
        (dt.date(2026, 7, 2), 400, "muenchen", 4.0),
        (dt.date(2026, 7, 3), 400, "muenchen", 12.0),
        (dt.date(2026, 7, 6), 400, "muenchen", None),
    ])
    k = kennzahlen(df)
    assert k["n"] == 4
    assert k["canc"] == 1
    assert k["avail"] == pytest.approx(75.0)
    assert k["ontime"] == pytest.approx(100 / 3)
    assert k["avg"] == pytest.approx(16 / 3)
    assert k["gt5"] == pytest.approx(100 / 3)


def test_kennzahlen_empty_sample_returns_none_not_nan():
    k = kennzahlen(make_df([]))
    assert k["n"] == 0
    assert k["canc"] == 0
    assert k["avail"] is None
    assert k["ontime"] is None
    assert k["avg"] is None
    assert k["gt5"] is None
    assert k["p90"] is None


def test_kennzahlen_all_cancelled_has_no_delay_stats():
    df = make_df([(dt.date(2026, 7, 1), 400, "muenchen", None)])
    k = kennzahlen(df)
    assert k["n"] == 1
    assert k["canc"] == 1
    assert k["avail"] == pytest.approx(0.0)
    assert k["avg"] is None


def test_compute_always_returns_six_slots():
    df = make_df([(dt.date(2026, 7, 1), 400, "muenchen", 1.0)])
    s = compute_schulweg(df, "2026-07")
    assert len(s["slots"]) == 6
    assert s["slots"][0]["label"] == "06:40"
    assert s["slots"][5]["label"] == "–"


def test_compute_ignores_weekends_and_holidays():
    df = make_df([
        (dt.date(2026, 7, 1), 400, "muenchen", 1.0),   # Wednesday, school day
        (dt.date(2026, 7, 4), 400, "muenchen", 99.0),  # Saturday
        (dt.date(2026, 8, 5), 400, "muenchen", 99.0),  # summer holidays
    ])
    s = compute_schulweg(df, "2026-07")
    assert s["win"]["muenchen"]["n"] == 1
    assert s["win"]["muenchen"]["avg"] == pytest.approx(1.0)


def test_compute_ignores_arrivals_outside_the_window():
    df = make_df([
        (dt.date(2026, 7, 1), 400, "muenchen", 1.0),
        (dt.date(2026, 7, 1), 389, "muenchen", 99.0),   # 06:29
        (dt.date(2026, 7, 1), 511, "muenchen", 99.0),   # 08:31
    ])
    s = compute_schulweg(df, "2026-07")
    assert s["win"]["muenchen"]["n"] == 1


def test_window_bounds_are_inclusive():
    df = make_df([
        (dt.date(2026, 7, 1), 390, "muenchen", 1.0),
        (dt.date(2026, 7, 1), 510, "muenchen", 3.0),
    ])
    s = compute_schulweg(df, "2026-07")
    assert s["win"]["muenchen"]["n"] == 2


def test_month_reference_uses_all_days_and_all_hours():
    df = make_df([
        (dt.date(2026, 7, 1), 400, "muenchen", 1.0),    # in window
        (dt.date(2026, 7, 4), 900, "muenchen", 9.0),    # Saturday afternoon
    ])
    s = compute_schulweg(df, "2026-07")
    assert s["win"]["muenchen"]["n"] == 1
    assert s["mon"]["muenchen"]["n"] == 2
    assert s["mon"]["muenchen"]["avg"] == pytest.approx(5.0)


def test_half_empty_slot_keeps_the_row():
    df = make_df([(dt.date(2026, 7, 1), 400, "muenchen", 2.0)])
    s = compute_schulweg(df, "2026-07")
    slot = s["slots"][0]
    assert slot["dirs"]["muenchen"]["n"] == 1
    assert slot["dirs"]["wolfratshausen"]["n"] == 0
    assert slot["dirs"]["wolfratshausen"]["avg"] is None


def test_duplicate_train_in_slot_is_warned_not_dropped():
    df = make_df([
        (dt.date(2026, 7, 1), 400, "muenchen", 2.0),
        (dt.date(2026, 7, 1), 404, "muenchen", 6.0),
    ])
    s = compute_schulweg(df, "2026-07")
    assert s["slots"][0]["dirs"]["muenchen"]["n"] == 2
    assert any("mehr als eine Fahrt" in w for w in s["warnungen"])


def test_daily_series_covers_only_days_with_data():
    df = make_df([
        (dt.date(2026, 7, 1), 400, "muenchen", 2.0),
        (dt.date(2026, 7, 2), 400, "muenchen", 6.0),
    ])
    s = compute_schulweg(df, "2026-07")
    assert list(s["daily"]) == [dt.date(2026, 7, 1), dt.date(2026, 7, 2)]
    assert s["daily"][dt.date(2026, 7, 2)] == pytest.approx(6.0)


def test_fallback_month_uses_werktage():
    df = make_df([(dt.date(2026, 8, 5), 400, "muenchen", 2.0)])
    s = compute_schulweg(df, "2026-08")
    assert s["fallback"] is True
    assert s["win"]["muenchen"]["n"] == 1


def test_ferien_source_is_carried_through_to_the_sheet():
    df = make_df([(dt.date(2026, 7, 1), 400, "muenchen", 2.0)])
    s = compute_schulweg(df, "2026-07")
    assert "Tabelle" in s["quelle"]      # kein_netz-Fixture erzwingt Fallback
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd factsheet && python -m pytest tests/test_stats.py -v`
Expected: FAIL — `ImportError: cannot import name 'kennzahlen'`

- [ ] **Step 3: Write the minimal implementation**

Append to `factsheet/schulweg.py`:

```python
RICHTUNGEN = ("wolfratshausen", "muenchen")


def kennzahlen(rows):
    """Kennzahlen einer Teilmenge. Leere Stichproben liefern None statt NaN -
    dth()/dn() wuerden sonst 'nan' ins PDF schreiben bzw. abbrechen."""
    n = len(rows)
    canc = int(rows["cancelled"].sum()) if n else 0
    dl = rows.loc[~rows["cancelled"], "delay_minutes"].dropna() if n else []
    if len(dl) == 0:
        return {"n": n, "canc": canc,
                "avail": 100 * (n - canc) / n if n else None,
                "ontime": None, "avg": None, "gt5": None, "p90": None}
    return {
        "n": n, "canc": canc,
        "avail": 100 * (n - canc) / n,
        "ontime": 100 * float((dl <= 0).mean()),
        "avg": float(dl.mean()),
        "gt5": 100 * float((dl > 5).mean()),
        "p90": float(dl.quantile(.9)),
    }


def compute_schulweg(df, month):
    """Alle Kennzahlen des Schulweg-Datenblatts."""
    tage, fallback, quelle = tage_im_monat(month)
    tage_set = set(tage)

    d = df[df["direction_bucket"].isin(RICHTUNGEN)].copy()
    d["minute"] = d["local"].dt.hour * 60 + d["local"].dt.minute

    fenster = d[d["date"].isin(tage_set)
                & d["minute"].between(WINDOW_VON, WINDOW_BIS)].copy()

    centres = slot_centres(fenster["minute"].tolist())
    fenster["slot"] = fenster["minute"].map(lambda m: assign_slot(m, centres))

    warnungen = []
    if not fenster.empty:
        doppelt = fenster.groupby(["date", "direction_bucket", "slot"]).size()
        for (day, richtung, idx), anzahl in doppelt[doppelt > 1].items():
            warnungen.append(
                f"WARNUNG: {day} {richtung} Slot {hhmm(centres[int(idx)])}: "
                f"mehr als eine Fahrt ({anzahl}) - Werte werden gemittelt.")

    slots = []
    for i in range(SLOTS):
        label = hhmm(centres[i]) if i < len(centres) else "–"
        dirs = {}
        for richtung in RICHTUNGEN:
            teil = fenster[(fenster["slot"] == i)
                           & (fenster["direction_bucket"] == richtung)]
            dirs[richtung] = kennzahlen(teil)
        slots.append({"label": label, "dirs": dirs})

    nc = fenster[~fenster["cancelled"]]
    daily = {}
    if not nc.empty:
        means = nc.groupby("date")["delay_minutes"].mean()
        daily = {day: float(v) for day, v in means.sort_index().items()}

    return {
        "days": len(tage), "fallback": fallback, "quelle": quelle,
        "centres": centres,
        "win": {r: kennzahlen(fenster[fenster["direction_bucket"] == r])
                for r in RICHTUNGEN},
        "mon": {r: kennzahlen(d[d["direction_bucket"] == r])
                for r in RICHTUNGEN},
        "slots": slots, "daily": daily, "warnungen": warnungen,
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd factsheet && python -m pytest tests/test_stats.py -v`
Expected: 14 passed

- [ ] **Step 5: Run the whole suite**

Run: `cd factsheet && python -m pytest tests/ -v -m "not network"`
Expected: 46 passed

- [ ] **Step 6: Commit**

```bash
git add factsheet/schulweg.py factsheet/tests/test_stats.py
git commit -m "feat: compute Schulweg window and per-slot metrics"
```

---

### Task 5: Sparkline copy with corrected labels

**Files:**
- Modify: `factsheet/schulweg.py`
- Create: `factsheet/tests/test_render.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `school_spark(daily: dict[datetime.date, float]) -> str` — SVG markup.

`generate.py`'s `sparkline` is **not** imported. Its `.spark` / `.spark-lab`
CSS lives only inside `render_html`'s css literal (`generate.py:287-288`), and
its label rule `d % 5 == 0 or d == 1` yields 3 labels for 18 points on a gapped
school-day series. `factsheet/CLAUDE.md:50-52` freezes it, so it could not be
fixed in place. This is an independent copy.

- [ ] **Step 1: Write the failing test**

`factsheet/tests/test_render.py`:

```python
import datetime as dt
import re

from schulweg import school_spark


def label_count(svg):
    return len(re.findall(r'class="spark-lab"', svg))


def test_spark_labels_scale_with_point_count():
    for n in (18, 22, 23):
        daily = {dt.date(2026, 7, 1) + dt.timedelta(days=i): 3.0 for i in range(n)}
        assert 4 <= label_count(school_spark(daily)) <= 7


def test_spark_always_labels_first_and_last_point():
    daily = {dt.date(2026, 7, 1) + dt.timedelta(days=i): 3.0 for i in range(18)}
    svg = school_spark(daily)
    assert ">1<" in svg
    assert ">18<" in svg


def test_spark_handles_single_point():
    svg = school_spark({dt.date(2026, 7, 1): 3.0})
    assert "<svg" in svg
    assert "nan" not in svg


def test_spark_handles_empty_series():
    svg = school_spark({})
    assert "<svg" in svg
    assert "nan" not in svg


def test_spark_handles_all_zero_delays():
    daily = {dt.date(2026, 7, 1) + dt.timedelta(days=i): 0.0 for i in range(5)}
    svg = school_spark(daily)
    assert "nan" not in svg
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd factsheet && python -m pytest tests/test_render.py -v`
Expected: FAIL — `ImportError: cannot import name 'school_spark'`

- [ ] **Step 3: Write the minimal implementation**

Append to `factsheet/schulweg.py`:

```python
def school_spark(daily):
    """Sparkline der taeglichen Durchschnittsverspaetung.

    Eigene Kopie statt Import aus generate.py: die dortige Fassung beschriftet
    nur Tage mit 'd % 5 == 0 or d == 1', was bei einer Reihe aus reinen
    Schultagen (Luecken an Wochenenden und in Ferien) je nach Monat 3 bis 6
    Beschriftungen ergibt. Hier wird stattdessen jeder n-te Punkt beschriftet,
    plus erster und letzter.

    Die Punkte sind gleichmaessig ueber den Index verteilt, nicht ueber das
    Datum: eine Luecke Fr->Mo sieht aus wie Mo->Di. Fuer eine Reihe 'je
    Schultag' ist das beabsichtigt."""
    days = sorted(daily)
    W, H = 700, 80
    if not days:
        return f'<svg viewBox="0 0 {W} {H}" class="spark"></svg>'

    vmax = max(daily.values()) or 1
    pts = []
    for i, day in enumerate(days):
        px = 10 + (W - 20) * i / (len(days) - 1 or 1)
        py = H - 18 - (H - 30) * daily[day] / vmax
        pts.append((px, py))

    poly = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    area = f"10,{H-18} " + poly + f" {pts[-1][0]:.1f},{H-18}"
    dots = "".join(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.3" fill="#1b4f8a"/>'
                   for px, py in pts)

    step = max(1, round(len(days) / 6))
    marked = {0, len(days) - 1} | set(range(0, len(days), step))
    xlab = "".join(f'<text x="{pts[i][0]:.1f}" y="{H-4}" class="spark-lab">'
                   f'{days[i].day}</text>'
                   for i in sorted(marked))

    return (f'<svg viewBox="0 0 {W} {H}" class="spark">'
            f'<polygon points="{area}" fill="#dbe7f5"/>'
            f'<polyline points="{poly}" fill="none" stroke="#1b4f8a" stroke-width="2"/>'
            f'{dots}{xlab}</svg>')
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd factsheet && python -m pytest tests/test_render.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add factsheet/schulweg.py factsheet/tests/test_render.py
git commit -m "feat: add school-day sparkline with label selection that scales"
```

---

### Task 6: HTML template, CLI and PDF output

**Files:**
- Modify: `factsheet/schulweg.py`
- Modify: `factsheet/tests/test_render.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5.
- Produces:
  - `fmt(value, dec=1, suffix="") -> str` — `None` renders `–`.
  - `kpi_strip(s) -> str`, `slot_grid(s) -> str`, `render_html_schulweg(s, month_label, year, archive_month) -> str`
  - `main()` — CLI printing `Berichtsmonat: <YYYY-MM>` and `Erstellt: <path>`.

- [ ] **Step 1: Write the failing test**

Append to `factsheet/tests/test_render.py`:

```python
import pytest

from schulweg import fmt, render_html_schulweg


def test_fmt_renders_none_as_dash():
    assert fmt(None) == "–"
    assert fmt(None, suffix="%") == "–"


def test_fmt_uses_german_decimal_comma():
    assert fmt(5.39, dec=2) == "5,39"
    assert fmt(90.58, dec=1, suffix="%") == "90,6%"


def empty_stats(fallback=False):
    leer = {"n": 0, "canc": 0, "avail": None, "ontime": None,
            "avg": None, "gt5": None, "p90": None}
    return {
        "days": 23, "fallback": fallback, "centres": [],
        "win": {"wolfratshausen": dict(leer), "muenchen": dict(leer)},
        "mon": {"wolfratshausen": dict(leer), "muenchen": dict(leer)},
        "slots": [{"label": "–",
                   "dirs": {"wolfratshausen": dict(leer), "muenchen": dict(leer)}}
                  for _ in range(6)],
        "daily": {}, "warnungen": [], "quelle": "OpenHolidays API",
    }


def test_html_survives_an_entirely_empty_month():
    html = render_html_schulweg(empty_stats(), "Juli", 2026, "2026-07")
    assert "nan" not in html
    assert "None" not in html


def test_html_has_the_page_wrapper_render_pdf_needs():
    html = render_html_schulweg(empty_stats(), "Juli", 2026, "2026-07")
    assert '<div class="page">' in html
    assert "@page { size: A4; margin: 0; }" in html
    assert "width:210mm" in html


def test_html_defines_the_spark_css_it_uses():
    html = render_html_schulweg(empty_stats(), "Juli", 2026, "2026-07")
    assert ".spark-lab {" in html


def test_html_has_no_em_dash():
    html = render_html_schulweg(empty_stats(), "Juli", 2026, "2026-07")
    assert "—" not in html


def test_html_shows_six_slot_rows():
    html = render_html_schulweg(empty_stats(), "Juli", 2026, "2026-07")
    assert html.count('class="slot-row"') == 6


def test_fallback_month_is_labelled_in_the_header():
    html = render_html_schulweg(empty_stats(fallback=True), "August", 2026, "2026-08")
    assert "Werktage" in html
    assert "keine Schultage" in html


def test_ferien_source_is_named_on_the_sheet():
    """Ein Rueckfall auf die Tabelle darf nie unsichtbar sein."""
    s = empty_stats()
    s["quelle"] = "hinterlegte Tabelle (Stand 2026-08-05)"
    html = render_html_schulweg(s, "Juli", 2026, "2026-07")
    assert "hinterlegte Tabelle (Stand 2026-08-05)" in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd factsheet && python -m pytest tests/test_render.py -v`
Expected: FAIL — `ImportError: cannot import name 'fmt'`

- [ ] **Step 3: Write the formatter and the two block builders**

First add the `generate.py` import at the **top** of `factsheet/schulweg.py`,
below the module docstring and beside `import datetime as dt`. It has to land
here rather than with the CLI, because `fmt` below calls `dn`:

```python
from generate import (MONATE, MONATE_DATEI, TZ, dn, load_month, prev_month,
                      render_pdf)
```

All seven names are verified to exist: `MONATE:24`, `MONATE_DATEI:28`, `TZ:21`,
`dn:38`, `load_month:52`, `prev_month:46`, `render_pdf:392`. `dth` is
deliberately **not** imported — every number on this sheet is below 1.000, so
the thousands separator never applies.

Then append:

```python
def fmt(value, dec=1, suffix=""):
    """Zahl deutsch formatieren; leere Stichproben werden zum Gedankenstrich."""
    if value is None:
        return "–"
    return dn(value, dec) + suffix


KPI_ZEILEN = [
    ("Verfügbarkeit", "avail", 1, "%"),
    ("pünktlich", "ontime", 1, "%"),
    ("Ø Verspätung", "avg", 2, ""),
    ("über 5 Min.", "gt5", 1, "%"),
    ("p90 (Min.)", "p90", 0, ""),
]

DIR_LABEL = {"wolfratshausen": "&rarr; Wolfratshausen", "muenchen": "&rarr; M&uuml;nchen"}


def kpi_strip(s):
    rows = ""
    for label, key, dec, suffix in KPI_ZEILEN:
        cells = ""
        for richtung in RICHTUNGEN:
            win = fmt(s["win"][richtung][key], dec, suffix)
            mon = fmt(s["mon"][richtung][key], dec, suffix)
            cells += (f'<div class="kpi-cell"><span class="kv">{win}</span>'
                      f'<span class="kr">Monat {mon}</span></div>')
        rows += f'<div class="kpi-row"><div class="kpi-lab">{label}</div>{cells}</div>'
    return rows


def slot_grid(s):
    werte = [d[r]["avg"] for d in (x["dirs"] for x in s["slots"])
             for r in RICHTUNGEN if d[r]["avg"] is not None]
    vmax = max(werte) if werte else 1
    rows = ""
    for slot in s["slots"]:
        cells = ""
        for richtung in RICHTUNGEN:
            k = slot["dirs"][richtung]
            breite = 100 * k["avg"] / vmax if k["avg"] is not None else 0
            farbe = "#2e9e5b"
            if k["avg"] is not None and k["avg"] > 5:
                farbe = "#c8371f"
            elif k["avg"] is not None and k["avg"] > 3:
                farbe = "#f0902f"
            ausf = (f'<span class="slot-canc">{k["canc"]} Ausf.</span>'
                    if k["canc"] else '<span class="slot-canc"></span>')
            cells += (f'<div class="slot-cell"><div class="slot-track">'
                      f'<div class="slot-fill" style="width:{breite:.1f}%;'
                      f'background:{farbe}"></div></div>'
                      f'<span class="slot-val">{fmt(k["avg"], 2)}</span>{ausf}</div>')
        rows += (f'<div class="slot-row"><div class="slot-lab">{slot["label"]}</div>'
                 f'{cells}</div>')
    return rows
```

- [ ] **Step 4: Write the page template**

Append to `factsheet/schulweg.py`:

```python
CSS = """
@page { size: A4; margin: 0; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Helvetica Neue',Arial,sans-serif; color:#1c2733; width:210mm; }
.page { padding:6mm 13mm 2mm; }
.head { display:flex; align-items:center; justify-content:space-between;
  border-bottom:3px solid #1b4f8a; padding-bottom:7px; margin-bottom:12px; }
.brand { display:flex; align-items:center; gap:12px; }
.logo { width:44px;height:44px;border-radius:9px;background:#1b4f8a;color:#fff;
  font-weight:800;font-size:19px;display:flex;align-items:center;justify-content:center;letter-spacing:-1px; }
h1 { font-size:21px; font-weight:800; letter-spacing:-.3px; }
.sub { font-size:12px; color:#6a7684; margin-top:1px; }
.period { text-align:right;font-size:12px;color:#6a7684; }
.period b { display:block;font-size:17px;color:#1b4f8a;font-weight:800; }
.section-t { font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:1.1px;
  color:#1b4f8a;margin:0 0 8px; display:flex;align-items:center;gap:7px; }
.section-t::before { content:"";width:5px;height:14px;background:#1b4f8a;border-radius:2px; }
.card { border:1px solid #e2e8ef;border-radius:11px;padding:12px 14px;background:#fbfcfd;margin-bottom:12px; }
.colhead { display:flex;font-size:11px;font-weight:800;color:#1b4f8a;margin-bottom:6px; }
.colhead .kpi-lab, .colhead .slot-lab { flex:none; }
.colhead span { flex:1;text-align:center; }
.kpi-row { display:flex;align-items:center;border-top:1px solid #eef2f6;padding:5px 0; }
.kpi-lab { width:150px;flex:none;font-size:12px;font-weight:700; }
.kpi-cell { flex:1;text-align:center; }
.kpi-cell .kv { display:block;font-size:17px;font-weight:800;color:#1c2733; }
.kpi-cell .kr { display:block;font-size:10px;color:#6a7684;margin-top:1px; }
.slot-row { display:flex;align-items:center;border-top:1px solid #eef2f6;padding:6px 0; }
.slot-lab { width:66px;flex:none;font-size:13px;font-weight:800;color:#1b4f8a; }
.slot-cell { flex:1;display:flex;align-items:center;gap:8px;padding-right:14px; }
.slot-track { flex:1;background:#eef2f6;border-radius:5px;height:16px; }
.slot-fill { height:100%;border-radius:5px; }
.slot-val { width:38px;flex:none;text-align:right;font-size:12px;font-weight:800; }
.slot-canc { width:58px;flex:none;font-size:10px;color:#c8371f;font-weight:700; }
.spark { width:100%;height:auto; }
.spark-lab { font-size:9px;fill:#8592a1;text-anchor:middle; }
.notemark { font-size:10px;color:#6a7684;margin-top:6px;line-height:1.45; }
.foot { margin-top:4px;padding-top:5px;border-top:1px solid #e2e8ef;
  font-size:9.5px;color:#8592a1;display:flex;justify-content:space-between; }
"""


def render_html_schulweg(s, month_label, year, archive_month):
    if s["fallback"]:
        tage = (f'{s["days"]} Werktage'
                f'<br><span style="color:#c8371f">keine Schultage im Monat</span>')
        basis = ("Im Berichtsmonat lagen keine Schultage. Ausgewiesen sind "
                 "ersatzweise alle Werktage (Mo–Fr).")
    else:
        tage = f'{s["days"]} Schultage'
        basis = ("Basis: Schultage in Bayern (ohne Wochenenden, gesetzliche "
                 "Feiertage und bayerische Schulferien).")

    proben = [d[r]["n"] for d in (x["dirs"] for x in s["slots"])
              for r in RICHTUNGEN if d[r]["n"]]
    spanne = (f"{min(proben)}–{max(proben)}" if proben else "0")

    kopf = ('<div class="colhead"><div class="kpi-lab"></div>'
            + "".join(f"<span>{DIR_LABEL[r]}</span>" for r in RICHTUNGEN)
            + "</div>")
    kopf_slots = ('<div class="colhead"><div class="slot-lab"></div>'
                  + "".join(f"<span>{DIR_LABEL[r]}</span>" for r in RICHTUNGEN)
                  + "</div>")

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{CSS}</style></head>
<body><div class="page">

<div class="head">
  <div class="brand">
    <div class="logo">S7</div>
    <div><h1>S-Bahn S7 &middot; Baierbrunn &middot; Schulweg</h1>
      <div class="sub">Morgenverkehr Mo&ndash;Fr 06:30&ndash;08:30 &middot; planm&auml;&szlig;ige Ank&uuml;nfte in Baierbrunn</div></div>
  </div>
  <div class="period">Berichtszeitraum<b>{month_label} {year}</b>{tage}</div>
</div>

<div class="card">
  <div class="section-t">Morgenverkehr im Vergleich zum Gesamtmonat</div>
  {kopf}
  {kpi_strip(s)}
  <div class="notemark">{basis} Der Klammerwert je Zelle ist der Monatswert
  &uuml;ber alle Tage und alle Stunden und entspricht dem Wert im
  Monatsdatenblatt.</div>
</div>

<div class="card">
  <div class="section-t">Je Fahrt &middot; planm&auml;&szlig;ige Ankunft in Baierbrunn</div>
  {kopf_slots}
  {slot_grid(s)}
  <div class="notemark">Balkenl&auml;nge: &Oslash; Versp&auml;tung in Minuten,
  gemeinsame Skala f&uuml;r beide Richtungen. Stichprobe je Fahrt und Richtung:
  {spanne} Ank&uuml;nfte im Monat.</div>
</div>

<div class="card">
  <div class="section-t">&Oslash; Versp&auml;tung je Tag</div>
  {school_spark(s['daily'])}
</div>

<div class="foot">
  <span>Quelle: s7bb-data (github.com/s7bb/s7bb-data) &middot; archive/{archive_month}.json
  &middot; Ferien: {s['quelle']}</span>
  <span>Bahnhof Baierbrunn &middot; Versp&auml;tungen &amp; Ausf&auml;lle gg&uuml;. Fahrplan</span>
</div>

</div></body></html>"""
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd factsheet && python -m pytest tests/test_render.py -v`
Expected: 14 passed

- [ ] **Step 6: Add the CLI**

Append to `factsheet/schulweg.py`:

```python
def main():
    import argparse
    import pathlib
    import sys

    ap = argparse.ArgumentParser(
        description="S7-Baierbrunn-Schulweg-Datenblatt (PDF) erzeugen.")
    ap.add_argument("--month", help="Berichtsmonat YYYY-MM (Standard: Vormonat)")
    ap.add_argument("--outdir", default="output",
                    help="Ausgabeverzeichnis (Standard: output)")
    args = ap.parse_args()

    month = args.month or prev_month(dt.datetime.now(TZ).date())
    year, mo = (int(x) for x in month.split("-"))

    print(f"Berichtsmonat: {month} ({MONATE[mo]} {year})")
    df, _ = load_month(month)
    s = compute_schulweg(df, month)
    for warnung in s["warnungen"]:
        print(warnung, file=sys.stderr)

    html = render_html_schulweg(s, MONATE[mo], year, month)

    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    pdf_path = outdir / f"S7_Baierbrunn_{MONATE_DATEI[mo]}{year}_Schulweg.pdf"
    render_pdf(html, pdf_path)

    print(f"Erstellt: {pdf_path}")
    basis = "Werktage" if s["fallback"] else "Schultage"
    for richtung in RICHTUNGEN:
        k = s["win"][richtung]
        print(f"  {richtung}: {k['n']} Fahrten an {s['days']} {basis} | "
              f"Verf. {fmt(k['avail'], 1, '%')} | "
              f"pünktlich {fmt(k['ontime'], 1, '%')} | "
              f"Ø Versp. {fmt(k['avg'], 2)} Min.")


if __name__ == "__main__":
    main()
```

The import line added in Step 3 already covers everything `main()` needs
(`prev_month`, `load_month`, `render_pdf`, `MONATE`, `MONATE_DATEI`, `TZ`). No
import changes are required here.

- [ ] **Step 7: Generate a real month and check it fits one page**

Run: `cd factsheet && python schulweg.py --month 2026-07`
Expected: prints `Erstellt: output/S7_Baierbrunn_Juli2026_Schulweg.pdf`, and
**no** `WARNUNG: Inhalt ...px > eine A4-Seite`.

Spot-check the PDF against the spec: → Wolfratshausen window Verfügbarkeit
90,6 %, Ø 5,39 Min., and the 08:00 slot showing Ø 9,50 Min. with 3 Ausfälle.

If the page overflows, reduce padding in `CSS` — never drop an element. This
template is not yet frozen; it becomes frozen once Task 8 records it in
`factsheet/CLAUDE.md`.

- [ ] **Step 8: Commit**

```bash
git add factsheet/schulweg.py factsheet/tests/test_render.py
git commit -m "feat: render the Schulweg one-pager and add its CLI"
```

---

### Task 7: Workflow publishes both PDFs

**Files:**
- Modify: `.github/workflows/monthly-factsheet.yml:43-95`

**Interfaces:**
- Consumes: `schulweg.py`'s CLI from Task 6, which prints `Berichtsmonat: <YYYY-MM>` and an `output/...pdf` path.
- Produces: a release carrying both PDFs.

Four defects to fix, all in the "Datenblatt erzeugen" and "Release
veroeffentlichen" steps:

1. The guards at lines 56-65 live **inside** the first step. A second step would
   run after them and never be checked.
2. `tee gen.log` (lines 52/54) **truncates**. A second `| tee gen.log` would wipe
   `generate.py`'s output and disable the not-finalized guard for the Datenblatt.
3. Line 68 (`YM=`) lacks `head -n1`. With two `Berichtsmonat:` lines it produces
   `"2026-07\n2026-07"`, and `echo "REPORT_YM=$YM" >> "$GITHUB_ENV"` then emits a
   bare `2026-07` line that Actions rejects as invalid format.
4. Line 67 (`PDF=`) takes only the first match, so the release would silently
   carry the Datenblatt alone.

- [ ] **Step 1: Run both generators in one step**

Replace lines 51-55:

```yaml
          if [ -n "$INPUT_MONTH" ]; then
            python generate.py --month "$INPUT_MONTH" 2>&1 | tee gen.log
            python schulweg.py --month "$INPUT_MONTH" 2>&1 | tee -a gen.log
          else
            python generate.py 2>&1 | tee gen.log
            python schulweg.py 2>&1 | tee -a gen.log
          fi
```

`schulweg.py` runs second and appends. It must never run first: `load_month`
calls `sys.exit()` on a fetch failure (`generate.py:58`), and the guards below
expect `generate.py`'s output to be present in the log.

- [ ] **Step 2: Collect both PDF paths and a single month**

Replace lines 66-72:

```yaml
          # PDF-Pfade und Berichtsmonat aus der Generator-Ausgabe ableiten.
          # sort -u, weil beide Generatoren in dieselbe Logdatei schreiben;
          # head -n1 beim Monat, weil beide ihn ausgeben.
          PDFS=$(grep -oE 'output/[^ ]+\.pdf' gen.log | sort -u | sed 's#^#factsheet/#' | tr '\n' ' ')
          YM=$(grep -oE 'Berichtsmonat: [0-9]{4}-[0-9]{2}' gen.log | grep -oE '[0-9]{4}-[0-9]{2}' | head -n1)
          if [ -z "$PDFS" ] || [ -z "$YM" ]; then
            echo "Konnte PDF-Pfade oder Berichtsmonat nicht ermitteln." >&2
            exit 1
          fi
```

- [ ] **Step 3: Export the path list**

Replace lines 75-79:

```yaml
          {
            echo "PDF_PATHS=$PDFS"
            echo "REPORT_YM=$YM"
            echo "RELEASE_TAG=$TAG"
          } >> "$GITHUB_ENV"
```

`$GITHUB_ENV` is line-oriented `KEY=VALUE`, so the list stays space-separated on
one line.

- [ ] **Step 4: Upload both files**

Replace lines 86-94:

```yaml
          TITLE="S7 Baierbrunn Datenblätter ${REPORT_YM}"
          NOTES="Automatisch erzeugt (${REPORT_YM}): Monatsdatenblatt und Schulweg-Datenblatt."
          if gh release view "$RELEASE_TAG" >/dev/null 2>&1; then
            # Release existiert bereits (z. B. Backfill/Re-Run): PDFs ersetzen.
            gh release upload "$RELEASE_TAG" $PDF_PATHS --clobber
          else
            gh release create "$RELEASE_TAG" $PDF_PATHS \
              --title "$TITLE" --notes "$NOTES"
          fi
```

`$PDF_PATHS` is deliberately **unquoted** so it word-splits into two arguments.

- [ ] **Step 5: Verify the log parsing locally**

```bash
cd factsheet
python generate.py --month 2026-07 2>&1 | tee gen.log
python schulweg.py --month 2026-07 2>&1 | tee -a gen.log
PDFS=$(grep -oE 'output/[^ ]+\.pdf' gen.log | sort -u | sed 's#^#factsheet/#' | tr '\n' ' ')
YM=$(grep -oE 'Berichtsmonat: [0-9]{4}-[0-9]{2}' gen.log | grep -oE '[0-9]{4}-[0-9]{2}' | head -n1)
echo "PDFS=[$PDFS]"
echo "YM=[$YM]"
rm gen.log
```

Expected exactly:

```
PDFS=[factsheet/output/S7_Baierbrunn_Juli2026_Datenblatt.pdf factsheet/output/S7_Baierbrunn_Juli2026_Schulweg.pdf ]
YM=[2026-07]
```

`YM` must be a single line. If it prints twice, Step 2 was not applied.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/monthly-factsheet.yml
git commit -m "ci: publish both factsheets and fix log parsing for two generators"
```

---

### Task 8: Documentation, container and freeze declaration

**Files:**
- Modify: `factsheet/CLAUDE.md`
- Modify: `factsheet/Dockerfile:13,20`
- Modify: `factsheet/README.md:14-23,34-38,45-55`
- Modify: `CLAUDE.md` (repo root)
- Modify: `README.md` (repo root)

- [ ] **Step 1: Make the container able to run both sheets**

`factsheet/Dockerfile` line 13 copies only `generate.py`, so
`from generate import ...` would fail. Line 20 hardcodes the entrypoint, so the
new sheet could not be invoked at all.

Replace line 13:

```dockerfile
# Generatoren; Daten werden zur Laufzeit von raw.githubusercontent.com geholt.
COPY generate.py schulweg.py ./
```

Replace lines 19-20:

```dockerfile
# Ohne Argumente laufen beide Generatoren; mit Argumenten (z. B. --month
# 2026-06) werden sie an beide durchgereicht.
ENTRYPOINT ["sh", "-c", "python generate.py \"$@\" && python schulweg.py \"$@\"", "--"]
```

- [ ] **Step 2: Amend `factsheet/CLAUDE.md`**

Four edits. The third is the one that currently forbids this whole change.

1. **"Aufgabe"** (lines 8-17) — step 1 becomes: *"Das Monatsdatenblatt **und**
   das Schulweg-Datenblatt fuer den zuletzt abgeschlossenen Kalendermonat
   erzeugen."*
2. **"Standardablauf"** (lines 19-38) — add `python schulweg.py` alongside every
   `python generate.py` invocation, and list both output filenames.
3. **"Was du NICHT tun sollst"** (lines 136-137) — the bullet currently reads
   *"Nur `output/` und - ausschliesslich bei Schema-Aenderungen - die
   Datenaufbereitung in `generate.py` aendern."* It must permit `schulweg.py`:

   > Nur `output/`, `schulweg.py` und - ausschliesslich bei
   > Schema-Aenderungen - die Datenaufbereitung in `generate.py` aendern.

4. **Network rule** (line 138-139) currently reads *"Keine externen Netzwerkziele
   ausser `raw.githubusercontent.com/s7bb/...` ansprechen."* It must name
   `openholidaysapi.org` as the second permitted target and state that a failure
   there is **non-fatal by design** — the committed `FERIEN` table takes over and
   the sheet says so in its footer.
5. **New section "Schulweg-Datenblatt"** covering:
   - Purpose and window: Mo–Fr 06:30–08:30, both directions, per departure slot.
   - Its own freeze declaration, mirroring lines 40-62: after Task 6 the layout
     is fixed; only the data changes month to month. `CSS`, `kpi_strip`,
     `slot_grid`, `school_spark`, `render_html_schulweg`, the colour values and
     the order/count of the three cards are not to be edited.
   - **Ferien sources:** OpenHolidays API first, committed `FERIEN` table as
     fallback, and the sheet footer always names which one was used. The table
     is regenerated with `python tools/refresh_ferien.py`, never hand-edited.
   - **`FERIEN` maintenance:** refresh the table before `FERIEN_ABGEDECKT`
     expires (currently 2028-01-31). A month outside it aborts the run *only*
     when the API is also unavailable — that combination is deliberate.
   - The Werktage fallback for months with no school days.
   - That `schulweg.py` runs **after** `generate.py`, never before.

- [ ] **Step 3: Update `factsheet/README.md`**

- File tree (lines 14-23): add `schulweg.py`, `requirements-dev.txt`, `pytest.ini`,
  `tests/`, `tools/refresh_ferien.py`.
- Run commands (lines 34-38): add `python schulweg.py` and both output names.
- Workflow description (lines 45-55): both scripts run, the release carries two
  PDFs.
- Add a short "Tests" section:

```markdown
## Tests

```bash
cd factsheet
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

Die Tests decken Kalender, Slot-Zuordnung, Kennzahlen und HTML-Aufbau ab; sie
gehen nicht ins Netz. Das PDF-Rendering wird ueber die Seitenhoehenpruefung in
`render_pdf` verifiziert.
```

- [ ] **Step 4: Update the root `CLAUDE.md`**

- "Layout" tree: add `schulweg.py`, `requirements-dev.txt`, `pytest.ini`,
  `tests/`, `tools/refresh_ferien.py`.
- "Commands": add `python schulweg.py` and the pytest invocation. Replace
  "No test suite" with the pytest command.
- "Architecture": add a paragraph for `schulweg.py` — imports `load_month`,
  `dth`, `dn`, `render_pdf`, `prev_month`, `MONATE`, `MONATE_DATEI`, `TZ` from
  `generate.py`, adds its own calendar, slot bucketing, metrics and template.
- "Critical constraint": state that the freeze now covers two templates, and
  that `generate.py` must not be modified at all by Schulweg work.

- [ ] **Step 5: Update the root `README.md`**

Line 11-12 points at the latest release as "the most recent monthly one-pager".
Change it to say each release carries two PDFs — the Monatsdatenblatt and the
Schulweg-Datenblatt (Morgenverkehr Mo–Fr 06:30–08:30) — and update the
`s7bb/factsheet` row of the repository table.

- [ ] **Step 6: Verify the container builds and runs**

```bash
cd factsheet
docker build -t s7bb-factsheet .
docker run --rm -v "$PWD/output:/app/output" s7bb-factsheet --month 2026-07
```

Expected: both PDFs in `factsheet/output/`, no A4 warning.

If Docker is unavailable, skip and note it — Step 1's correctness is still
checked by review.

- [ ] **Step 7: Commit**

```bash
git add factsheet/CLAUDE.md factsheet/Dockerfile factsheet/README.md CLAUDE.md README.md
git commit -m "docs: document the Schulweg sheet and freeze its template"
```

---

### Task 9: Cross-month verification

**Files:** none modified — this task only runs and inspects.

- [ ] **Step 1: Run the full test suite**

Run: `cd factsheet && python -m pytest tests/ -v -m "not network"`
Expected: 60 passed.

Then the drift check against the live API:

Run: `cd factsheet && python -m pytest tests/ -v -m network`
Expected: 1 passed.

- [ ] **Step 2: Generate every verification month**

```bash
cd factsheet
for m in 2026-05 2026-06 2026-07 2026-08; do
  echo "=== $m"
  python schulweg.py --month "$m"
done
```

Expected for each: `Erstellt: ...`, and **no** `WARNUNG: Inhalt ...px > eine
A4-Seite`. 2026-08 is not finalized upstream and will print the
`noch nicht finalisiert` warning — that is expected here and is exactly what
makes the workflow refuse to publish it.

- [ ] **Step 3: Confirm the May bucketing regression**

May 2026 splits trains across 06:39/06:40/06:41. Open
`output/S7_Baierbrunn_Mai2026_Schulweg.pdf` and confirm the grid shows **exactly
6 rows** with labels `06:40 07:00 07:20 07:40 08:00 08:20` — not 18 rows and not
`06:39`.

- [ ] **Step 4: Confirm the August fallback**

Open `output/S7_Baierbrunn_August2026_Schulweg.pdf`. The header must read
`21 Werktage / keine Schultage im Monat`, the card note must explain the
fallback, and no cell may contain `nan` or `None`.

- [ ] **Step 5: Confirm page 1 is untouched**

```bash
cd /path/to/repo
# generate.py must be untouched since before this branch started.
git diff --stat main... -- factsheet/generate.py
git log --oneline main... -- factsheet/generate.py
```

Expected: both commands print **nothing**. Any output means `generate.py` was
modified, which violates the plan's first global constraint — revert those
changes before continuing.

Then confirm the page-1 output is unchanged:

```bash
cd factsheet
python generate.py --month 2026-07 | tail -n1 > /tmp/nachher.txt
diff /tmp/vorher.txt /tmp/nachher.txt && echo "Datenblatt unveraendert"
```

`/tmp/vorher.txt` is the baseline captured in "Before you start" below. The
`diff` must be empty. Do not transcribe expected figures into this plan — the
only trustworthy baseline is a real run from before the change.

- [ ] **Step 6: Commit the generated PDFs**

```bash
git add factsheet/output/
git commit -m "chore: add July 2026 Datenblatt and Schulweg-Datenblatt"
```

Note: `output/` currently holds only the June Datenblatt, while July is
finalized upstream and due. Committing July here closes that gap. Do **not**
commit the August PDFs — that month is not finalized.

---

## Before you start

Capture the page-1 baseline **on `main`, before Task 1**, so Task 9 Step 5 has
something real to compare against:

```bash
cd factsheet
pip install -r requirements.txt
python -m playwright install --with-deps chromium
python generate.py --month 2026-07 | tail -n1 > /tmp/vorher.txt
cat /tmp/vorher.txt
```

## Notes for the implementer

- **`factsheet/output/` and `.DS_Store`.** The repo has untracked `.DS_Store`
  files at the root and in `factsheet/`. Adding them to `.gitignore` is a
  reasonable drive-by but is not part of this plan; do not bundle it into a
  feature commit.
- **The `FERIEN` table is the one thing this plan cannot verify for you.**
  Task 2 Step 1 is a real research step. If the official dates differ from the
  table, the tests in Task 2 Step 5 will fail loudly for July and August 2026 —
  fix the table, never the test.
- **The one-page budget is the layout's only hard limit.** If a month overflows
  after the template is frozen in Task 8, treat it as a data anomaly and
  investigate the month, per `factsheet/CLAUDE.md:71-75`.
