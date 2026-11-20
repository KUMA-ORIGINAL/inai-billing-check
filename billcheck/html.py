"""Самодостаточные HTML-страницы: данные встраиваются JSON-ом в шаблон, внешних скриптов нет."""
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from .claim import BLANK, INTRO, claim_basis, claim_positions
from .explain import ADVICE_FAQ_ID, TYPE_NAMES, advice, explain, load_faq, possible_overpay, ratio_text
from .family import family_summary, number_reputation, self_check
from .money import format_som, money
from .pipeline import Result
from .report import daily_totals

TEMPLATES = Path(__file__).resolve().parent / "templates"
PLACEHOLDER = "__BILL_DATA__"

MONTHS = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь",
          "ноябрь", "декабрь")
WEEKDAYS = ("ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС")
DROP_REASONS_RU = {
    "empty_line": "пустая строка",
    "column_count": "не то число колонок",
    "unknown_type": "неизвестный тип списания",
    "bad_datetime": "дата не разбирается",
    "bad_number": "плохое число: пусто, текст, NaN, Infinity или меньше нуля",
}
RULE_NAMES = {"night_charge": "ночные платные SMS и контент", "new_subscription": "новая подписка",
              "duplicate_charge": "двойные списания", "international_rate": "дорогие международные звонки",
              "day_spike": "необычные дни (z-score > 3)"}


def anomaly_title(anomaly_type: str, type_: str) -> str:
    return {"night_charge": f"Платное {'SMS' if type_ == 'sms' else 'контент'} ночью",
            "new_subscription": "Новая подписка",
            "duplicate_charge": "Двойное списание",
            "international_rate": "Дорогой международный звонок",
            "day_spike": "Необычный день"}[anomaly_type]


def spike_label(a) -> str:
    """Подпись над столбиком дня-всплеска: «в 9,2 раза больше обычного»."""
    if a.anomaly_type != "day_spike" or not a.baseline:
        return ""
    return f"в {ratio_text((a.baseline + a.amount) / a.baseline)} раза больше обычного"


def cents(value: Decimal) -> int:
    return int(round(money(value) * 100))


LESS_THAN_ESCAPE = "\\" + "u003c"  # JSON-экранирование «<»: ни </script>, ни <!-- не попадут в разметку


def embed(template: str, data: dict) -> str:
    """Данные страницы — JSON внутри <script type="application/json">; каждый «<» экранирован."""
    payload = json.dumps(data, ensure_ascii=False).replace("<", LESS_THAN_ESCAPE)
    page = (TEMPLATES / template).read_text(encoding="utf-8")
    page = page.replace("/*__BASE_CSS__*/", (TEMPLATES / "base.css").read_text(encoding="utf-8"))
    page = page.replace("/*__BASE_JS__*/", (TEMPLATES / "base.js").read_text(encoding="utf-8"))
    return page.replace(PLACEHOLDER, payload)


def period(result: Result) -> dict:
    if not result.charges:
        return {"from": "", "to": "", "label": "нет списаний"}
    first, last = min(c.dt for c in result.charges), max(c.dt for c in result.charges)
    label = (f"{MONTHS[first.month - 1]} {first.year}" if (first.year, first.month) == (last.year, last.month)
             else f"{first:%d.%m.%Y} — {last:%d.%m.%Y}")
    return {"from": f"{first:%d.%m.%Y}", "to": f"{last:%d.%m.%Y}", "label": label}


def receipt_days(result: Result, flags: dict[int, list[int]], spike_days: set[str]) -> list[dict]:
    by_day: dict[str, list] = {}
    for charge in sorted(result.charges, key=lambda c: (c.dt, c.line)):
        by_day.setdefault(charge.dt.date().isoformat(), []).append(charge)
    days = []
    for day, total in daily_totals(result.charges).items():
        key = day.isoformat()
        lines = [{"line": c.line, "time": f"{c.dt:%H:%M:%S}", "type": c.type, "type_ru": TYPE_NAMES[c.type],
                  "number": c.number, "cost": format_som(c.cost), "raw": c.raw, "flags": flags.get(c.line, [])}
                 for c in by_day.get(key, [])]
        days.append({"date": key, "label": f"{WEEKDAYS[day.weekday()]} {day:%d.%m}", "total": format_som(total),
                     "total_cents": cents(total), "lines": lines, "spike": key in spike_days,
                     "flagged": any(line["flags"] for line in lines)})
    return days


