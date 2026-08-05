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
