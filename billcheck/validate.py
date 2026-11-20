"""python analyze.py --validate data — сверка всех детализаций папки с эталонами организаторов.

Для каждого billing_XX.csv, рядом с которым лежит billing_XX_expected.json: совпали ли поля
отчёта, сколько заложенных аномалий найдено и сколько ложных. Правила зачёта — как в check.py
(selfcheck.compare), сверка полей — как в блоке «Автопроверка» приложения (rich.checks).
"""
import json
from pathlib import Path

from .pipeline import analyze
from .rich import checks
from .selfcheck import compare


def expected_for(path: Path) -> dict | None:
    target = path.with_name(f"{path.stem}_expected.json")
    if not target.is_file():
        return None
    data = json.loads(target.read_text(encoding="utf-8-sig"))
    return data if isinstance(data, dict) else {"anomalies": data}


def validate_file(path: Path, expected: dict) -> dict:
    report = analyze(path).report
    fields = [row for row in checks(report, expected) if row["field"] != "anomalies"]
    verdict = compare(report["anomalies"], expected.get("anomalies", []))
    fields_ok = all(row["ok"] for row in fields)
    return {"file": path.name, "fields_ok": fields_ok, "bad_fields": [r["field"] for r in fields if not r["ok"]],
            "found": verdict["found"], "total": verdict["found"] + len(verdict["missed"]),
            "false_positives": len(verdict["false_positives"]), "passed": fields_ok and verdict["passed"]}


def validate_dir(folder: str | Path) -> list[dict]:
    rows = []
    for path in sorted(Path(folder).glob("billing_*.csv")):
        expected = expected_for(path)
        if expected is not None:
            rows.append(validate_file(path, expected))
    return rows


def format_row(row: dict) -> str:
    fields = "да" if row["fields_ok"] else "НЕТ (" + ", ".join(row["bad_fields"]) + ")"
    return (f"{row['file']}: поля отчёта совпали — {fields}; аномалий найдено {row['found']} из {row['total']}; "
            f"ложных {row['false_positives']} → {'ЗАЧЁТ' if row['passed'] else 'НЕЗАЧЁТ'}")


def main(folder: str | Path, out=print) -> int:
    """0 — все файлы в зачёте, 1 — хотя бы один нет, 2 — в папке нет пар CSV + эталон."""
    rows = validate_dir(folder)
    if not rows:
        out(f"Ошибка: в {folder} нет пар billing_XX.csv + billing_XX_expected.json.")
        return 2
    for row in rows:
        out(format_row(row))
    passed = sum(row["passed"] for row in rows)
    found, total = sum(r["found"] for r in rows), sum(r["total"] for r in rows)
    false = sum(r["false_positives"] for r in rows)
    ok = passed == len(rows)
    out(f"ИТОГО {passed}/{len(rows)} {'ЗАЧЁТ' if ok else 'НЕЗАЧЁТ'} (аномалий {found} из {total}, ложных {false})")
    return 0 if ok else 1
