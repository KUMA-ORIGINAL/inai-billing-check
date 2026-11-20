import json

import pytest

from billcheck.family import family_summary, load_profiles, number_reputation, profile_name, self_check
from billcheck.pipeline import analyze
from helpers import DATA_DIR


@pytest.fixture(scope="module")
def results():
    return [analyze(p) for p in sorted(DATA_DIR.glob("billing_0*.csv"))]


def test_7575_everywhere(results):
    top = number_reputation(results)[0]
    assert (top["number"], top["members"], top["members_total"], top["charges"], top["total_som"]) == \
        ("7575", 5, 5, 7, 85.0)
    assert (top["types"], top["night"], top["in_rules"]) == (["content"], 0, 0)


def test_reputation_only_short_numbers(results):
    numbers = [row["number"] for row in number_reputation(results)]
    assert numbers and all(n.isdigit() and 3 <= len(n) <= 6 for n in numbers)


def test_reputation_not_in_anomalies(results):
    for result in results:
        assert all(a.charge is None or a.charge.number != "7575" for a in result.anomalies)


def test_self_check_open_data(results, data_dir):
    assert self_check(results, data_dir) == {"files": 5, "reports_equal": 5, "anomalies_expected": 20,
                                             "found": 20, "false_positives": 0}


def test_self_check_none_without_expected(results, tmp_path):
    assert self_check(results, tmp_path) is None


def test_family_summary(results, data_dir):
    rows = family_summary(results, load_profiles(data_dir))
    assert [r["name"] for r in rows] == ["Я", "Папа", "Бабушка", "Мама", "Брат"]
    grandma = rows[2]
    assert (grandma["file"], grandma["total_som"], grandma["overpay_som"], grandma["anomalies"],
            grandma["new_subscription"]) == ("billing_03.csv", 2106.02, 65.0, 5, True)
    assert rows[1]["new_subscription"] is False


def test_family_totals(results, data_dir):
    rows = family_summary(results, load_profiles(data_dir))
    assert round(sum(r["total_som"] for r in rows), 2) == 8285.42
    assert round(sum(r["overpay_som"] for r in rows), 2) == 204.26
    assert sum(r["anomalies"] for r in rows) == 20


def test_profiles_fallback(tmp_path, data_dir):
    assert load_profiles(tmp_path) == {}
    (tmp_path / "family.json").write_text(json.dumps({"a.csv": "Мама"}, ensure_ascii=False), encoding="utf-8")
    profiles = load_profiles(tmp_path)
    assert profile_name(profiles, data_dir / "a.csv") == "Мама"
    assert profile_name(profiles, data_dir / "billing_09.csv") == "billing_09"
