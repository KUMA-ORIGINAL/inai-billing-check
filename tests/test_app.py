import json
from decimal import Decimal
from pathlib import Path

import pytest
from helpers import DATA_DIR, ch

from billcheck.anomalies import DEFAULT_RULES, REASONS, Rules, find_all, find_international, find_night_charges
from billcheck.app import analyze_upload, family_snapshot, render_markdown, render_print
from billcheck.llm import explain_anomaly, mask_number, template_explanation
from billcheck.parse import BillingFileError
from billcheck.pdf import text_to_csv
from billcheck.pipeline import analyze
from billcheck.rich import checks, radar, rich_report


@pytest.fixture(scope="module")
def snapshot():
    return family_snapshot(DATA_DIR)


def _expected(n: int) -> dict:
    return json.loads((DATA_DIR / f"billing_0{n}_expected.json").read_text(encoding="utf-8"))


# ---------- пороги правил
def test_default_rules_keep_tz_reasons():
    assert DEFAULT_RULES.reasons() is REASONS
    assert Rules.from_dict({}) == DEFAULT_RULES
    assert Rules.from_dict({"z_threshold": "мусор", "unknown": 1, "intl_rate_limit": "Infinity"}) == DEFAULT_RULES


def test_rules_are_clamped_and_change_findings():
    rules = Rules.from_dict({"night_end_hour": 99, "intl_rate_limit": 50, "z_window_days": 1})
    assert (rules.night_end_hour, rules.intl_rate_limit, rules.z_window_days) == (24, Decimal(50), 2)
    call = [ch("2026-09-27 10:40:38", "call", "+971007731297", 99, 0, "66")]
    assert find_international(call) and not find_international(call, rules)
    sms = [ch("2026-09-14 07:30:00", "sms", "62626", 0, 0, "10")]
    assert not find_night_charges(sms) and find_night_charges(sms, Rules(night_end_hour=8))
    assert "до 08:00" in find_night_charges(sms, Rules(night_end_hour=8))[0].reason


# ---------- расширенный отчёт
def test_rich_report_matches_jury_fields_and_adds_screen_data():
    result = analyze(DATA_DIR / "billing_01.csv")
    report = rich_report(result)
    assert {k: report[k] for k in result.report} | {"anomalies": result.report["anomalies"]} == result.report | {
        "anomalies": result.report["anomalies"]}
    assert [{k: a[k] for k in ("datetime", "type", "anomaly_type", "amount_som", "reason")}
            for a in report["anomalies"]] == result.report["anomalies"]
    assert report["summary"] == {"reclaimable_som": 56.0, "spike_excess_som": 290.97, "anomaly_count": 4,
                                 "reclaimable_share_pct": 4.55, "avg_day_som": 41.01}
    night = report["anomalies"][0]
    assert night["anomaly_type"] == "night_charge" and night["reclaimable"] and night["evidence"]["hour"] == 5
    assert [c["hit"] for c in night["context"]] == [False, False, True, False, False]
    assert "8899" in night["explanation_ky"] and night["reason_ky"] and night["advice_ky"]
    spike = next(a for a in report["anomalies"] if a["anomaly_type"] == "day_spike")
    assert not spike["reclaimable"] and spike["evidence"]["day_total"] == 317.25
    assert len(report["rows"]) == report["valid_rows"] and len(report["by_hour"]) == 24
    assert len(report["dropped_log"]) == report["dropped_rows"]
    assert report["tariff"]["worth"] and report["tariff"]["savings_som"] == 320.16


def test_duplicate_evidence_marks_both_lines():
    report = rich_report(analyze(DATA_DIR / "billing_03.csv"))
    dup = next(a for a in report["anomalies"] if a["anomaly_type"] == "duplicate_charge")
    assert dup["evidence"]["gap_sec"] == 53 and dup["evidence"]["first_datetime"] == "2026-09-12 16:55:01"
    assert sum(c["hit"] for c in dup["context"]) == 2


