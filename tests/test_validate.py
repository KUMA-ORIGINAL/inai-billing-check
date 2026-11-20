"""python analyze.py --validate: сверка папки с эталонами."""
import json
import shutil

from helpers import DATA_DIR

from billcheck.validate import main, validate_dir


def test_open_data_passes_5_of_5(capsys):
    import analyze as cli
    assert cli.main(["--validate", str(DATA_DIR)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 6
    assert out[0].startswith("billing_01.csv: поля отчёта совпали — да; аномалий найдено 4 из 4; ложных 0")
    assert out[-1].startswith("ИТОГО 5/5 ЗАЧЁТ") and "20 из 20" in out[-1]


def test_default_folder_is_data(capsys):
    import analyze as cli
    assert cli.main(["--validate"]) == 0
    assert "ИТОГО 5/5 ЗАЧЁТ" in capsys.readouterr().out


def test_wrong_expected_fails(tmp_path):
    shutil.copy(DATA_DIR / "billing_03.csv", tmp_path / "billing_03.csv")
    expected = json.loads((DATA_DIR / "billing_03_expected.json").read_text(encoding="utf-8"))
    expected["total_som"] += 1
    expected["anomalies"] = expected["anomalies"][:2] + [dict(expected["anomalies"][0], datetime="2026-09-02 00:00:00")]
    (tmp_path / "billing_03_expected.json").write_text(json.dumps(expected), encoding="utf-8")
    [row] = validate_dir(tmp_path)
    assert row["fields_ok"] is False and row["bad_fields"] == ["total_som"]
    assert (row["found"], row["total"]) == (2, 3) and row["passed"] is False
    lines = []
    assert main(tmp_path, out=lines.append) == 1
    assert "НЕТ (total_som)" in lines[0] and lines[-1].startswith("ИТОГО 0/1 НЕЗАЧЁТ")


def test_files_without_expected_are_skipped(tmp_path):
    shutil.copy(DATA_DIR / "billing_01.csv", tmp_path / "billing_01.csv")
    lines = []
    assert main(tmp_path, out=lines.append) == 2
    assert "нет пар" in lines[0]
