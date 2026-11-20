"""Обязательный отчёт ТЗ: суммы, категории, календарные дни, топ-5 номеров."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from .money import money
from .parse import TYPES, Charge

ZERO = Decimal(0)


def normalize_number(number: str) -> str:
    """Местный номер без плюса (996XXXXXXXXX) приводим к +996XXXXXXXXX; остальное как есть."""
    number = number.strip()
    if len(number) == 12 and number.isdigit() and number.startswith("996"):
        return "+" + number
    return number


def daily_totals(charges: list[Charge]) -> dict[date, Decimal]:
    """Расходы по дням без пропусков: с 1-го числа месяца первой записи до дня последней."""
    if not charges:
        return {}
    days = [c.dt.date() for c in charges]
    start, end = min(days).replace(day=1), max(days)
    totals = {start + timedelta(days=i): ZERO for i in range((end - start).days + 1)}
    for charge in charges:
        totals[charge.dt.date()] += charge.cost
    return totals


def summarize(charges: list[Charge], dropped_count: int) -> dict:
    by_category = {type_: ZERO for type_ in TYPES}
    by_number: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for charge in charges:
        by_category[charge.type] += charge.cost
        number = normalize_number(charge.number)
        if number:
            by_number[number] += charge.cost
    top5 = sorted(by_number.items(), key=lambda item: (-item[1], item[0]))[:5]
    return {
        "valid_rows": len(charges),
        "dropped_rows": dropped_count,
        "total_som": money(sum((c.cost for c in charges), ZERO)),
        "by_category": {type_: money(total) for type_, total in by_category.items()},
        "by_day": {day.isoformat(): money(total) for day, total in daily_totals(charges).items()},
        "top5_numbers": [{"number": number, "cost_som": money(total)} for number, total in top5],
    }
