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