@pytest.mark.parametrize("n", range(1, 6))
def test_checks_all_green_on_open_data(n):
    report = rich_report(analyze(DATA_DIR / f"billing_0{n}.csv"))
    rows = checks(report, _expected(n))
    assert rows and all(r["ok"] for r in rows), [r for r in rows if not r["ok"]]


def test_checks_catch_a_wrong_field():
    report = rich_report(analyze(DATA_DIR / "billing_01.csv"))
    wrong = _expected(1) | {"total_som": 1.0}
    assert not next(r for r in checks(report, wrong) if r["field"] == "total_som")["ok"]
    assert checks(report, None) == []


def test_radar_scores_short_numbers(snapshot):
    rows = {r["number"]: r for r in snapshot["radar"]}
    assert rows["53530"]["subscribers"] == 2 and rows["53530"]["score"] == 47
    assert rows["8899"]["night_share"] == 1.0
    assert rows["7575"]["subscribers"] == 5  # видно только по всей семье
    assert snapshot["radar"][0]["score"] >= snapshot["radar"][-1]["score"]
    assert radar([]) == []


# ---------- приложение
def test_family_snapshot(snapshot):
    assert snapshot["family"] == "Семья Осмоновых"
    assert [m["role"] for m in snapshot["members"]][0] == "Бабушка"
    assert all(m["content"] and all(c["ok"] for c in m["checks"]) for m in snapshot["members"])


def test_analyze_upload_with_settings_and_expected():
    content = (DATA_DIR / "billing_03.csv").read_text(encoding="utf-8")
    res = analyze_upload({"filename": "billing_03.csv", "content": content, "expected": _expected(3)})
    assert res["report"]["summary"]["reclaimable_som"] == 65.0 and all(c["ok"] for c in res["checks"])
    strict = analyze_upload({"filename": "b.csv", "content": content, "settings": {"intl_rate_limit": 50}})
    assert "international_rate" not in {a["anomaly_type"] for a in strict["report"]["anomalies"]}
    assert strict["report"]["meta"]["settings"]["intl_rate_limit"] == 50.0


def test_live_duplicate_is_caught():
    content = (DATA_DIR / "billing_05.csv").read_text(encoding="utf-8").rstrip() + "\n" + \
        "01.09.2026 12:00:00,call,+996700000001,60,0,\"1,20\"\n01.09.2026 12:00:20,call,+996700000001,60,0,1.20\n"
    res = analyze_upload({"filename": "billing_05.csv", "content": content})
    assert any(a["anomaly_type"] == "duplicate_charge" and a["datetime"] == "2026-09-01 12:00:20"
               for a in res["report"]["anomalies"])


@pytest.mark.parametrize("body", [{"filename": "a.csv", "content": ""}, {"filename": "a.csv", "content_b64": "!!"},
                                  {"filename": "a.csv", "content_b64": "//79"}, None])
def test_analyze_upload_rejects_bad_input(body):
    with pytest.raises(BillingFileError):
        analyze_upload(body)


def test_pdf_text_rows_become_csv(tmp_path):
    text = "INAI MOBILE · Детализация\n2026-09-01 09:32:08 sms +996700188574 0 0 1,00\n" \
           "01.09.2026 14:41:43 data 1501 38,8 1,94\nИтого 2,94\n2026-09-02 10:00:00 content 7575 0 0 15\n"
    csv_text = text_to_csv(text)
    path = tmp_path / "from_pdf.csv"
    path.write_text(csv_text, encoding="utf-8")
    result = analyze(path)
    assert result.report["valid_rows"] == 3 and result.report["total_som"] == 17.94


def test_pdf_without_pdfplumber_explains_itself():
    import base64
    try:
        import pdfplumber  # noqa: F401
        pytest.skip("pdfplumber установлен")
    except ImportError:
        pass
    with pytest.raises(BillingFileError, match="pdfplumber"):
        analyze_upload({"filename": "bill.pdf", "content_b64": base64.b64encode(b"%PDF-1.4").decode()})


