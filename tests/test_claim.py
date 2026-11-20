from datetime import date

from billcheck.claim import build_claim
from billcheck.pipeline import analyze


def test_claim_billing_03(data_dir):
    text = build_claim(analyze(data_dir / "billing_03.csv"), today=date(2026, 11, 21))
    assert "INAI Mobile" in text
    assert "Прошу провести проверку и перерасчёт по следующим списаниям:" in text
    for position in ("1. ", "2. ", "3. ", "4. "):
        assert f"\n{position}" in text
    assert "\n5. " not in text
    assert "Итого к проверке: 65.00 сом" in text
    assert "z-score" not in text and "29.09.2026" not in text
    assert "строка 243" in text and "62626" in text
    assert "Дата составления: 21.11.2026" in text
    assert "________" in text  # ФИО и номер не заполнены


def test_claim_selected_lines(data_dir):
    text = build_claim(analyze(data_dir / "billing_03.csv"), selected_lines={243})
    assert "Итого к проверке: 10.00 сом" in text and "\n2. " not in text


def test_claim_fills_name_and_number(data_dir):
    text = build_claim(analyze(data_dir / "billing_03.csv"), msisdn="+996700000000", full_name="Иванова А.")
    assert "Иванова А." in text and "+996700000000" in text


def test_claim_international_shows_cost_and_overpay(data_dir):
    text = build_claim(analyze(data_dir / "billing_03.csv"))
    line = next(row for row in text.splitlines() if "+971" in row)
    assert "к перерасчёту 41.00 сом" in line
