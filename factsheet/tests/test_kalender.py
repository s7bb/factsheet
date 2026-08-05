import datetime as dt
import json

import pytest

import schulweg
from schulweg import (FERIEN, FERIEN_ABGEDECKT, MIN_FERIEN_PRO_JAHR,
                      QUELLE_API, easter, feiertage, ferien_api, ferien_ranges,
                      ist_ferientag, pruefe_abdeckung, tage_im_monat)


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
    """Jeder Zeitraum muss INNERHALB der Abdeckung beginnen.

    Das Ende darf darueber hinausragen: die Weihnachtsferien beginnen im
    Dezember und laufen ins Folgejahr (z. B. 2028-12-23..2029-01-05). Ohne
    diesen Eintrag waere ein Dezember-Blatt am Rand der Abdeckung falsch.
    """
    lo, hi = (dt.date.fromisoformat(x) for x in FERIEN_ABGEDECKT)
    for a, b in FERIEN:
        start, ende = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
        assert lo <= start <= hi, f"{a}..{b} beginnt ausserhalb der Abdeckung"
        assert ende >= lo, f"{a}..{b} endet vor Beginn der Abdeckung"


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
    assert fallback is False


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
    """Faengt Drift zwischen beiden Pfaden ab, bevor sie in ein PDF geraet.

    Ueber refresh_ferien.hole(), nicht ueber ferien_api(): die Abdeckung ist
    inzwischen laenger als die drei Jahre, die eine einzelne API-Abfrage
    zulaesst. hole() zerlegt das Fenster und fuehrt die Teile zusammen -
    genau so ist die committete Tabelle entstanden.
    """
    import pathlib
    import sys as _sys
    _sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
    import refresh_ferien

    von, bis = (dt.date.fromisoformat(x) for x in FERIEN_ABGEDECKT)
    live = [(s, e) for s, e, _ in refresh_ferien.hole(von, bis)]
    assert live == [tuple(r) for r in FERIEN]
