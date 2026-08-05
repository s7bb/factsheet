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
