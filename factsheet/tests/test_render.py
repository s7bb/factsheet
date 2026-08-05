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
