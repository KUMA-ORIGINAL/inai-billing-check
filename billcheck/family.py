"""Взгляд на всю семью сразу: итоги по профилям, репутация коротких номеров, самопроверка.

Репутация номеров — наблюдение, а не аномалия: в anomalies.json она никогда не попадает.
"""
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from .anomalies import NIGHT_END, NIGHT_TYPES, is_short_number
from .explain import possible_overpay
from .money import money
from .pipeline import Result
from .selfcheck import compare, load_anomalies

FAMILY_FILE = "family.json"


def load_family(data_dir: Path) -> dict:
    """family.json: {"family": «Семья …», "members": [{file, name, role, msisdn}]}.
    Старый формат {имя файла: подпись} тоже читается. Нет файла или он битый — пустая семья."""
    try:
        data = json.loads((Path(data_dir) / FAMILY_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"family": "", "members": []}
    if not isinstance(data, dict):
        return {"family": "", "members": []}
    if not isinstance(data.get("members"), list):
        return {"family": "", "members": [{"file": str(k), "name": str(v), "role": str(v), "msisdn": ""}
                                          for k, v in data.items()]}
    members = [{"file": str(m.get("file", "")), "name": str(m.get("name") or m.get("role") or ""),
                "role": str(m.get("role", "")), "msisdn": str(m.get("msisdn", ""))}
               for m in data["members"] if isinstance(m, dict) and m.get("file")]
    return {"family": str(data.get("family", "")), "members": members}


def load_profiles(data_dir: Path) -> dict[str, str]:
    """Подписи профилей: имя файла → «Бабушка» (роль, а если её нет — имя). Нет файла — пустой словарь."""
    return {m["file"]: m["role"] or m["name"] for m in load_family(data_dir)["members"]}


def profile_name(profiles: dict[str, str], source: Path) -> str:
    return profiles.get(Path(source).name, Path(source).stem)


def number_reputation(results: list[Result]) -> list[dict]:
    """Короткие номера (3–6 цифр), которые списывают деньги, и у скольких членов семьи."""
    stats: dict[str, dict] = defaultdict(lambda: {"members": set(), "charges": 0, "total": Decimal(0),
                                                  "types": set(), "night": 0, "in_rules": 0,
                                                  "by_member": [Decimal(0)] * len(results)})
    for index, result in enumerate(results):
        flagged = {a.line for a in result.anomalies if a.line is not None}
        for charge in result.charges:
            number = charge.number.strip()
            if not is_short_number(number) or charge.cost <= 0:
                continue
            row = stats[number]
            row["members"].add(index)
            row["charges"] += 1
            row["total"] += charge.cost
            row["by_member"][index] += charge.cost
            row["types"].add(charge.type)
            row["night"] += charge.type in NIGHT_TYPES and charge.dt.time() < NIGHT_END
            row["in_rules"] += charge.line in flagged
    rows = [{"number": number, "members": len(row["members"]), "members_total": len(results),
             "charges": row["charges"], "total_som": money(row["total"]), "types": sorted(row["types"]),
             "night": row["night"], "in_rules": row["in_rules"],
             "by_member": [money(value) for value in row["by_member"]]}
            for number, row in stats.items()]
    return sorted(rows, key=lambda r: (-r["members"], -r["total_som"], r["number"]))


def family_summary(results: list[Result], profiles: dict[str, str]) -> list[dict]:
    return [{"name": profile_name(profiles, r.source), "file": r.source.name,
             "total_som": r.report["total_som"], "overpay_som": money(possible_overpay(r.anomalies)),
             "anomalies": len(r.anomalies),
             "new_subscription": any(a.anomaly_type == "new_subscription" for a in r.anomalies)}
            for r in results]


def self_check(results: list[Result], data_dir: Path) -> dict | None:
    """Сверка с эталонами организаторов (<имя>_expected.json в data_dir). Нет эталонов — None."""
    totals = {"files": 0, "reports_equal": 0, "anomalies_expected": 0, "found": 0, "false_positives": 0}
    for result in results:
        path = Path(data_dir) / f"{result.source.stem}_expected.json"
        if not path.is_file():
            continue
        try:  # эталон бывает объектом с anomalies или просто списком; нечитаемый — пропускаем
            expected = json.loads(path.read_text(encoding="utf-8-sig"))
            expected_anomalies = load_anomalies(path)
            verdict = compare(result.report["anomalies"], expected_anomalies)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        totals["files"] += 1
        totals["reports_equal"] += result.report == expected
        totals["anomalies_expected"] += len(expected_anomalies)
        totals["found"] += verdict["found"]
        totals["false_positives"] += len(verdict["false_positives"])
    return totals if totals["files"] else None
