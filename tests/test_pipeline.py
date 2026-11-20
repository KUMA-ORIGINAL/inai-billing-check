import csv
import json

import pytest

import analyze as cli
from billcheck.pipeline import analyze
from helpers import write_csv


@pytest.mark.parametrize("n", range(1, 6))
def test_report_equals_expected(data_dir, n):
    assert analyze(data_dir / f"billing_0{n}.csv").report == json.loads(
        (data_dir / f"billing_0{n}_expected.json").read_text(encoding="utf-8"))


def test_cli_single_file_outputs(data_dir, tmp_path):
    out = tmp_path / "out"
    assert cli.main([str(data_dir / "billing_01.csv"), "--out", str(out)]) == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    anomalies = json.loads((out / "anomalies.json").read_text(encoding="utf-8"))
    assert report["valid_rows"] == 338
    assert [a["datetime"] for a in anomalies] == [a["datetime"] for a in report["anomalies"]]
    assert all({"datetime", "type", "reason", "amount_som", "anomaly_type", "line"} <= set(a) for a in anomalies)
    with (out / "dropped_rows.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["line", "reason", "raw"] and len(rows) == 1 + 7


def test_cli_many_files(data_dir, tmp_path):
    out = tmp_path / "out"
    files = [str(data_dir / "billing_01.csv"), str(data_dir / "billing_02.csv")]
    assert cli.main(files + ["--out", str(out)]) == 0
    assert (out / "billing_01" / "anomalies.json").is_file()
    assert (out / "billing_02" / "report.json").is_file()
    assert (out / "index.html").is_file()


def test_header_only_file(tmp_path):
    out = tmp_path / "out"
    assert cli.main([str(write_csv(tmp_path, [])), "--out", str(out)]) == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert (report["valid_rows"], report["total_som"], report["anomalies"]) == (0, 0.0, [])


def test_missing_file_exit_code(tmp_path, capsys):
    assert cli.main([str(tmp_path / "nope.csv"), "--out", str(tmp_path / "out")]) == 2
    assert "не найден" in capsys.readouterr().err


def test_headerless_file_exit_code(tmp_path):
    path = write_csv(tmp_path, ["2026-09-01 09:32:08,sms,+996700188574,0,0,1.00"], header=False)
    assert cli.main([str(path), "--out", str(tmp_path / "out")]) == 2


def test_anomalies_json_has_explanations(data_dir, tmp_path):
    out = tmp_path / "out"
    assert cli.main([str(data_dir / "billing_03.csv"), "--out", str(out)]) == 0
    anomalies = json.loads((out / "anomalies.json").read_text(encoding="utf-8"))
    night = next(a for a in anomalies if a["anomaly_type"] == "night_charge")
    assert night["line"] == 243 and "62626" in night["explanation_ru"]
    assert "Подписки" in night["advice_ru"] and "Жазылуулар" in night["advice_ky"]


@pytest.mark.parametrize("expected_text", ['[{"datetime": "2026-09-14 01:37:37", "type": "sms"}]',
                                           "{not json", '{"valid_rows": 1}'])
def test_odd_expected_file_next_to_input_does_not_block_outputs(data_dir, tmp_path, expected_text):
    source = tmp_path / "billing_hidden.csv"
    source.write_bytes((data_dir / "billing_03.csv").read_bytes())
    (tmp_path / "billing_hidden_expected.json").write_text(expected_text, encoding="utf-8")
    out = tmp_path / "out"
    assert cli.main([str(source), "--out", str(out)]) == 0
    assert len(json.loads((out / "anomalies.json").read_text(encoding="utf-8"))) == 5
    assert (out / "report.html").is_file()


def test_analyze_function_from_task_text_writes_files(data_dir, tmp_path):
    """ТЗ: analyze(file) → отчёт + anomalies.json — так можно вызвать и из Python."""
    report = cli.analyze(data_dir / "billing_03.csv", out=tmp_path / "out")
    assert report == json.loads((data_dir / "billing_03_expected.json").read_text(encoding="utf-8"))
    assert len(json.loads((tmp_path / "out" / "anomalies.json").read_text(encoding="utf-8"))) == 5
