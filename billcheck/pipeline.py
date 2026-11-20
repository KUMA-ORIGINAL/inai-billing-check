"""Сквозной расчёт по одному файлу и запись результатов для жюри."""
import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .anomalies import Anomaly, find_all
from .explain import advice, explain
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
    """anomalies.json: поля эталона + строка детализации (у day_spike — null), пояснение и советы RU/KY."""
    return [a.as_dict() | {"line": a.line, "explanation_ru": explain(a),
                           "advice_ru": advice(a, "ru"), "advice_ky": advice(a, "ky")}
            for a in result.anomalies]


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_outputs(result: Result, out_dir: Path, profile: str | None = None, llm_text: str | None = None,
                  family_link: str | None = None) -> dict[str, Path]:
    from .html import render_report  # html импортирует Result отсюда

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {name: out_dir / name for name in ("report.json", "anomalies.json", "dropped_rows.csv", "report.html")}
    paths["report.html"].write_text(render_report(result, profile, llm_text, family_link), encoding="utf-8")
    write_json(paths["report.json"], result.report)
    write_json(paths["anomalies.json"], anomaly_records(result))
    with paths["dropped_rows.csv"].open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["line", "reason", "raw"])
        writer.writerows([d.line, d.reason, d.raw] for d in result.dropped)
    return paths
