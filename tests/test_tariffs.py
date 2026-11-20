from datetime import datetime
from decimal import Decimal

import pytest
from helpers import ch

from billcheck.parse import read_billing
from billcheck.report import summarize
from billcheck.tariffs import Advice, Plan, Usage, advise, all_offers, load_price, night_share, price_offer, usage_of

START = Plan("T01", "Старт", Decimal(100), 50, Decimal(1), 20, Decimal(2), Decimal(80), Decimal(1))
NIGHT = Plan("T04", "Ночной", Decimal(350), 150, Decimal(5), 50, Decimal(2), Decimal(70), Decimal(1),
             night_unlimited=True)
MINUTES = Plan("A02", "100 минут", Decimal(90), 100, Decimal(0), 0)
GB5 = Plan("A01", "5 ГБ", Decimal(100), 0, Decimal(5), 0)


def usage(minutes=0, sms=0, gb="0", night_gb="0", paid="1000"):
    return Usage(minutes, sms, Decimal(gb), Decimal(night_gb), Decimal(paid), Decimal(0))


def test_usage_counts_only_what_a_package_covers():
    charges = [
        ch("2026-09-01 10:00:00", "call", "996555000111", 61, 0, 2.0),    # 2 минуты: округление вверх
        ch("2026-09-01 10:05:00", "call", "996555000111", 0, 0, 0),       # нулевой звонок — 0 минут
        ch("2026-09-01 10:10:00", "call", "+971501234567", 60, 0, 40),    # международный — вне пакета
        ch("2026-09-01 11:00:00", "sms", "996555000111", 0, 0, 1),
        ch("2026-09-01 11:01:00", "sms", "7575", 0, 0, 10),               # платный короткий номер
        ch("2026-09-01 12:00:00", "data", "", 600, 512, 25.6),
        ch("2026-09-01 13:00:00", "subscription", "53530", 0, 0, 30),
        ch("2026-09-01 14:00:00", "content", "7575", 0, 0, 15),
    ]
    u = usage_of(charges)
    assert (u.minutes, u.sms, u.gb) == (2, 1, Decimal("0.5"))
    assert u.paid == Decimal("28.6")
    assert u.outside == Decimal(95)


def test_paid_plus_outside_is_the_whole_month(data_dir):
    charges, dropped = read_billing(data_dir / "billing_03.csv")
    u = usage_of(charges)
    assert float(u.paid + u.outside) == pytest.approx(summarize(charges, len(dropped))["total_som"])


@pytest.mark.parametrize("start, duration, share", [
    ("2026-09-01 01:00:00", 0, "1"),        # ровно начало ночи — ночь
    ("2026-09-01 07:00:00", 0, "0"),        # ровно конец ночи — уже день
    ("2026-09-01 00:30:00", 3600, "0.5"),   # входит в ночь
    ("2026-09-01 06:30:00", 3600, "0.5"),   # выходит из ночи
    ("2026-09-01 12:00:00", 3600, "0"),
])
def test_night_share_follows_tz2_borders(start, duration, share):
    assert night_share(datetime.fromisoformat(start), Decimal(duration)) == Decimal(share)


def test_price_counts_overage_after_package():
    offer = price_offer(START, (), usage(minutes=60, sms=25, gb="1.5"))
    # 100 абонплата + 10 мин × 2 + 0,5 ГБ × 80 + 5 SMS × 1
    assert offer.cost == Decimal(165)
    assert offer.extra_cost == {"call": Decimal(20), "data": Decimal(40), "sms": Decimal(5)}


def test_night_unlimited_removes_only_night_traffic():
    u = usage(gb="8", night_gb="4")
    assert price_offer(NIGHT, (), u).cost == Decimal(350)            # 4 ГБ днём влезают в 5 ГБ
    assert price_offer(START, (), u).cost == Decimal(100 + 7 * 80)   # у обычного тарифа ночь не бесплатна


def test_same_addon_can_be_taken_twice_and_ties_prefer_fewer_addons():
    offers = all_offers(usage(minutes=250), [START], [GB5, MINUTES])
    best = offers[0]
    assert [a.id for a in best.addons] == ["A02", "A02"]
    assert best.cost == Decimal(100 + 180 + 0)
    tie = all_offers(usage(), [START], [GB5, MINUTES])
    assert tie[0].addons == () and tie[0].cost == Decimal(100)


def test_advice_on_open_data(data_dir):
    charges, _ = read_billing(data_dir / "billing_03.csv")
    advice = advise(charges, data_dir)
    assert advice.best.plan.name == "Максимум"
    assert [a.name for a in advice.best.addons] == ["100 минут", "100 минут"]
    assert advice.savings > 800 and advice.worth_switching
    assert [o.plan.id for o in advice.options][0] == advice.best.plan.id
    assert len({o.plan.id for o in advice.options}) == len(advice.options) == 5


def test_small_savings_are_not_worth_switching():
    advice_usage = usage(paid="110")
    best = all_offers(advice_usage, [START], [])[0]
    assert advice_usage.paid - best.cost == Decimal(10)
    assert not Advice(advice_usage, best, [best]).worth_switching


def test_no_price_files_means_no_advice(tmp_path, data_dir):
    charges, _ = read_billing(data_dir / "billing_01.csv")
    assert load_price(tmp_path) is None
    assert advise(charges, tmp_path) is None
    (tmp_path / "tariffs.json").write_text("{broken", encoding="utf-8")
    assert advise(charges, tmp_path) is None


def test_nothing_to_compare_means_no_advice(data_dir):
    only_subscription = [ch("2026-09-01 13:00:00", "subscription", "53530", 0, 0, 30)]
    assert advise(only_subscription, data_dir) is None
