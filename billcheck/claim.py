"""Заявление в учебного оператора INAI Mobile на проверку и перерасчёт спорных списаний.

Текст собирается из claim_positions(): ими же пользуется HTML-отчёт, поэтому сумма
в интерфейсе и в тексте заявления считается по одним и тем же позициям.
"""
from datetime import date
from decimal import Decimal

from .explain import TYPE_NAMES, disputed, number_text, som
from .money import round_money
from .pipeline import Result

BLANK = "________________"
INTRO = "Прошу провести проверку и перерасчёт по следующим списаниям:"


def claim_positions(result: Result) -> list[dict]:
    """Спорные строки детализации (без day_spike), по одной позиции на строку."""
    reasons: dict[int, list[str]] = {}
    for a in result.anomalies:
        if a.line is not None:
            reasons.setdefault(a.line, []).append(a.reason)
    positions = []
    for a in sorted(disputed(result.anomalies).values(), key=lambda a: a.dt):
        charge = a.charge
        amount = (f"списано {som(charge.cost)}, к перерасчёту {som(a.amount)}" if a.amount != charge.cost
                  else som(a.amount))
        text = (f"{a.dt:%d.%m.%Y %H:%M:%S} — {TYPE_NAMES[charge.type]}, номер {number_text(charge.number)} — "
                f"{amount} (строка {a.line} детализации). Причина: {'; '.join(reasons[a.line])}.")
        positions.append({"line": a.line, "amount": round_money(a.amount), "text": text})
    return positions


def claim_basis(result: Result) -> str:
    if not result.charges:
        return f"Основание: детализация {result.source.name}."
    first = min(c.dt for c in result.charges)
    last = max(c.dt for c in result.charges)
    return f"Основание: детализация {result.source.name} за {first:%d.%m.%Y} — {last:%d.%m.%Y}."


def build_claim(result: Result, selected_lines: set[int] | None = None, msisdn: str | None = None,
                full_name: str | None = None, today: date | None = None) -> str:
    """Текст заявления. selected_lines — какие строки детализации включить (None — все спорные)."""
    positions = [p for p in claim_positions(result) if selected_lines is None or p["line"] in selected_lines]
    total = sum((p["amount"] for p in positions), Decimal(0))
    lines = ["В службу поддержки INAI Mobile",
             f"от абонента: {full_name or BLANK}",
             f"номер телефона: {msisdn or BLANK}",
             "",
             "ЗАЯВЛЕНИЕ о проверке и перерасчёте списаний",
             "",
             INTRO,
             ""]
    lines += [f"{i}. {p['text']}" for i, p in enumerate(positions, start=1)] or ["— спорные списания не выбраны —"]
    lines += ["",
              f"Итого к проверке: {som(total)}",
              "",
              claim_basis(result),
              f"Дата составления: {(today or date.today()):%d.%m.%Y}",
              f"Подпись: {BLANK}"]
    return "\n".join(lines) + "\n"
