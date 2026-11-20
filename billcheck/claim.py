"""Заявление в учебного оператора INAI Mobile на проверку и перерасчёт спорных списаний."""
from datetime import date
from decimal import Decimal

from .explain import TYPE_NAMES, disputed, number_text, som
from .money import round_money
from .pipeline import Result

BLANK = "________________"


def build_claim(result: Result, selected_lines: set[int] | None = None, msisdn: str | None = None,
                full_name: str | None = None, today: date | None = None) -> str:
    """Текст заявления. selected_lines — какие строки детализации включить (None — все спорные)."""
    positions = sorted((a for line, a in disputed(result.anomalies).items()
                        if selected_lines is None or line in selected_lines), key=lambda a: a.dt)
    total = round_money(sum((a.amount for a in positions), Decimal(0)))
    reasons = {}
    for a in result.anomalies:
        if a.line is not None:
            reasons.setdefault(a.line, []).append(a.reason)

    lines = ["В службу поддержки INAI Mobile",
             f"от абонента: {full_name or BLANK}",
             f"номер телефона: {msisdn or BLANK}",
             "",
             "ЗАЯВЛЕНИЕ о проверке и перерасчёте списаний",
             "",
             "Прошу провести проверку и перерасчёт по следующим списаниям:",
             ""]
    for i, a in enumerate(positions, start=1):
        charge = a.charge
        amount = (f"списано {som(charge.cost)}, к перерасчёту {som(a.amount)}" if a.amount != charge.cost
                  else som(a.amount))
        lines.append(f"{i}. {a.dt:%d.%m.%Y %H:%M:%S} — {TYPE_NAMES[charge.type]}, номер "
                     f"{number_text(charge.number)} — {amount} (строка {a.line} детализации). "
                     f"Причина: {'; '.join(reasons[a.line])}.")
    if not positions:
        lines.append("— спорные списания не выбраны —")
    lines += ["",
              f"Итого к проверке: {total:.2f} сом",
              ""]
    if result.charges:
        first = min(c.dt for c in result.charges)
        last = max(c.dt for c in result.charges)
        lines.append(f"Основание: детализация {result.source.name} за {first:%d.%m.%Y} — {last:%d.%m.%Y}.")
    lines += [f"Дата составления: {(today or date.today()):%d.%m.%Y}",
              f"Подпись: {BLANK}"]
    return "\n".join(lines) + "\n"
