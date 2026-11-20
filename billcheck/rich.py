"""Расширенный отчёт для приложения «Акчам кайда?»: всё, что нужно экрану, поверх отчёта жюри.

report.json и anomalies.json для автопроверки не меняются: их поля — подмножество этого отчёта.
Здесь добавляются улики (строки детализации вокруг находки), пояснения и советы на русском и
кыргызском, сводка «к возврату», траты по часам, журнал пропущенных строк и совет по тарифу.
"""
from collections import defaultdict
from decimal import Decimal

from .anomalies import NIGHT_TYPES, Anomaly, Rules, is_short_number
from .explain import ADVICE_FAQ_ID, TYPE_NAMES, disputed, explain, load_faq, possible_overpay, som
from .money import money
from .parse import Charge
from .pipeline import Result
from .selfcheck import REPORT_FIELDS, compare
from .tariffs import Advice, advise

CONTEXT_AROUND = 2
DROP_REASONS = {
    "empty_line": "пустая строка",
    "column_count": "не то число колонок",
    "unknown_type": "неизвестный тип списания",
    "bad_datetime": "дата не разбирается",
    "bad_number": "плохое число: пусто, текст, NaN, Infinity или меньше нуля",
}
TYPE_KY = {"call": "чалуу", "sms": "SMS", "data": "интернет", "subscription": "жазылуу", "content": "контент"}


