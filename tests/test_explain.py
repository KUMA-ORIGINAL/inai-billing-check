import json
from datetime import datetime
from decimal import Decimal

from billcheck.anomalies import REASONS, Anomaly, find_day_spikes, find_duplicates, find_international
from billcheck.explain import advice, explain, possible_overpay
from billcheck.pipeline import analyze
from helpers import ch


def _faq(data_dir, faq_id):
    return next(x for x in json.loads((data_dir / "faq.json").read_text(encoding="utf-8")) if x["id"] == faq_id)


def test_explain_has_numbers():
    [a] = find_international([ch("2026-09-27 10:40:38", "call", "+971007731297", 99, 0, "66")])
    text = explain(a)
    assert "+971007731297" in text and "40,00 сом/мин" in text and "33,00 сом" in text


def test_explain_duplicate_gap():
    [a] = find_duplicates([ch("2026-09-12 16:55:01", "call", "+996700395431", 214, 0, "6"),
                           ch("2026-09-12 16:55:54", "call", "+996700395431", 214, 0, "6.00")])
    text = explain(a)
    assert "12.09" in text and "16:55:54" in text and "53 с" in text and "6,00 сом" in text


def test_explain_day_spike_ratio():
    days = [ch(f"2026-09-0{d} 12:00:00", "call", "+996700000001", 60, 0, "10") for d in range(1, 8)]
    [a] = find_day_spikes(days + [ch("2026-09-08 12:00:00", "call", "+996700000001", 60, 0, "50")])
    text = explain(a)
    assert "08.09" in text and "50,00 сом" in text and "в 5,0 раза" in text and "10,00 сом" in text


def test_every_open_anomaly_is_explained(data_dir):
    for n in range(1, 6):
        for a in analyze(data_dir / f"billing_0{n}.csv").anomalies:
            assert explain(a) and advice(a, "ru") and advice(a, "ky")


def test_advice_from_faq_ru_ky(data_dir):
    night = Anomaly(datetime(2026, 9, 14, 1, 37, 37), "sms", "night_charge", Decimal(10), REASONS["night_charge"], 243)
    spike = Anomaly(datetime(2026, 9, 29), "day_spike", "day_spike", Decimal(1), REASONS["day_spike"])
    assert advice(night, "ky") == _faq(data_dir, 8)["answer_ky"]
    assert advice(night) == _faq(data_dir, 8)["answer_ru"]
    assert advice(spike, "ru") == _faq(data_dir, 15)["answer_ru"]


def test_overpay_no_double_count():
    def anomaly(kind, amount, line):
        return Anomaly(datetime(2026, 9, 5), "sms", kind, Decimal(amount), REASONS[kind], line)
    anomalies = [anomaly("night_charge", "15", 10),
                 Anomaly(datetime(2026, 9, 25), "day_spike", "day_spike", Decimal("290.97"), REASONS["day_spike"]),
                 anomaly("night_charge", "10", 20),
                 anomaly("duplicate_charge", "12", 20)]
    assert possible_overpay(anomalies) == Decimal("27.00")


def test_overpay_billing_03(data_dir):
    assert possible_overpay(analyze(data_dir / "billing_03.csv").anomalies) == Decimal("65.00")
