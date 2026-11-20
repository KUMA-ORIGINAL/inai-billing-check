"""Пять правил аномалий из уточнений организаторов (CLARIFICATIONS_RU, раздел 4)."""
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal

from .money import money
from .parse import Charge
from .report import normalize_number

REASONS = {
    "night_charge": "Платное SMS/контент ночью с 00:00 до 06:00",
    "new_subscription": "Новая подписка на короткий номер",
    "duplicate_charge": "Одинаковое списание в пределах 60 секунд",
    "international_rate": "Международный звонок дороже 20 сом/мин",
    "day_spike": "Расходы дня выше среднего предыдущих 7 дней: z-score > 3",
}

NIGHT_END = time(6, 0)
NIGHT_TYPES = ("sms", "content")
DUPLICATE_WINDOW_SEC = 60
RATE_LIMIT_PER_MIN = Decimal(20)


@dataclass(frozen=True)
class Anomaly:
    dt: datetime
    type: str
    anomaly_type: str
    amount: Decimal
    reason: str
    line: int | None = None
    charge: Charge | None = None

    def as_dict(self) -> dict:
        """Ровно поля эталона организаторов."""
        return {"datetime": self.dt.strftime("%Y-%m-%d %H:%M:%S"), "type": self.type,
                "anomaly_type": self.anomaly_type, "amount_som": money(self.amount), "reason": self.reason}


def _from_charge(charge: Charge, kind: str, amount: Decimal) -> Anomaly:
    return Anomaly(charge.dt, charge.type, kind, amount, REASONS[kind], charge.line, charge)


def is_short_number(number: str) -> bool:
    return 3 <= len(number) <= 6 and number.isdigit()


def find_night_charges(charges: list[Charge]) -> list[Anomaly]:
    return [_from_charge(c, "night_charge", c.cost) for c in charges
            if c.type in NIGHT_TYPES and c.cost > 0 and c.dt.time() < NIGHT_END]


def find_new_subscription(charges: list[Charge]) -> list[Anomaly]:
    """Первая по порядку строк файла подписка на короткий номер из 3–6 цифр."""
    for charge in sorted(charges, key=lambda c: c.line):
        if charge.type == "subscription" and is_short_number(charge.number.strip()):
            return [_from_charge(charge, "new_subscription", charge.cost)]
    return []


def find_duplicates(charges: list[Charge]) -> list[Anomaly]:
    """Одинаковые type, number, duration_sec, mb, cost в пределах 60 с; флаг — на более позднюю."""
    last_seen: dict[tuple, datetime] = {}
    found = []
    for charge in sorted(charges, key=lambda c: (c.dt, c.line)):
        key = (charge.type, normalize_number(charge.number), charge.duration_sec, charge.mb, charge.cost)
        previous = last_seen.get(key)
        if previous is not None and (charge.dt - previous).total_seconds() <= DUPLICATE_WINDOW_SEC:
            found.append(_from_charge(charge, "duplicate_charge", charge.cost))
        last_seen[key] = charge.dt
    return found


def is_international(number: str) -> bool:
    number = number.strip()
    return number.startswith("+") and not number.startswith("+996")


def find_international(charges: list[Charge]) -> list[Anomaly]:
    found = []
    for c in charges:
        if not is_international(c.number) or c.duration_sec <= 0:
            continue
        if c.cost * 60 / c.duration_sec > RATE_LIMIT_PER_MIN:
            overpay = max(Decimal(0), c.cost - RATE_LIMIT_PER_MIN * c.duration_sec / 60)
            found.append(_from_charge(c, "international_rate", overpay))
    return found
