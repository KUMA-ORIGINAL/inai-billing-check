"""Пояснения человеческим языком, советы из FAQ оператора и сумма «возможно лишнего»."""
import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from .anomalies import Anomaly
from .money import format_som, round_money

FAQ_PATH = Path(__file__).resolve().parent.parent / "data" / "faq.json"

TYPE_NAMES = {"call": "звонок", "sms": "SMS", "data": "интернет", "subscription": "подписка", "content": "контент"}
# Какой ответ FAQ оператора (05_support/faq.json) подходит к аномалии.
ADVICE_FAQ_ID = {"night_charge": 8, "new_subscription": 8,
                 "duplicate_charge": 14, "international_rate": 14, "day_spike": 15}


def som(value: Decimal) -> str:
    return f"{format_som(value)} сом"


def number_text(number: str) -> str:
    return number or "без номера"


def duration_text(seconds: Decimal) -> str:
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes} мин {rest} с" if rest else f"{minutes} мин"


def ratio_text(ratio: Decimal) -> str:
    return f"{ratio:.1f}".replace(".", ",")


def explain(a: Anomaly) -> str:
    dt, charge = a.dt, a.charge
    day = dt.strftime("%d.%m")
    if a.anomaly_type == "night_charge":
        what = "SMS" if a.type == "sms" else "контент"
        return (f"{day} в {dt:%H:%M} списано {som(a.amount)} за платное {what} с номера {number_text(charge.number)}. "
                "Ночные платные списания часто приходят от подписок, на которые вы не соглашались.")
    if a.anomaly_type == "new_subscription":
        return (f"{day} подключена подписка на короткий номер {charge.number}: {som(a.amount)}. "
                "Если вы её не оформляли — её можно отключить и попросить вернуть деньги.")
    if a.anomaly_type == "duplicate_charge":
        gap = int((charge.dt - a.previous.dt).total_seconds()) if a.previous else 0
        return (f"{day} в {dt:%H:%M:%S} одно и то же списание ({TYPE_NAMES[a.type]} на {number_text(charge.number)}, "
                f"{som(charge.cost)}) прошло дважды с разницей {gap} с.")
    if a.anomaly_type == "international_rate":
        rate = charge.cost * 60 / charge.duration_sec
        return (f"Звонок на {charge.number} ({duration_text(charge.duration_sec)}) стоил {som(rate)}/мин — "
                f"дороже 20 сом/мин. Переплата — {som(a.amount)}.")
    if a.anomaly_type == "day_spike":
        mean = a.baseline if a.baseline is not None else Decimal(0)
        spent = mean + a.amount
        if mean > 0:
            ratio = f"в {ratio_text(spent / mean)} раза больше обычного ({som(mean)} в день за предыдущую неделю)"
        else:
            ratio = "хотя за предыдущую неделю расходов не было"
        return f"{day} вы потратили {som(spent)} — {ratio}."
    return a.reason


@lru_cache(maxsize=4)
def load_faq(path: Path = FAQ_PATH) -> dict[int, dict]:
    try:
        return {item["id"]: item for item in json.loads(path.read_text(encoding="utf-8"))}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def advice(a: Anomaly, lang: str = "ru") -> str:
    item = load_faq().get(ADVICE_FAQ_ID.get(a.anomaly_type, 0), {})
    return item.get(f"answer_{lang}", "")


def disputed(anomalies: list[Anomaly]) -> dict[int, Anomaly]:
    """Спорные строки детализации без day_spike: одна строка — одна позиция, большая из сумм."""
    by_line: dict[int, Anomaly] = {}
    for a in anomalies:
        if a.anomaly_type == "day_spike" or a.line is None:
            continue
        if a.line not in by_line or a.amount > by_line[a.line].amount:
            by_line[a.line] = a
    return by_line


def possible_overpay(anomalies: list[Anomaly]) -> Decimal:
    """«Возможно лишнее»: day_spike не входит (он агрегирует те же списания), строка считается один раз."""
    return round_money(sum((a.amount for a in disputed(anomalies).values()), Decimal(0)))
