import json
from decimal import Decimal

import pytest

from billcheck.anomalies import (REASONS, find_all, find_day_spikes, find_duplicates, find_international,
                                 find_new_subscription, find_night_charges)
from billcheck.parse import read_billing
from helpers import ch


def test_night_boundaries():
    found = find_night_charges([ch("2026-09-05 00:00:00", "content", "1414", 0, 0, "10"),
                                ch("2026-09-05 05:59:59", "sms", "8899", 0, 0, "15"),
                                ch("2026-09-05 06:00:00", "sms", "8899", 0, 0, "15"),
                                ch("2026-09-05 03:00:00", "call", "+996700000000", 60, 0, "2"),
                                ch("2026-09-05 02:00:00", "sms", "+996700000000", 0, 0, "0")])
    assert [a.amount for a in found] == [Decimal("10"), Decimal("15")]
    assert found[0].as_dict() == {"datetime": "2026-09-05 00:00:00", "type": "content",
                                  "anomaly_type": "night_charge", "amount_som": 10.0,
                                  "reason": REASONS["night_charge"]}


def test_only_first_subscription_in_file():
    found = find_new_subscription([ch("2026-09-30 12:23:29", "subscription", "53530", 0, 0, "8.00", line=334),
                                   ch("2026-09-23 12:00:35", "subscription", "53530", 0, 0, "8.00", line=263)])
    assert len(found) == 1
    assert (found[0].line, found[0].amount) == (263, Decimal("8.00"))


@pytest.mark.parametrize("number, flagged", [
    ("53530", True), ("777", True), ("123456", True),
    ("12", False), ("1234567", False), ("+53530", False), ("53a30", False), ("", False)])
def test_subscription_number_length(number, flagged):
    found = find_new_subscription([ch("2026-09-23 12:00:00", "subscription", number, 0, 0, "8")])
    assert bool(found) is flagged


def test_duplicate_across_formats():
    found = find_duplicates([ch("2026-09-12 16:55:54", "call", "+996700395431", 214, 0, "6.00", line=208),
                             ch("2026-09-12 16:55:01", "call", "+996700395431", 214, 0, "6", line=207)])
    assert [(a.line, a.dt.isoformat(" "), a.amount) for a in found] == [(208, "2026-09-12 16:55:54", Decimal("6.00"))]
    assert found[0].as_dict()["anomaly_type"] == "duplicate_charge"


def test_duplicate_chain_of_three():
    rows = [ch(f"2026-09-12 10:0{m}:{s}", "sms", "+996700000001", 0, 0, "2", line=i)
            for i, (m, s) in enumerate([("0", "00"), ("0", "30"), ("1", "00")], start=2)]
    assert [a.line for a in find_duplicates(rows)] == [3, 4]


def test_duplicate_window_is_inclusive():
    at_60 = [ch("2026-09-12 10:00:00", "sms", "+996700000001", 0, 0, "2"),
             ch("2026-09-12 10:01:00", "sms", "+996700000001", 0, 0, "2")]
    at_61 = [ch("2026-09-12 10:00:00", "sms", "+996700000001", 0, 0, "2"),
             ch("2026-09-12 10:01:01", "sms", "+996700000001", 0, 0, "2")]
    assert len(find_duplicates(at_60)) == 1 and find_duplicates(at_61) == []


def test_duplicate_needs_all_fields_equal():
    rows = [ch("2026-09-12 10:00:00", "call", "+996700000001", 60, 0, "2"),
            ch("2026-09-12 10:00:10", "call", "+996700000001", 61, 0, "2"),
            ch("2026-09-12 10:00:20", "call", "+996700000002", 60, 0, "2"),
            ch("2026-09-12 10:00:30", "sms", "+996700000001", 60, 0, "2")]
    assert find_duplicates(rows) == []


