import json
import re

import analyze as cli
from billcheck.html import render_report, report_payload
from billcheck.pipeline import analyze
from helpers import write_csv


def _payload(page: str) -> dict:
    match = re.search(r'<script id="bill-data" type="application/json">(.*?)</script>', page, re.S)
    return json.loads(match.group(1))


def test_report_html_self_contained(data_dir):
    page = render_report(analyze(data_dir / "billing_03.csv"), profile="Бабушка")
    assert "<script src" not in page and "__BILL_DATA__" not in page
    for dt in ("2026-09-07 17:54:43", "2026-09-12 16:55:54", "2026-09-14 01:37:37",
               "2026-09-23 12:18:37", "2026-09-29 00:00:00"):
        assert dt in page
    data = _payload(page)
    assert data["profile"] == "Бабушка" and data["overpay_text"] == "65,00"
    assert sum(p["cents"] for p in data["claim"]["positions"]) == 6500


def test_report_html_escapes_script(tmp_path):
    path = write_csv(tmp_path, ["2026-09-01 10:00:00,sms,</script><b>x,0,0,1.00"])
    page = render_report(analyze(path))
    assert "</script><b>" not in page
    assert _payload(page)["days"][0]["lines"][0]["number"] == "</script><b>x"


def test_payload_receipt_and_marks(data_dir):
    data = report_payload(analyze(data_dir / "billing_03.csv"))
    assert len(data["days"]) == 30
    assert sum(len(d["lines"]) for d in data["days"]) == 596
    night = next(line for d in data["days"] for line in d["lines"] if line["line"] == 243)
    assert night["flags"] and night["raw"] == "14.09.2026 01:37:37,sms,62626,0,0,10.00"
    spike_day = next(d for d in data["days"] if d["date"] == "2026-09-29")
    assert spike_day["spike"] is True
    assert [row["reason"] for row in data["dropped"]][:1] and all(row["reason_ru"] for row in data["dropped"])


def test_payload_checklist_has_live_numbers(data_dir):
    data = report_payload(analyze(data_dir / "billing_03.csv"))
    text = json.dumps(data["checklist"], ensure_ascii=False)
    assert "596" in text and "8" in text and "Эталон организаторов" in text and "5 из 5" in text


def test_cli_writes_report_html(data_dir, tmp_path):
    out = tmp_path / "out"
    assert cli.main([str(data_dir / "billing_03.csv"), "--out", str(out)]) == 0
    page = (out / "report.html").read_text(encoding="utf-8")
    assert _payload(page)["profile"] == "Бабушка"


def test_report_html_survives_html_comment_in_data(tmp_path):
    path = write_csv(tmp_path, ["2026-09-01 10:00:00,sms,<!--x,0,0,1.00", "2026-09-01 11:00:00,sms,<script>,0,0,1.00"])
    page = render_report(analyze(path))
    data = _payload(page)  # json.loads не падает — значит и JSON.parse в браузере не упадёт
    assert [line["number"] for line in data["days"][0]["lines"]] == ["<!--x", "<script>"]
    assert "<!--x" not in page and "<script>," not in page
