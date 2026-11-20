"""Тарифный советник: сколько стоил бы тот же месяц на пакетном тарифе INAI Mobile.

Прайс — учебные тарифы и доппакеты из ТЗ 2 (data/tariffs.json, data/addons.json), правила расчёта —
CLARIFICATIONS_RU.md, раздел 2: каждый звонок округляется вверх до минуты, 1 ГБ = 1024 МБ, ночной
безлимит [01:00, 07:00) снимает с интернета только пересечение сессии с ночью, доппакеты 0–2 (можно
одинаковые). Это совет, а не аномалия: в anomalies.json и report.json он не попадает.

В пакет входят только местные звонки, обычные SMS и интернет. Международные звонки, подписки, контент
и SMS на короткие платные номера стоят одинаково на любом тарифе и в сравнение не входят.
"""
import itertools
import json
import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from .anomalies import billing_month, is_international, is_short_number
from .parse import Charge

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TARIFFS_FILE, ADDONS_FILE = "tariffs.json", "addons.json"
NIGHT_START, NIGHT_END = time(1), time(7)
MB_PER_GB = Decimal(1024)
MAX_ADDONS = 2
# Менять тариф ради копеек не советуем. Порог как в ТЗ 2: экономия за 3 месяца строго больше 50 сом.
MIN_SAVINGS_3M = Decimal(50)


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    fee: Decimal
    minutes: int
    gb: Decimal
    sms: int
    call_rate: Decimal = Decimal(0)
    data_rate: Decimal = Decimal(0)
    sms_rate: Decimal = Decimal(0)
    night_unlimited: bool = False


@dataclass(frozen=True)
class Usage:
    """Потребление за месяц, которое может войти в пакет, и сколько за него списали поштучно."""
    minutes: int
    sms: int
    gb: Decimal
    night_gb: Decimal  # часть интернета, попавшая в [01:00, 07:00)
    paid: Decimal      # сколько за эти звонки, SMS и интернет списано по детализации
    outside: Decimal   # международные звонки, подписки, контент, платные SMS — вне пакетов


@dataclass(frozen=True)
class Offer:
    plan: Plan
    addons: tuple[Plan, ...]
    cost: Decimal
    fee: Decimal
    extra_minutes: Decimal
    extra_gb: Decimal
    extra_sms: Decimal

    @property
    def extra_cost(self) -> dict[str, Decimal]:
        return {"call": self.extra_minutes * self.plan.call_rate, "data": self.extra_gb * self.plan.data_rate,
                "sms": self.extra_sms * self.plan.sms_rate}

    def sort_key(self) -> tuple:
        # Равная цена: меньше доппакетов, затем id тарифа и доппакетов (как в ТЗ 2).
        return self.cost, len(self.addons), self.plan.id, tuple(sorted(a.id for a in self.addons))


@dataclass(frozen=True)
class Advice:
    usage: Usage
    best: Offer
    options: list[Offer]  # лучший вариант для каждого тарифа, по возрастанию цены

    @property
    def savings(self) -> Decimal:
        return self.usage.paid - self.best.cost

    @property
    def worth_switching(self) -> bool:
        return self.savings * 3 > MIN_SAVINGS_3M


def _dec(value) -> Decimal:
    return Decimal(str(value))


def _plan(item: dict, overage: bool) -> Plan:
    rates = item.get("overage", {}) if overage else {}
    return Plan(id=str(item["id"]), name=str(item["name"]), fee=_dec(item["fee"]), minutes=int(item["minutes"]),
                gb=_dec(item["gb"]), sms=int(item["sms"]), call_rate=_dec(rates.get("call", 0)),
                data_rate=_dec(rates.get("data", 0)), sms_rate=_dec(rates.get("sms", 0)),
                night_unlimited=bool(item.get("night_unlimited", False)))


