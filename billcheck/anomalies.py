"""Пять правил аномалий из уточнений организаторов (CLARIFICATIONS_RU, раздел 4)."""
import math
import statistics
from dataclasses import dataclass, replace
from datetime import datetime, time
from decimal import Decimal

from .money import money
from .parse import Charge
from .report import daily_totals, normalize_number

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
SPIKE_WINDOW_DAYS = 7
SPIKE_Z = 3


@dataclass(frozen=True)
class Rules:
    """Пороги пяти правил. По умолчанию — строго уточнения организаторов; меняются только в демо «Пороги»."""
    night_start_hour: int = 0
    night_end_hour: int = 6
    intl_rate_limit: Decimal = RATE_LIMIT_PER_MIN
    duplicate_window_sec: int = DUPLICATE_WINDOW_SEC
    z_threshold: Decimal = Decimal(SPIKE_Z)
    z_window_days: int = SPIKE_WINDOW_DAYS

    @classmethod
    def from_dict(cls, data: dict | None) -> "Rules":
        """Пороги из запроса веб-демо: неизвестные ключи и мусор игнорируются, значения зажаты в разумные рамки."""
        data = data if isinstance(data, dict) else {}
        default = cls()

        def num(key: str, low, high, cast):
            try:
                value = Decimal(str(data[key]))
            except (KeyError, ArithmeticError, ValueError, TypeError):
                return getattr(default, key)
            if not value.is_finite():
                return getattr(default, key)
            return cast(min(max(value, Decimal(low)), Decimal(high)))

        start = num("night_start_hour", 0, 23, int)
        end = num("night_end_hour", 1, 24, int)
        return cls(night_start_hour=start, night_end_hour=max(end, start + 1),
                   intl_rate_limit=num("intl_rate_limit", 1, 1000, Decimal),
                   duplicate_window_sec=num("duplicate_window_sec", 0, 3600, int),
                   z_threshold=num("z_threshold", "0.5", 10, Decimal),
                   z_window_days=num("z_window_days", 2, 14, int))

    def as_dict(self) -> dict:
        return {"night_start_hour": self.night_start_hour, "night_end_hour": self.night_end_hour,
                "intl_rate_limit": float(self.intl_rate_limit), "duplicate_window_sec": self.duplicate_window_sec,
                "z_threshold": float(self.z_threshold), "z_window_days": self.z_window_days}

    def is_night(self, moment: datetime) -> bool:
        return self.night_start_hour <= moment.hour < self.night_end_hour

    def reasons(self) -> dict[str, str]:
        """Тексты reason. При порогах ТЗ — ровно REASONS."""
        if self == DEFAULT_RULES:
            return REASONS
        z = f"{self.z_threshold.normalize():f}"
        return {
            "night_charge": f"Платное SMS/контент ночью с {self.night_start_hour:02d}:00 до {self.night_end_hour:02d}:00",
            "new_subscription": REASONS["new_subscription"],
            "duplicate_charge": f"Одинаковое списание в пределах {self.duplicate_window_sec} секунд",
            "international_rate": f"Международный звонок дороже {self.intl_rate_limit.normalize():f} сом/мин",
            "day_spike": f"Расходы дня выше среднего предыдущих {self.z_window_days} дней: z-score > {z}",
        }


DEFAULT_RULES = Rules()


@dataclass(frozen=True)
class Anomaly:
    dt: datetime
    type: str
    anomaly_type: str
    amount: Decimal
    reason: str
    line: int | None = None
    charge: Charge | None = None
    previous: Charge | None = None   # duplicate_charge: более раннее такое же списание
    baseline: Decimal | None = None  # day_spike: средние расходы семи предыдущих дней

    def as_dict(self) -> dict:
        """Ровно поля эталона организаторов."""
        return {"datetime": self.dt.strftime("%Y-%m-%d %H:%M:%S"), "type": self.type,
                "anomaly_type": self.anomaly_type, "amount_som": money(self.amount), "reason": self.reason}


def _from_charge(charge: Charge, kind: str, amount: Decimal, rules: Rules = DEFAULT_RULES) -> Anomaly:
    return Anomaly(charge.dt, charge.type, kind, amount, rules.reasons()[kind], charge.line, charge)


