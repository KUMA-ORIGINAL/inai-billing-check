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
