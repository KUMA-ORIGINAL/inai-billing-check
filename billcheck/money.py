"""Деньги и числа из детализации: только Decimal, округление ROUND_HALF_UP до 0.01."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")


def parse_amount(text: str) -> Decimal | None:
    """Число из ячейки CSV: точка или запятая. None — пусто, не число, NaN, Infinity, < 0."""
    cleaned = text.strip().replace(",", ".")
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0:
        return None
    return value


def round_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def money(value: Decimal) -> float:
    """Сумма для JSON: float с двумя знаками."""
    return float(round_money(value))