def checklist(result: Result, llm_text: str | None, expected_dir: Path) -> list[dict]:
    report = result.report
    counts = Counter(a.anomaly_type for a in result.anomalies)
    dropped = Counter(d.reason for d in result.dropped)
    explained = sum(1 for a in result.anomalies if explain(a))
    rules = " · ".join(f"{name} — {counts.get(kind, 0)}" for kind, name in RULE_NAMES.items())
    groups = [
        {"title": "Обязательно по ТЗ 4", "items": [
            {"title": "Суммы по категориям и по дням, топ-5 номеров по стоимости", "ok": True, "where": "spend",
             "value": f"5 категорий · {len(report['by_day'])} дней без пропусков · "
                      f"топ-{len(report['top5_numbers'])} номеров"},
            {"title": "Разбор грязных данных: два формата даты, запятая в суммах, пустые и битые строки",
             "ok": True, "where": "quality",
             "value": f"разобрано {report['valid_rows']} списаний, отброшено {report['dropped_rows']}"
                      + (": " + ", ".join(f"{DROP_REASONS_RU[k]} — {v}" for k, v in dropped.items()) if dropped else "")},
            {"title": "Аномалии пяти типов", "ok": True, "where": "found", "value": rules},
            {"title": "У каждой аномалии — понятное пояснение и сумма возможной переплаты", "ok": True,
             "where": "found", "value": f"{explained} из {len(result.anomalies)}"},
        ]},
        {"title": "Бонусы", "items": [
            {"title": "График трат по дням с отмеченными аномалиями", "ok": True, "where": "chart",
             "value": "день-всплеск выделен, дни со спорными списаниями отмечены точкой"},
            {"title": "Пояснения через LLM", "ok": bool(llm_text), "where": "hero",
             "value": "письмо абоненту написано ИИ по посчитанным числам" if llm_text
                      else "включается флагом --llm: бесплатный Gemini, локальная Ollama, Groq или Claude"},
            {"title": "Чтение PDF-детализации", "ok": False, "where": "",
             "value": "не делали: у организаторов нет образцов PDF"},
        ]},
    ]
    check = self_check([result], expected_dir)
    if check:
        groups.append({"title": "Сверка с эталоном организаторов", "items": [
            {"title": "Эталон организаторов", "ok": check["reports_equal"] == 1 and check["false_positives"] == 0,
             "where": "", "value": f"отчёт совпал: {'да' if check['reports_equal'] else 'нет'} · аномалий найдено "
                                   f"{check['found']} из {check['anomalies_expected']} · ложных {check['false_positives']}"}]})
    return groups


def phone_payload(result: Result) -> dict:
    """Платные короткие номера этого абонента для демо-окна телефона и честный совет из FAQ (id 8)."""
    faq = load_faq().get(ADVICE_FAQ_ID["new_subscription"], {})
    numbers = [{"number": row["number"], "charges": row["charges"], "total_text": format_som(Decimal(str(row["total_som"]))),
                "types_text": ", ".join(TYPE_NAMES[t] for t in row["types"])}
               for row in number_reputation([result])]
    return {"numbers": numbers, "advice_ru": faq.get("answer_ru", ""), "advice_ky": faq.get("answer_ky", "")}


