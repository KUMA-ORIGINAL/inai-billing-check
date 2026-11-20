"""Правила зачёта жюри ТЗ 4: найдено не меньше 80% заложенных аномалий, ложных не больше 2."""
import json
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