def _dt(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _num(value: Decimal) -> str:
    """Число для кыргызского текста: 15, 9,59."""
    text = f"{value.quantize(Decimal('0.01'))}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _row(c: Charge, hit: bool) -> dict:
    return {"line": c.line, "datetime": _dt(c.dt), "type": c.type, "number": c.number,
            "duration_sec": float(c.duration_sec), "mb": float(c.mb), "cost_som": money(c.cost), "hit": hit}


def _same_number(charges: list[Charge], number: str, kind: str) -> list[Charge]:
    return [c for c in charges if c.type == kind and c.number.strip() == number]


def _spike_top(charges: list[Charge], a: Anomaly, limit: int = 3) -> list[Charge]:
    day = [c for c in charges if c.dt.date() == a.dt.date()]
    return sorted(day, key=lambda c: (-c.cost, c.dt))[:limit]


def context(charges: list[Charge], a: Anomaly) -> list[dict]:
    """Улика: строки детализации вокруг находки, подозрительные помечены hit."""
    ordered = sorted(charges, key=lambda c: (c.dt, c.line))
    if a.anomaly_type == "day_spike":
        top = {c.line for c in _spike_top(charges, a)}
        day = [c for c in ordered if c.dt.date() == a.dt.date()]
        picked = [c for c in day if c.line in top]
        if day:  # рядом с самыми дорогими — обычные строки того же дня, чтобы было видно разницу
            picked += [c for c in day if c.line not in top][:2]
        return [_row(c, c.line in top) for c in sorted(picked, key=lambda c: (c.dt, c.line))]
    hits = {a.line} | ({a.previous.line} if a.previous else set())
    index = next((i for i, c in enumerate(ordered) if c.line == a.line), None)
    if index is None:
        return []
    first = min(i for i, c in enumerate(ordered) if c.line in hits)
    window = ordered[max(0, first - CONTEXT_AROUND):index + CONTEXT_AROUND + 1]
    return [_row(c, c.line in hits) for c in window]


def evidence(charges: list[Charge], a: Anomaly, rules: Rules) -> dict:
    c = a.charge
    if a.anomaly_type == "night_charge":
        return {"hour": c.dt.hour, "window": f"[{rules.night_start_hour:02d}:00, {rules.night_end_hour:02d}:00)"}
    if a.anomaly_type == "new_subscription":
        same = _same_number(charges, c.number.strip(), "subscription")
        return {"repeats_in_month": len(same), "total_in_month": money(sum((x.cost for x in same), Decimal(0)))}
    if a.anomaly_type == "duplicate_charge":
        prev = a.previous
        return {"first_line": prev.line if prev else None, "first_datetime": _dt(prev.dt) if prev else None,
                "gap_sec": int((c.dt - prev.dt).total_seconds()) if prev else 0}
    if a.anomaly_type == "international_rate":
        minutes = c.duration_sec / 60
        return {"rate_per_min": money(c.cost / minutes), "limit_per_min": float(rules.intl_rate_limit),
                "fair_cost": money(rules.intl_rate_limit * minutes), "minutes": money(minutes)}
    if a.anomaly_type == "day_spike":
        mean = a.baseline or Decimal(0)
        return {"day_total": money(mean + a.amount), "mean_7d": money(mean),
                "top_charges": [{"line": x.line, "datetime": _dt(x.dt), "type": x.type, "number": x.number,
                                 "cost_som": money(x.cost)} for x in _spike_top(charges, a)]}
    return {}


def explanation_ru(charges: list[Charge], a: Anomaly, ev: dict) -> str:
    text = explain(a)
    if a.anomaly_type == "new_subscription" and ev["repeats_in_month"] > 1:
        text += (f" За месяц она списала уже {ev['repeats_in_month']} раза — всего "
                 f"{som(Decimal(str(ev['total_in_month'])))}. Подписки продлеваются сами, пока их не отключить.")
    if a.anomaly_type == "day_spike" and ev["top_charges"]:
        text += " Больше всего: " + ", ".join(
            f"{TYPE_NAMES[x['type']]} {x['number'] or 'без номера'} — {som(Decimal(str(x['cost_som'])))}"
            for x in ev["top_charges"]) + "."
    return text


def explanation_ky(a: Anomaly, ev: dict, rules: Rules) -> str:
    c, day = a.charge, a.dt.strftime("%d.%m")
    if a.anomaly_type == "night_charge":
        what = "SMS" if a.type == "sms" else "контент"
        return (f"{day} күнү саат {a.dt:%H:%M} {c.number} номерине акы төлөнүүчү {what} үчүн {_num(a.amount)} сом "
                "алынган. Түн ичинде адамдар уктайт — мындай төлөмдөр көбүнчө абоненттин кабарсыз туташтырылат.")
    if a.anomaly_type == "new_subscription":
        text = (f"{day} күнү саат {a.dt:%H:%M} кыска {c.number} номерине акы төлөнүүчү жазылуу пайда болду "
                f"({_num(a.amount)} сом).")
        if ev["repeats_in_month"] > 1:
            text += (f" Бир айда {ev['repeats_in_month']} жолу алынды — баары "
                     f"{_num(Decimal(str(ev['total_in_month'])))} сом.")
        return text + " Жазылуу өчүрүлмөйүнчө өзү эле узартыла берет."
    if a.anomaly_type == "duplicate_charge":
        first = ev["first_datetime"][11:] if ev.get("first_datetime") else ""
        return (f"{c.number or 'номерсиз'} номерине бир эле {TYPE_KY[a.type]} ({_num(c.cost)} сом) "
                f"{ev['gap_sec']} секунддун ичинде эки жолу алынды: {first} жана {a.dt:%H:%M:%S}.")
    if a.anomaly_type == "international_rate":
        return (f"{c.number} номерине чалуу {_num(Decimal(str(ev['minutes'])))} мүнөткө созулуп, {_num(c.cost)} сом "
                f"турду — бул мүнөтүнө {_num(Decimal(str(ev['rate_per_min'])))} сом, ал эми норма "
                f"{_num(rules.intl_rate_limit)} сомго чейин. Ашык төлөм {_num(a.amount)} сом.")
    if a.anomaly_type == "day_spike":
        mean, total = Decimal(str(ev["mean_7d"])), Decimal(str(ev["day_total"]))
        ratio = f"адаттагыдан {(total / mean):.1f} эсе көп ".replace(".", ",") if mean > 0 else ""
        text = (f"{day} күнү {_num(total)} сом коротулган — {ratio}"
                f"(мурунку {rules.z_window_days} күндүн орточосу {_num(mean)} сом).")
        if ev["top_charges"]:
            text += " Эң көп: " + ", ".join(f"{TYPE_KY[x['type']]} {x['number'] or 'номерсиз'} "
                                            f"{_num(Decimal(str(x['cost_som'])))} сом" for x in ev["top_charges"]) + "."
        return text
    return a.reason


def advice_texts(a: Anomaly) -> tuple[str, str]:
    """Что делать — конкретный шаг на двух языках; для подписок и ночного контента — плюс совет из FAQ оператора."""
    number = a.charge.number if a.charge else ""
    amount_ru, amount_ky = som(a.amount), f"{_num(a.amount)} сом"
    steps = {
        "night_charge": (f"Вы не заказывали этого ночью? Оспорьте {amount_ru} и попросите запретить платный контент на номере.",
                         f"Түнү муну буйрутма кылган жоксузбу? {amount_ky} талашып, номерге акы төлөнүүчү контентке "
                         "тыюу салууну сураңыз."),
        "new_subscription": (f"Если вы её не оформляли — отключите подписку {number} и потребуйте возврат.",
                             f"Эгер сиз туташтырбасаңыз — {number} жазылуусун өчүрүп, акчаны кайтарууну талап кылыңыз."),
        "duplicate_charge": (f"Одно списание прошло дважды — требуйте вернуть второе: {amount_ru}.",
                             f"Бир төлөм эки жолу өттү — экинчисин кайтарууну талап кылыңыз: {amount_ky}."),
        "international_rate": ("Вы звонили по этому номеру? Если нет — это может быть Wangiri (звонок-приманка). "
                               "Если да — уточните у оператора тариф на это направление.",
                               "Бул номерге чалдыңызбы? Эгер жок болсо — бул Wangiri (алдамчы чалуу) болушу мүмкүн. "
                               "Эгер ооба — оператордон бул багыттын тарифин тактаңыз."),
        "day_spike": ("Проверьте, кто и куда звонил в этот день. Если звонки не ваши — заблокируйте SIM и обратитесь к оператору.",
                      "Бул күнү ким жана кайда чалганын текшериңиз. Эгер чалуулар сиздики болбосо — SIM-картаны "
                      "бөгөттөп, операторго кайрылыңыз."),
    }
    ru, ky = steps[a.anomaly_type]
    if a.anomaly_type in ("night_charge", "new_subscription"):
        faq = load_faq().get(ADVICE_FAQ_ID[a.anomaly_type], {})
        if faq.get("answer_ru"):
            ru, ky = f"{ru} {faq['answer_ru']}", f"{ky} {faq.get('answer_ky') or faq['answer_ru']}"
    return ru, ky


def reasons_ky(rules: Rules) -> dict[str, str]:
    z = f"{rules.z_threshold.normalize():f}"
    return {
        "night_charge": f"Түнкү {rules.night_start_hour:02d}:00–{rules.night_end_hour:02d}:00 аралыгында акы "
                        "төлөнүүчү SMS/контент",
        "new_subscription": "Кыска номерге жаңы жазылуу",
        "duplicate_charge": f"{rules.duplicate_window_sec} секунддун ичинде бирдей төлөм",
        "international_rate": f"Мүнөтү {_num(rules.intl_rate_limit)} сомдон кымбат эл аралык чалуу",
        "day_spike": f"Күндүк чыгым мурунку {rules.z_window_days} күндүн орточосунан жогору: z-score > {z}",
    }


def rich_anomalies(result: Result) -> list[dict]:
    rules, charges = result.rules, result.charges
    claimed = {id(a) for a in disputed(result.anomalies).values()}
    ky = reasons_ky(rules)
    rows = []
    for a in result.anomalies:
        ev = evidence(charges, a, rules)
        advice_ru, advice_ky = advice_texts(a)
        rows.append(a.as_dict() | {
            "explanation": explanation_ru(charges, a, ev), "explanation_ky": explanation_ky(a, ev, rules),
            "advice": advice_ru, "advice_ky": advice_ky, "reason_ky": ky[a.anomaly_type],
            "number": a.charge.number if a.charge else "", "line": a.line or 0,
            "reclaimable": id(a) in claimed, "evidence": ev, "context": context(charges, a),
        })
    return rows


def tariff_block(advice: Advice | None) -> dict | None:
    """Совет по тарифу (данные и правила ТЗ 2) в числах — подписи строит страница."""
    if advice is None:
        return None
    from .html import offer_name  # html тянет шаблоны, поэтому импорт по месту

    best, usage = advice.best, advice.usage
    parts = [{"label": f"Абонплата {offer_name(best)}", "label_ky": f"Абоненттик акы {offer_name(best)}",
              "som": money(best.fee)}]
    for key, amount, ru, ky in (("call", best.extra_minutes, "мин", "мүн"), ("data", best.extra_gb, "ГБ", "ГБ"),
                                ("sms", best.extra_sms, "SMS", "SMS")):
        if amount > 0:
            shown = f"{amount:.1f}".replace(".", ",") if key == "data" else f"{amount:.0f}"
            parts.append({"label": f"Сверх пакета: {shown} {ru}", "label_ky": f"Пакеттен ашык: {shown} {ky}",
                          "som": money(best.extra_cost[key])})
    faq = load_faq().get(5, {})  # «Как сменить тариф?»
    return {
        "worth": advice.worth_switching, "paid_som": money(usage.paid), "best_name": offer_name(best),
        "best_som": money(best.cost), "savings_som": money(advice.savings), "year_som": money(advice.savings * 12),
        "outside_som": money(usage.outside), "minutes": usage.minutes, "sms": usage.sms,
        "gb": float(round(usage.gb, 1)), "parts": parts,
        "options": [{"name": offer_name(o), "som": money(o.cost), "best": o is best} for o in advice.options],
        "advice_ru": faq.get("answer_ru", ""), "advice_ky": faq.get("answer_ky", ""),
    }


def rich_report(result: Result) -> dict:
    report, charges = result.report, result.charges
    anomalies = rich_anomalies(result)
    days = list(report["by_day"])
    total = Decimal(str(report["total_som"]))
    reclaim = possible_overpay(result.anomalies)
    by_hour = [Decimal(0)] * 24
    by_type: dict[str, int] = defaultdict(int)
    for c in charges:
        by_hour[c.dt.hour] += c.cost
        by_type[c.type] += 1
    return report | {
        "anomalies": anomalies,
        "meta": {"source": result.source.name, "period": [days[0], days[-1]] if days else ["", ""],
                 "settings": result.rules.as_dict()},
        "summary": {"reclaimable_som": money(reclaim),
                    "spike_excess_som": money(sum((a.amount for a in result.anomalies
                                                   if a.anomaly_type == "day_spike"), Decimal(0))),
                    "anomaly_count": len(anomalies),
                    "reclaimable_share_pct": money(reclaim * 100 / total) if total else 0.0,
                    "avg_day_som": money(total / len(days)) if days else 0.0},
        "usage": {"call_minutes": money(sum((c.duration_sec for c in charges if c.type == "call"), Decimal(0)) / 60),
                  "sms_count": by_type.get("sms", 0),
                  "data_mb": money(sum((c.mb for c in charges if c.type == "data"), Decimal(0))),
                  "records_by_type": dict(by_type)},
        "by_hour": [money(v) for v in by_hour],
        "rows": [[c.line, _dt(c.dt), c.type, c.number, float(c.duration_sec), float(c.mb), money(c.cost)]
                 for c in sorted(charges, key=lambda c: (c.dt, c.line))],
        "dropped_log": [{"line": d.line, "raw": d.raw, "reason": DROP_REASONS.get(d.reason, d.reason)}
                        for d in result.dropped],
        "tariff": tariff_block(advise(charges)),
    }


def checks(report: dict, expected: dict | list | None) -> list[dict]:
    """Сверка с эталоном организаторов по каждому полю — для блока «Автопроверка» на экране."""
    if not expected:
        return []
    exp = expected if isinstance(expected, dict) else {"anomalies": expected}
    rows = []
    for field in REPORT_FIELDS:
        if field not in exp:
            continue
        got, want = report.get(field), exp[field]
        if field == "by_category" and isinstance(want, dict):
            for key, value in want.items():
                mine = (got or {}).get(key)
                rows.append({"field": f"by_category.{key}", "ok": mine is not None and abs(mine - value) <= 0.01,
                             "got": mine, "expected": value})
        elif field == "by_day" and isinstance(want, dict):
            diff = sum(1 for k, v in want.items() if k not in (got or {}) or abs(got[k] - v) > 0.01)
            diff += sum(1 for k in (got or {}) if k not in want)
            rows.append({"field": "by_day", "ok": diff == 0, "got": f"{len(got or {})} дн., расхождений {diff}",
                         "expected": f"{len(want)} дн."})
        elif field == "top5_numbers":
            mine = [t["number"] for t in got or []]
            theirs = [t["number"] for t in want]
            rows.append({"field": field, "ok": got == want, "got": mine, "expected": theirs})
        else:
            ok = got == want if not isinstance(want, float) else abs((got or 0) - want) <= 0.01
            rows.append({"field": field, "ok": ok, "got": got, "expected": want})
    if isinstance(exp.get("anomalies"), list):
        verdict = compare([{k: a[k] for k in ("datetime", "type", "anomaly_type", "amount_som")}
                           for a in report["anomalies"]], exp["anomalies"])
        rows.append({"field": "anomalies", "ok": verdict["passed"] and not verdict["missed"] and not verdict["amount_mismatch"],
                     "got": f"найдено {verdict['found']}, ложных {len(verdict['false_positives'])}",
                     "expected": f"{len(exp['anomalies'])} аномалий"})
    return rows


def radar(members: list[dict], rules: Rules | None = None) -> list[dict]:
    """Короткие номера (3–6 цифр) по всем абонентам: у скольких, сколько, доля ночных и новых подписок.

    Эвристика экрана оператора: балл = (доля абонентов + доля ночных + доля новых подписок) / 3 × 100.
    В anomalies.json не попадает. members — [{"name", "report"}] с расширенными отчётами.
    """
    stats: dict[str, dict] = {}
    count = len(members)
    for m in members:
        report = m.get("report") or {}
        settings = Rules.from_dict((report.get("meta") or {}).get("settings")) if rules is None else rules
        new_subs = {a.get("number") for a in report.get("anomalies", []) if a.get("anomaly_type") == "new_subscription"}
        for row in report.get("rows", []):
            _, when, kind, number, _, _, cost = row
            number = str(number).strip()
            if not is_short_number(number) or not cost or cost <= 0:
                continue
            item = stats.setdefault(number, {"who": [], "charges": 0, "total": Decimal(0), "night": 0,
                                             "new": set(), "types": set(), "by_hour": [Decimal(0)] * 24})
            if m["name"] not in item["who"]:
                item["who"].append(m["name"])
            item["charges"] += 1
            item["total"] += Decimal(str(cost))
            hour = int(when[11:13])
            item["by_hour"][hour] += Decimal(str(cost))
            item["types"].add(kind)
            item["night"] += kind in NIGHT_TYPES and settings.night_start_hour <= hour < settings.night_end_hour
            if number in new_subs:
                item["new"].add(m["name"])
    rows = []
    for number, item in stats.items():
        subscribers = len(item["who"])
        night_share = item["night"] / item["charges"]
        new_share = len(item["new"]) / subscribers
        score = round(100 * (subscribers / count + night_share + new_share) / 3)
        rows.append({"number": number, "subscribers": subscribers, "who": sorted(item["who"]),
                     "charges": item["charges"], "total_som": money(item["total"]),
                     "night_share": round(night_share, 2), "new_subscription_share": round(new_share, 2),
                     "types": sorted(item["types"]), "score": score, "by_hour": [money(v) for v in item["by_hour"]]})
    return sorted(rows, key=lambda r: (-r["score"], -r["total_som"], r["number"]))
