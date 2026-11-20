"""Самопроверка по правилам жюри ТЗ 4.

python check.py out/anomalies.json data/billing_01_expected.json

Зачёт — найдено не менее 80% заложенных аномалий и не больше 2 ложных срабатываний.
Аномалии совпадают по datetime и anomaly_type (если его нет у одной из сторон — по type).
Если рядом с anomalies.json лежит report.json, дополнительно сверяются поля отчёта.
"""
import json
import sys
from pathlib import Path

RECALL_MIN = 0.8
FALSE_POSITIVES_MAX = 2
REPORT_FIELDS = ("valid_rows", "dropped_rows", "total_som", "by_category", "by_day", "top5_numbers")


def load_anomalies(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return data["anomalies"] if isinstance(data, dict) else data


def same_anomaly(found: dict, expected: dict) -> bool:
    if str(found.get("datetime", "")).strip() != str(expected.get("datetime", "")).strip():
        return False
    if found.get("anomaly_type") and expected.get("anomaly_type"):
        return found["anomaly_type"] == expected["anomaly_type"]
    return found.get("type") == expected.get("type")


def compare(found: list[dict], expected: list[dict]) -> dict:
    unused = list(found)
    missed, amount_mismatch = [], []
    for item in expected:
        match = next((f for f in unused if same_anomaly(f, item)), None)
        if match is None:
            missed.append(item)
            continue
        unused.remove(match)
        if "amount_som" in match and "amount_som" in item and abs(match["amount_som"] - item["amount_som"]) > 0.01:
            amount_mismatch.append({"found": match, "expected": item})
    matched = len(expected) - len(missed)
    recall = matched / len(expected) if expected else 1.0
    return {"found": matched, "missed": missed, "false_positives": unused, "recall": recall,
            "amount_mismatch": amount_mismatch,
            "passed": recall >= RECALL_MIN and len(unused) <= FALSE_POSITIVES_MAX}


def describe(a: dict) -> str:
    return f"{a.get('datetime')} {a.get('anomaly_type') or a.get('type')} {a.get('amount_som', '')}".strip()


def compare_report(report_path: Path, expected: dict) -> list[str]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    lines = []
    for field in REPORT_FIELDS:
        if field not in expected:
            continue
        ok = report.get(field) == expected[field]
        detail = "" if ok or isinstance(expected[field], (dict, list)) else \
            f" (у нас {report.get(field)}, в эталоне {expected[field]})"
        lines.append(f"  {field}: {'совпадает' if ok else 'НЕ совпадает'}{detail}")
    return lines


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    found_path, expected_path = Path(argv[0]), Path(argv[1])
    result = compare(load_anomalies(found_path), load_anomalies(expected_path))
    total = result["found"] + len(result["missed"])
    verdict = "ЗАЧЁТ" if result["passed"] else "НЕЗАЧЁТ"
    print(f"{verdict}: найдено {result['found']} из {total} ({result['recall']:.0%}), "
          f"ложных: {len(result['false_positives'])} (допустимо не больше {FALSE_POSITIVES_MAX})")
    for item in result["missed"]:
        print(f"  пропущена: {describe(item)}")
    for item in result["false_positives"]:
        print(f"  лишняя:    {describe(item)}")
    for pair in result["amount_mismatch"]:
        print(f"  сумма отличается: {describe(pair['found'])}, в эталоне {pair['expected'].get('amount_som')}")
    expected = json.loads(expected_path.read_text(encoding="utf-8-sig"))
    report_path = found_path.with_name("report.json")
    if isinstance(expected, dict) and report_path.is_file():
        print("Отчёт:")
        print("\n".join(compare_report(report_path, expected)))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
