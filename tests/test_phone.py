import json
import re

from billcheck.html import render_report
from billcheck.pipeline import analyze


def _payload(page: str) -> dict:
    return json.loads(re.search(r'<script id="bill-data" type="application/json">(.*?)</script>', page, re.S).group(1))


def test_phone_lists_this_subscriber_numbers(data_dir):
    page = render_report(analyze(data_dir / "billing_03.csv"), "Бабушка")
    phone = _payload(page)["phone"]
    numbers = [row["number"] for row in phone["numbers"]]
    assert "53530" in numbers and "62626" in numbers and "7799" not in numbers
    sub = next(row for row in phone["numbers"] if row["number"] == "53530")
    assert sub["total_text"] == "16,00" and sub["charges"] == 2
    assert "Демо" in page
    assert "Подписки" in phone["advice_ru"] and "Жазылуулар" in phone["advice_ky"]


def test_phone_has_no_ussd_codes(data_dir):
    page = render_report(analyze(data_dir / "billing_03.csv"))
    phone_markup = page[page.index('id="phone"'):page.index("</dialog>")]
    assert not re.search(r"\*\d+[#*]", phone_markup)


def test_phone_empty_without_short_numbers(tmp_path):
    path = tmp_path / "b.csv"
    path.write_text("datetime,type,number,duration_sec,mb,cost_som\n2026-09-01 10:00:00,call,+996700000001,60,0,2\n",
                    encoding="utf-8")
    assert _payload(render_report(analyze(path)))["phone"]["numbers"] == []
