import json
from datetime import date
from decimal import Decimal

import pytest

from billcheck.parse import read_billing
from billcheck.report import daily_totals, normalize_number, summarize
from helpers import ch


@pytest.mark.parametrize("n", range(1, 6))
def test_summary_matches_expected(data_dir, n):
    charges, bad = read_billing(data_dir / f"billing_0{n}.csv")
    expected = json.loads((data_dir / f"billing_0{n}_expected.json").read_text(encoding="utf-8"))
    expected.pop("anomalies")
    assert summarize(charges, len(bad)) == expected


def test_control_values(data_dir):
    first = summarize(*_read(data_dir, 1))
    fifth = summarize(*_read(data_dir, 5))
    assert first["total_som"] == 1230.16
    assert fifth["top5_numbers"][0] == {"number": "+996220863991", "cost_som": 577.0}


def _read(data_dir, n):
    charges, bad = read_billing(data_dir / f"billing_0{n}.csv")
    return charges, len(bad)


def test_zero_days_and_all_categories():
    charges = [ch("2026-09-03 10:00:00", "sms", "+996700000001", 0, 0, "1.50"),
               ch("2026-09-01 10:00:00", "call", "+996700000002", 60, 0, "2")]
    summary = summarize(charges, 0)
    assert summary["by_day"] == {"2026-09-01": 2.0, "2026-09-02": 0.0, "2026-09-03": 1.5}
    assert summary["by_category"] == {"call": 2.0, "sms": 1.5, "data": 0.0, "subscription": 0.0, "content": 0.0}


def test_series_starts_on_first_of_month():
    totals = daily_totals([ch("2026-09-04 10:00:00", "sms", "", 0, 0, "1")])
    assert list(totals) == [date(2026, 9, d) for d in range(1, 5)]
    assert totals[date(2026, 9, 1)] == Decimal(0)


def test_duplicates_are_not_removed():
    same = ch("2026-09-05 12:00:00", "call", "+996700000003", 60, 0, "6.00")
    summary = summarize([same, same], 0)
    assert summary["total_som"] == 12.0 and summary["valid_rows"] == 2


def test_top5_merges_local_formats_and_skips_empty():
    charges = [ch("2026-09-01 10:00:00", "call", "996700000004", 60, 0, "3"),
               ch("2026-09-01 11:00:00", "call", "+996700000004", 60, 0, "4"),
               ch("2026-09-01 12:00:00", "data", "", 0, 50, "100"),
               ch("2026-09-01 13:00:00", "sms", "+996700000009", 0, 0, "7"),
               ch("2026-09-01 14:00:00", "sms", "+996700000001", 0, 0, "7")]
    top = summarize(charges, 0)["top5_numbers"]
    assert top == [{"number": "+996700000001", "cost_som": 7.0},
                   {"number": "+996700000004", "cost_som": 7.0},
                   {"number": "+996700000009", "cost_som": 7.0}]


def test_empty_charges():
    summary = summarize([], 3)
    assert (summary["valid_rows"], summary["dropped_rows"], summary["total_som"]) == (0, 3, 0.0)
    assert summary["by_day"] == {} and summary["top5_numbers"] == []


@pytest.mark.parametrize("raw, normalized", [
    ("996700123456", "+996700123456"), ("+996700123456", "+996700123456"),
    ("7575", "7575"), ("+971007731297", "+971007731297"), ("", "")])
def test_normalize_number(raw, normalized):
    assert normalize_number(raw) == normalized
