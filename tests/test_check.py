import json

import check


def _anoms(*days):
    return [{"datetime": f"2026-09-{d:02d} 00:00:00", "type": "sms", "anomaly_type": "night_charge",
             "reason": "x", "amount_som": 1.0} for d in days]


def test_check_rules():
    expected = _anoms(1, 2, 3, 4, 5)
    ok = check.compare(_anoms(1, 2, 3, 4, 20, 21), expected)
    assert (ok["recall"], len(ok["missed"]), len(ok["false_positives"]), ok["passed"]) == (0.8, 1, 2, True)
    assert check.compare(_anoms(1, 2, 3), expected)["passed"] is False
    assert check.compare(_anoms(1, 2, 3, 4, 5, 20, 21, 22), expected)["passed"] is False


def test_match_without_anomaly_type():
    found = [{"datetime": "2026-09-01 00:00:00", "type": "sms", "reason": "ночью"}]
    expected = _anoms(1)
    assert check.compare(found, expected)["passed"] is True


def test_cli_on_open_data(data_dir, tmp_path, capsys):
    import analyze as cli
    out = tmp_path / "out"
    assert cli.main([str(data_dir / "billing_03.csv"), "--out", str(out)]) == 0
    capsys.readouterr()
    assert check.main([str(out / "anomalies.json"), str(data_dir / "billing_03_expected.json")]) == 0
    text = capsys.readouterr().out
    assert "ЗАЧЁТ" in text and "5 из 5" in text and "ложных: 0" in text
    assert "valid_rows" in text  # сверка полей отчёта, раз рядом лежит report.json


def test_expected_as_object_or_list(tmp_path):
    expected = _anoms(1, 2)
    (tmp_path / "a.json").write_text(json.dumps(expected), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps({"anomalies": expected}), encoding="utf-8")
    assert check.load_anomalies(tmp_path / "a.json") == check.load_anomalies(tmp_path / "b.json") == expected