def is_short_number(number: str) -> bool:
    return 3 <= len(number) <= 6 and number.isdigit()


def find_night_charges(charges: list[Charge], rules: Rules = DEFAULT_RULES) -> list[Anomaly]:
    return [_from_charge(c, "night_charge", c.cost, rules) for c in charges
            if c.type in NIGHT_TYPES and c.cost > 0 and rules.is_night(c.dt)]


def find_new_subscription(charges: list[Charge], rules: Rules = DEFAULT_RULES) -> list[Anomaly]:
    """Первая по порядку строк файла подписка на короткий номер из 3–6 цифр."""
    for charge in sorted(charges, key=lambda c: c.line):
        if charge.type == "subscription" and is_short_number(charge.number.strip()):
            return [_from_charge(charge, "new_subscription", charge.cost, rules)]
    return []


def find_duplicates(charges: list[Charge], rules: Rules = DEFAULT_RULES) -> list[Anomaly]:
    """Одинаковые type, number, duration_sec, mb, cost в пределах 60 с; флаг — на более позднюю."""
    last_seen: dict[tuple, Charge] = {}
    found = []
    for charge in sorted(charges, key=lambda c: (c.dt, c.line)):
        key = (charge.type, normalize_number(charge.number), charge.duration_sec, charge.mb, charge.cost)
        previous = last_seen.get(key)
        if previous is not None and (charge.dt - previous.dt).total_seconds() <= rules.duplicate_window_sec:
            found.append(replace(_from_charge(charge, "duplicate_charge", charge.cost, rules), previous=previous))
        last_seen[key] = charge
    return found


def is_international(number: str) -> bool:
    number = number.strip()
    return number.startswith("+") and not number.startswith("+996")


def find_international(charges: list[Charge], rules: Rules = DEFAULT_RULES) -> list[Anomaly]:
    found = []
    limit = rules.intl_rate_limit
    for c in charges:
        if not is_international(c.number) or c.duration_sec <= 0:
            continue
        if c.cost * 60 / c.duration_sec > limit:
            overpay = max(Decimal(0), c.cost - limit * c.duration_sec / 60)
            found.append(_from_charge(c, "international_rate", overpay, rules))
    return found


def _z_score(value: Decimal, window: list[Decimal]) -> float:
    mean = statistics.mean(window)
    std = statistics.pstdev(window)  # population std, ddof=0
    if std == 0:
        return math.inf if value > mean else 0.0
    return float((value - mean) / std)


def billing_month(charges: list[Charge]) -> list[Charge]:
    """Списания основного месяца детализации — месяца медианного по времени списания.
    Случайная строка из другого месяца или года не сдвигает ряд дней и не даёт ложных всплесков."""
    if not charges:
        return []
    middle = sorted(c.dt for c in charges)[len(charges) // 2]
    return [c for c in charges if (c.dt.year, c.dt.month) == (middle.year, middle.month)]


def find_day_spikes(charges: list[Charge], rules: Rules = DEFAULT_RULES) -> list[Anomaly]:
    """День дороже семи предыдущих полных дней (нулевые дни считаются): z-score > 3.
    Ряд — дни основного месяца с его 1-го числа."""
    series = list(daily_totals(billing_month(charges)).items())
    found = []
    size = rules.z_window_days
    for i in range(size, len(series)):
        day, value = series[i]
        window = [total for _, total in series[i - size:i]]
        if _z_score(value, window) > rules.z_threshold:
            mean = statistics.mean(window)
            found.append(Anomaly(datetime.combine(day, time()), "day_spike", "day_spike",
                                 value - mean, rules.reasons()["day_spike"], baseline=mean))
    return found


RULES = (find_night_charges, find_new_subscription, find_duplicates, find_international, find_day_spikes)


def find_all(charges: list[Charge], rules: Rules = DEFAULT_RULES) -> list[Anomaly]:
    """Все пять правил; на каждое правило — отдельная аномалия; сортировка по времени."""
    found = [anomaly for rule in RULES for anomaly in rule(charges, rules)]
    return sorted(found, key=lambda a: (a.dt, a.anomaly_type))
