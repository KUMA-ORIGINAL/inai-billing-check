import json
import re

import pytest

import analyze as cli
from billcheck.family import load_profiles
from billcheck.html import family_payload, render_family
from billcheck.pipeline import analyze
from helpers import DATA_DIR


@pytest.fixture(scope="module")
def results():
    return [analyze(p) for p in sorted(DATA_DIR.glob("billing_0*.csv"))]


def _payload(page: str) -> dict:
    match = re.search(r'<script id="bill-data" type="application/json">(.*?)</script>', page, re.S)
    return json.loads(match.group(1))


def test_family_page_has_profiles_and_reputation(results):
    links = [f"{r.source.stem}/report.html" for r in results]
    page = render_family(results, load_profiles(DATA_DIR), links, DATA_DIR)
    assert "<script src" not in page and "__BILL_DATA__" not in page
    data = _payload(page)
    assert [m["name"] for m in data["members"]] == ["Я", "Папа", "Бабушка", "Мама", "Брат"]
    assert data["members"][2]["link"] == "billing_03/report.html"
    assert data["totals"]["overpay_text"] == "204,26" and data["totals"]["total_text"] == "8\u00a0285,42"
    top = data["reputation"][0]
    assert top["number"] == "7575" and top["members_text"] == "у 5 из 5" and top["unseen_by_rules"] is True
    assert top["by_member"] == [30.0, 15.0, 10.0, 20.0, 10.0]


def test_self_check_badge(results):
    data = family_payload(results, load_profiles(DATA_DIR), ["#"] * 5, DATA_DIR)
    assert data["self_check"] == {"files": 5, "reports_equal": 5, "anomalies_expected": 20, "found": 20,
                                  "false_positives": 0}


def test_self_check_badge_hidden_without_expected(results, tmp_path):
    assert family_payload(results, {}, ["#"] * 5, tmp_path)["self_check"] is None


def test_cli_index_is_family_page(tmp_path):
    out = tmp_path / "out"
    assert cli.main([str(DATA_DIR), "--out", str(out)]) == 0
    data = _payload((out / "index.html").read_text(encoding="utf-8"))
    assert len(data["members"]) == 5 and data["members"][0]["link"] == "billing_01/report.html"
    report = _payload((out / "billing_03" / "report.html").read_text(encoding="utf-8"))
    assert report["back_link"] == {"href": "../index.html", "label": "← Вся семья"}


def test_family_payload_has_operator_advice(results):
    data = family_payload(results, load_profiles(DATA_DIR), ["#"] * 5, DATA_DIR)
    assert "Подписки" in data["advice_ru"] and "Жазылуулар" in data["advice_ky"]