def load_price(data_dir: Path = DATA_DIR) -> tuple[list[Plan], list[Plan]] | None:
    """Тарифы и доппакеты. Нет файлов или они битые — None: отчёт просто без советника."""
    try:
        tariffs = json.loads((Path(data_dir) / TARIFFS_FILE).read_text(encoding="utf-8-sig"))["tariffs"]
        addons = json.loads((Path(data_dir) / ADDONS_FILE).read_text(encoding="utf-8-sig"))
        plans = [_plan(item, overage=True) for item in tariffs]
        extras = [_plan(item, overage=False) for item in addons]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return (plans, extras) if plans else None


def night_share(start: datetime, duration_sec: Decimal) -> Decimal:
    """Доля сессии в ночи [01:00, 07:00). Нулевая длительность — по моменту начала."""
    if duration_sec <= 0:
        return Decimal(1) if NIGHT_START <= start.time() < NIGHT_END else Decimal(0)
    end = start + timedelta(seconds=float(duration_sec))
    overlap = 0.0
    day = start.date() - timedelta(days=1)
    while day <= end.date():
        lo, hi = datetime.combine(day, NIGHT_START), datetime.combine(day, NIGHT_END)
        overlap += max(0.0, (min(end, hi) - max(start, lo)).total_seconds())
        day += timedelta(days=1)
    return _dec(overlap) / duration_sec


def usage_of(charges: list[Charge]) -> Usage:
    """Потребление основного месяца детализации (тот же месяц, что и в поиске всплесков)."""
    minutes = sms = 0
    gb = night_gb = paid = outside = Decimal(0)
    for c in billing_month(charges):
        number = c.number.strip()
        if c.type == "call" and not is_international(number):
            minutes += math.ceil(c.duration_sec / 60) if c.duration_sec > 0 else 0
        elif c.type == "sms" and not is_short_number(number):
            sms += 1
        elif c.type == "data":
            volume = c.mb / MB_PER_GB
            gb += volume
            night_gb += volume * night_share(c.dt, c.duration_sec)
        else:
            outside += c.cost
            continue
        paid += c.cost
    return Usage(minutes, sms, gb, night_gb, paid, outside)


def price_offer(plan: Plan, addons: tuple[Plan, ...], usage: Usage) -> Offer:
    minutes = plan.minutes + sum(a.minutes for a in addons)
    gb = plan.gb + sum((a.gb for a in addons), Decimal(0))
    sms = plan.sms + sum(a.sms for a in addons)
    used_gb = usage.gb - (usage.night_gb if plan.night_unlimited else 0)
    fee = plan.fee + sum((a.fee for a in addons), Decimal(0))
    extra_minutes = Decimal(max(0, usage.minutes - minutes))
    extra_gb = max(Decimal(0), used_gb - gb)
    extra_sms = Decimal(max(0, usage.sms - sms))
    cost = fee + extra_minutes * plan.call_rate + extra_gb * plan.data_rate + extra_sms * plan.sms_rate
    return Offer(plan, addons, cost, fee, extra_minutes, extra_gb, extra_sms)


def all_offers(usage: Usage, plans: list[Plan], addons: list[Plan]) -> list[Offer]:
    combos = [combo for k in range(MAX_ADDONS + 1)
              for combo in itertools.combinations_with_replacement(sorted(addons, key=lambda a: a.id), k)]
    return sorted((price_offer(plan, combo, usage) for plan in plans for combo in combos),
                  key=Offer.sort_key)


def advise(charges: list[Charge], data_dir: Path = DATA_DIR) -> Advice | None:
    """Лучший тариф с доппакетами для этого месяца. None — нет прайса или нечего сравнивать."""
    price = load_price(data_dir)
    if price is None:
        return None
    usage = usage_of(charges)
    if usage.paid <= 0:
        return None
    offers = all_offers(usage, *price)
    per_plan: dict[str, Offer] = {}
    for offer in offers:
        per_plan.setdefault(offer.plan.id, offer)
    return Advice(usage, offers[0], sorted(per_plan.values(), key=Offer.sort_key))