def test_international_rate():
    found = find_international([ch("2026-09-27 10:40:38", "call", "+971007731297", 99, 0, "66"),
                                ch("2026-09-28 17:46:15", "call", "+1914035016", 115, 0, "47.92"),
                                ch("2026-09-28 18:00:00", "call", "+971007731297", 60, 0, "20")])
    assert [a.as_dict()["amount_som"] for a in found] == [33.0, 9.59]


def test_local_number_without_plus():
    assert find_international([ch("2026-09-27 10:40:38", "call", "996700000000", 60, 0, "50"),
                               ch("2026-09-27 10:41:38", "call", "+996700000000", 60, 0, "50")]) == []


def test_international_zero_duration():
    assert find_international([ch("2026-09-27 10:40:38", "call", "+971007731297", 0, 0, "50")]) == []


# --- Task 4: всплеск расходов за день и полный список ---------------------------------------

def _days(costs: dict[int, str]) -> list:
    return [ch(f"2026-09-{day:02d} 12:00:00", "call", "+996700000001", 60, 0, cost)
            for day, cost in costs.items()]


def test_first_seven_days_not_checked():
    assert find_day_spikes(_days({1: "1", 2: "1", 3: "1", 4: "1", 5: "1", 6: "1", 7: "100"})) == []
    found = find_day_spikes(_days({1: "1", 2: "1", 3: "1", 4: "1", 5: "1", 6: "1", 7: "1", 8: "100"}))
    assert [a.as_dict() for a in found] == [{
        "datetime": "2026-09-08 00:00:00", "type": "day_spike", "anomaly_type": "day_spike",
        "amount_som": 99.0, "reason": REASONS["day_spike"]}]
    assert (found[0].line, found[0].charge) == (None, None)


def test_zero_days_count_in_window():
    found = find_day_spikes(_days({8: "5"}))
    assert [(a.dt.day, a.as_dict()["amount_som"]) for a in found] == [(8, 5.0)]


def test_flat_days_no_spike():
    assert find_day_spikes(_days({d: "10" for d in range(1, 9)})) == []


def test_population_std():
    # pstdev окна ≈ 0.98974 → z ≈ 3.18 > 3 (с выборочным std было бы ≈ 2.94 — не всплеск)
    week = {1: "10", 2: "12", 3: "10", 4: "12", 5: "10", 6: "12", 7: "10"}
    assert [a.as_dict()["amount_som"] for a in find_day_spikes(_days(week | {8: "14"}))] == [3.14]
    assert find_day_spikes(_days(week | {8: "13"})) == []


@pytest.mark.parametrize("n", range(1, 6))
def test_all_anomalies_match_expected(data_dir, n):
    charges, _ = read_billing(data_dir / f"billing_0{n}.csv")
    expected = json.loads((data_dir / f"billing_0{n}_expected.json").read_text(encoding="utf-8"))["anomalies"]
    assert [a.as_dict() for a in find_all(charges)] == expected


def test_open_data_has_twenty_anomalies(data_dir):
    total = sum(len(find_all(read_billing(data_dir / f"billing_0{n}.csv")[0])) for n in range(1, 6))
    assert total == 20


@pytest.mark.parametrize("stray", ["2026-08-31 23:58:00,call,+996700000000,60,0,1",
                                   "2016-09-15 12:00:00,call,+996700000000,60,0,1",
                                   "2026-10-15 12:00:00,call,+996700000000,60,0,3"])
def test_stray_row_from_another_month_adds_no_spikes(data_dir, tmp_path, stray):
    text = (data_dir / "billing_03.csv").read_text(encoding="utf-8")
    path = tmp_path / "billing_03_stray.csv"
    path.write_text(text.rstrip("\n") + "\n" + stray + "\n", encoding="utf-8")
    expected = json.loads((data_dir / "billing_03_expected.json").read_text(encoding="utf-8"))["anomalies"]
    assert [a.as_dict() for a in find_all(read_billing(path)[0])] == expected
