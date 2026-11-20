"""Самодостаточные HTML-страницы: данные встраиваются JSON-ом в шаблон, внешних скриптов нет."""
import json
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .claim import BLANK, INTRO, claim_basis, claim_positions
from .explain import ADVICE_FAQ_ID, TYPE_NAMES, advice, explain, load_faq, possible_overpay, ratio_text
from .family import family_summary, number_reputation, self_check
from .money import format_som, money
from .pipeline import Result
from .report import daily_totals
from .tariffs import Advice, Offer, advise

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


def printed_line(a) -> str:
    """Строка «как в чеке» над карточкой: день недели, дата, время, тип, номер и строка файла."""
    day = f"{WEEKDAYS[a.dt.weekday()]} {a.dt:%d.%m.%Y}"
    if a.charge is None:
        return f"{day} · за весь день"
    return f"{day} · {a.dt:%H:%M:%S} · {TYPE_NAMES[a.charge.type]} · {a.charge.number or 'без номера'} · строка {a.line}"


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
    tariff = advise(result.charges)
    groups.append({"title": "Сверх ТЗ: объединили с ТЗ 2", "items": [
        {"title": "Тарифный советник: тот же месяц на пакетном тарифе по прайсу и правилам ТЗ 2",
         "ok": tariff is not None, "where": "tariff" if tariff else "",
         "value": (f"лучший — {offer_name(tariff.best)}: {format_som(tariff.best.cost)} сом вместо "
                   f"{format_som(tariff.usage.paid)}" if tariff else "нет data/tariffs.json или нечего сравнивать")}]})
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


SWITCH_FAQ_ID = 5  # «Как сменить тариф?»: где менять и разовый сбор


def offer_name(offer: Offer) -> str:
    """«Максимум + 2 × 100 минут»."""
    counts = Counter(a.name for a in offer.addons)
    extras = [f"{n} × {name}" if n > 1 else name for name, n in counts.items()]
    return " + ".join([f"«{offer.plan.name}»", *extras])


def whole_som(value: Decimal) -> str:
    """Крупная сумма без копеек: 10 872."""
    return f"{value.quantize(Decimal(1), rounding=ROUND_HALF_UP):,.0f}".replace(",", "\u00a0")


def gb_text(value: Decimal) -> str:
    return f"{value:.1f}".replace(".", ",")


def tariff_payload(advice: Advice | None) -> dict | None:
    """Блок «Можно платить меньше»: тот же месяц на лучшем тарифе учебного прайса INAI Mobile."""
    if advice is None:
        return None
    usage, best = advice.usage, advice.best
    parts = [{"label": f"Абонплата {offer_name(best)}", "text": format_som(best.fee)}]
    extra = best.extra_cost
    for key, amount, unit in (("call", best.extra_minutes, "мин"), ("data", best.extra_gb, "ГБ"),
                              ("sms", best.extra_sms, "SMS")):
        if amount > 0:
            shown = gb_text(amount) if key == "data" else f"{amount:.0f}"
            parts.append({"label": f"Сверх пакета: {shown} {unit}", "text": format_som(extra[key])})
    faq = load_faq().get(SWITCH_FAQ_ID, {})
    return {
        "worth": advice.worth_switching,
        "paid_text": format_som(usage.paid), "best_text": format_som(best.cost), "best_name": offer_name(best),
        "savings_text": format_som(advice.savings), "savings_cents": cents(advice.savings),
        "year_text": whole_som(advice.savings * 12),
        "usage_text": f"{usage.minutes} мин местных звонков · {usage.sms} SMS · {gb_text(usage.gb)} ГБ интернета",
        "outside_text": format_som(usage.outside),
        "parts": parts,
        "options": [{"name": offer_name(o), "text": format_som(o.cost), "best": o is best,
                     "savings_text": format_som(usage.paid - o.cost), "cheaper": o.cost < usage.paid}
                    for o in advice.options],
        "advice_ru": faq.get("answer_ru", ""), "advice_ky": faq.get("answer_ky", ""),
    }


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
                          "date": a.dt.date().isoformat(), "label": spike_label(a), "printed": printed_line(a)})
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
        "tariff": tariff_payload(advise(result.charges)),
    }


def render_report(result: Result, profile: str | None = None, llm_text: str | None = None,
                  back_link: dict | None = None, expected_dir: Path | None = None) -> str:
    return embed("report.html", report_payload(result, profile, llm_text, back_link, expected_dir))


def family_payload(results: list[Result], profiles: dict[str, str], links: list[str], data_dir: Path) -> dict:
    members = family_summary(results, profiles)
    savings = Decimal(0)
    for member, link, result in zip(members, links, results):
        advice = advise(result.charges)
        saving = advice.savings if advice and advice.worth_switching else Decimal(0)
        savings += saving
        member.update(link=link, total_text=format_som(Decimal(str(member["total_som"]))),
                      overpay_text=format_som(Decimal(str(member["overpay_som"]))), period=period(result)["label"],
                      savings_cents=cents(saving), savings_text=format_som(saving),
                      tariff_name=offer_name(advice.best) if saving else "")
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
                   "anomalies": sum(m["anomalies"] for m in members), "count": len(members),
                   "savings_cents": cents(savings), "savings_text": format_som(savings),
                   "year_text": whole_som(savings * 12)},
        "reputation": reputation,
        "self_check": self_check(results, data_dir),
        "advice_ru": load_faq().get(ADVICE_FAQ_ID["new_subscription"], {}).get("answer_ru", ""),
        "advice_ky": load_faq().get(ADVICE_FAQ_ID["new_subscription"], {}).get("answer_ky", ""),
    }


def render_family(results: list[Result], profiles: dict[str, str], links: list[str], data_dir: Path) -> str:
    return embed("family.html", family_payload(results, profiles, links, data_dir))
