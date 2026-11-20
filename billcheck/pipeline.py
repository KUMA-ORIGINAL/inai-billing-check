"""Сквозной расчёт по одному файлу и запись результатов для жюри."""
import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .anomalies import Anomaly, find_all
from .parse import Charge, Dropped, read_billing
from .report import summarize


@dataclass
class Result:
    source: Path
    charges: list[Charge]
    dropped: list[Dropped]
    anomalies: list[Anomaly]
    report: dict


def analyze(path: str | Path) -> Result:
    """Детализация → отчёт ровно в формате эталона организаторов + список аномалий."""
    path = Path(path)
    charges, dropped = read_billing(path)
    anomalies = find_all(charges)
    report = summarize(charges, len(dropped)) | {"anomalies": [a.as_dict() for a in anomalies]}
    return Result(path, charges, dropped, anomalies, report)


def anomaly_records(result: Result) -> list[dict]:
    """anomalies.json: поля эталона + номер строки детализации (у day_spike — null)."""
    return [a.as_dict() | {"line": a.line} for a in result.anomalies]


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_outputs(result: Result, out_dir: Path) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {name: out_dir / name for name in ("report.json", "anomalies.json", "dropped_rows.csv")}
    write_json(paths["report.json"], result.report)
    write_json(paths["anomalies.json"], anomaly_records(result))
    with paths["dropped_rows.csv"].open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["line", "reason", "raw"])
        writer.writerows([d.line, d.reason, d.raw] for d in result.dropped)
    return paths