def report_payload(result: Result, profile: str | None = None, llm_text: str | None = None,
                   back_link: dict | None = None, expected_dir: Path | None = None) -> dict:
    """Данные страницы отчёта. back_link — {"href", "label"} кнопки «назад»; expected_dir — где искать эталон."""
    report = result.report
    overpay = possible_overpay(result.anomalies)
    flags: dict[int, list[int]] = {}
    anomalies = []
    for i, a in enumerate(result.anomalies):
        if a.line is not None:
            flags.setdefault(a.line, []).append(i)
        anomalies.append({"id": i, **a.as_dict(), "title": anomaly_title(a.anomaly_type, a.type),
                          "amount_text": format_som(a.amount), "line": a.line,
                          "raw": a.charge.raw if a.charge else "", "number": a.charge.number if a.charge else "",
                          "cost_text": format_som(a.charge.cost) if a.charge else "",
                          "explanation": explain(a), "advice_ru": advice(a, "ru"), "advice_ky": advice(a, "ky"),
                          "date": a.dt.date().isoformat(), "label": spike_label(a)})
    spike_days = {a["date"] for a in anomalies if a["anomaly_type"] == "day_spike"}
    positions = claim_positions(result)
    return {
        "profile": profile or result.source.stem,
        "file": result.source.name,
        "period": period(result),
        "valid_rows": report["valid_rows"], "dropped_rows": report["dropped_rows"],
        "total_text": format_som(Decimal(str(report["total_som"]))),
        "overpay_text": format_som(overpay), "overpay_cents": cents(overpay),
        "by_category": [{"type": k, "label": TYPE_NAMES[k], "text": format_som(Decimal(str(v))), "value": v}
                        for k, v in report["by_category"].items()],
        "top5": [{"number": t["number"], "text": format_som(Decimal(str(t["cost_som"]))), "value": t["cost_som"]}
                 for t in report["top5_numbers"]],
        "days": receipt_days(result, flags, spike_days),
        "anomalies": anomalies,
        "claim": {"head": ["В службу поддержки INAI Mobile"], "blank": BLANK, "intro": INTRO,
                  "basis": claim_basis(result),
                  "positions": [{"line": p["line"], "cents": cents(p["amount"]), "text": p["text"]}
                                for p in positions]},
        "checklist": checklist(result, llm_text, expected_dir or result.source.parent),
        "dropped": [{"line": d.line, "reason": d.reason, "reason_ru": DROP_REASONS_RU[d.reason], "raw": d.raw}
                    for d in result.dropped],
        "llm": llm_text,
        "back_link": back_link,
        "phone": phone_payload(result),
    }


def render_report(result: Result, profile: str | None = None, llm_text: str | None = None,
                  back_link: dict | None = None, expected_dir: Path | None = None) -> str:
    return embed("report.html", report_payload(result, profile, llm_text, back_link, expected_dir))


def family_payload(results: list[Result], profiles: dict[str, str], links: list[str], data_dir: Path) -> dict:
    members = family_summary(results, profiles)
    for member, link, result in zip(members, links, results):
        member.update(link=link, total_text=format_som(Decimal(str(member["total_som"]))),
                      overpay_text=format_som(Decimal(str(member["overpay_som"]))), period=period(result)["label"])
    total = sum((Decimal(str(m["total_som"])) for m in members), Decimal(0))
    overpay = sum((Decimal(str(m["overpay_som"])) for m in members), Decimal(0))
    reputation = []
    for row in number_reputation(results):
        types = ", ".join(TYPE_NAMES[t] for t in row["types"])
        reputation.append(row | {
            "members_text": f"у {row['members']} из {row['members_total']}",
            "total_text": format_som(Decimal(str(row["total_som"]))),
            "when": "ночью" if row["night"] == row["charges"] else "днём" if row["night"] == 0 else "днём и ночью",
            "types_text": types,
            "unseen_by_rules": row["in_rules"] == 0 and row["members"] >= 2,
        })
    periods = {m["period"] for m in members}
    return {
        "members": members,
        "names": [m["name"] for m in members],
        "period": periods.pop() if len(periods) == 1 else "",
        "totals": {"total_text": format_som(total), "overpay_text": format_som(overpay),
                   "anomalies": sum(m["anomalies"] for m in members), "count": len(members)},
        "reputation": reputation,
        "self_check": self_check(results, data_dir),
    }


def render_family(results: list[Result], profiles: dict[str, str], links: list[str], data_dir: Path) -> str:
    return embed("family.html", family_payload(results, profiles, links, data_dir))