def test_markdown_and_print_reports():
    report = rich_report(analyze(DATA_DIR / "billing_03.csv"))
    md = render_markdown(report, "Мама")
    assert md.startswith("# Акчам кайда? — Мама") and "| 2026-09-12 16:55:54 | Двойное списание |" in md
    assert "Можно платить меньше" in md
    page = render_print(report, "Прошу вернуть <b>65</b>")
    assert "<script" not in page and "&lt;b&gt;65&lt;/b&gt;" in page


# ---------- ИИ: «объяснить проще»
def _anomaly() -> dict:
    return rich_report(analyze(DATA_DIR / "billing_01.csv"))["anomalies"][3]  # +971, 33 сом


def test_mask_number():
    assert mask_number("+996777165026") == "+99677••••26" and mask_number("7575") == "7575"


def test_explain_uses_template_without_llm():
    a = _anomaly()
    assert template_explanation(a, "ky")["text"].startswith(a["explanation_ky"])
    assert explain_anomaly(a, "ru", lambda s, u: None)["source"] == "template"


def test_explain_rejects_invented_numbers_and_masks_input():
    seen = {}

    def fake(system, user):
        seen["user"] = user
        return "Звонок стоил 999 сом — это ошибка."
    assert explain_anomaly(_anomaly(), "ru", fake)["source"] == "template"
    assert "+971007731297" not in seen["user"] and "+97100••••97" in seen["user"]
    ok = explain_anomaly(_anomaly(), "ru", lambda s, u: "Минута стоила 40 сом вместо 20. Уточните тариф у оператора.")
    assert ok == {"text": "Минута стоила 40 сом вместо 20. Уточните тариф у оператора.", "source": "llm"}


# ---------- скрытый файл: перестановки и форматы не меняют результат
def _fuzz(content: str, seed: int) -> str:
    """Скрытый файл «как попало»: строки перемешаны, половина дат в форме ДД.ММ.ГГГГ, суммы с запятой."""
    import random
    rng = random.Random(seed)
    head, *rows = content.splitlines()
    out = []
    for index, row in enumerate(rows):
        cells = row.split(",")
        if len(cells) == 6 and cells[0][:4].isdigit() and "-" in cells[0][:5]:
            if rng.random() < 0.5:
                d, t = cells[0].split(" ")
                y, m, dd = d.split("-")
                cells[0] = f"{dd}.{m}.{y} {t}"
            if rng.random() < 0.5 and "." in cells[5] and not cells[5].startswith('"'):
                cells[5] = '"' + cells[5].replace(".", ",") + '"'
            row = ",".join(cells)
        out.append((index, row))
    rng.shuffle(out)
    # «Новая подписка» по уточнениям — первая В ФАЙЛЕ (а не по времени), поэтому строки подписок
    # остаются в исходном порядке относительно друг друга; всё остальное перемешано.
    slots = [i for i, (_, row) in enumerate(out) if ",subscription," in row]
    for slot, item in zip(slots, sorted(out[i] for i in slots)):
        out[slot] = item
    return "\n".join([head, *(row for _, row in out)]) + "\n"


@pytest.mark.parametrize("n,seed", [(n, s) for n in range(1, 6) for s in (1, 2)])
def test_fuzzed_file_gives_same_answer(tmp_path, n, seed):
    source = DATA_DIR / f"billing_0{n}.csv"
    fuzzed = tmp_path / source.name
    fuzzed.write_text(_fuzz(source.read_text(encoding="utf-8"), seed), encoding="utf-8")
    original, shuffled = analyze(source), analyze(fuzzed)
    assert shuffled.report == original.report | {"anomalies": shuffled.report["anomalies"]}
    key = lambda a: (a["datetime"], a["anomaly_type"], a["amount_som"])  # noqa: E731
    assert sorted(map(key, shuffled.report["anomalies"])) == sorted(map(key, original.report["anomalies"]))
    assert find_all(shuffled.charges) and Path(fuzzed).exists()
