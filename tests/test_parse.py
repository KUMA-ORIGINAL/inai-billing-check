from datetime import datetime
from decimal import Decimal

import pytest

from billcheck.money import format_som, money, parse_amount
from billcheck.parse import BillingFileError, read_billing
from helpers import write_csv

BROKEN_AND_ONE_GOOD = [
    "",
    "2026-09-12 14:00:00,call",
    "2026-09-10 10:00:00,unknown,,0,0,1",
    "2026/09/12 14:00:00,call,+996700123456,60,0,1.2",
    "2026-09-31 10:00:00,call,+996555100000,60,0,1",
    "11.09.2026 12:00:00,sms,+996700123456,0,0,Infinity",
    "2026-09-10 10:00:00,data,,0,NaN,1",
    "2026-09-10 10:00:00,data,,0,20,broken",
    "2026-09-10 10:00:00,call,+996555100000,-1,0,1",
    '01.09.2026 13:03:21,call,+996700188574,43,0,"1,20"',
]
EXPECTED_REASONS = ["empty_line", "column_count", "unknown_type", "bad_datetime",
                    "bad_datetime", "bad_number", "bad_number", "bad_number", "bad_number"]


@pytest.mark.parametrize("name, valid, dropped", [
    ("billing_01", 338, 7), ("billing_02", 480, 9), ("billing_03", 596, 8),
    ("billing_04", 668, 13), ("billing_05", 775, 6)])
def test_open_files_counts(data_dir, name, valid, dropped):
    charges, bad = read_billing(data_dir / f"{name}.csv")
    assert (len(charges), len(bad)) == (valid, dropped)


def test_each_broken_kind(tmp_path):
    charges, bad = read_billing(write_csv(tmp_path, BROKEN_AND_ONE_GOOD))
    assert [b.reason for b in bad] == EXPECTED_REASONS
    assert [b.line for b in bad] == list(range(2, 11))
    assert bad[1].raw == "2026-09-12 14:00:00,call"
    assert len(charges) == 1
    good = charges[0]
    assert good.cost == Decimal("1.20") and good.dt == datetime(2026, 9, 1, 13, 3, 21)
    assert (good.line, good.type, good.number, good.duration_sec) == (11, "call", "+996700188574", Decimal(43))
    assert good.raw == '01.09.2026 13:03:21,call,+996700188574,43,0,"1,20"'


def test_crlf_and_bom(tmp_path):
    plain = read_billing(write_csv(tmp_path, BROKEN_AND_ONE_GOOD, name="lf.csv"))
    crlf = read_billing(write_csv(tmp_path, BROKEN_AND_ONE_GOOD, newline="\r\n", bom=True, name="crlf.csv"))
    assert crlf == plain


def test_empty_number_is_allowed(tmp_path):
    charges, bad = read_billing(write_csv(tmp_path, ['01.09.2026 14:41:43,data,,1501,"38,8","1,94"']))
    assert bad == [] and charges[0].number == "" and charges[0].mb == Decimal("38.8")


def test_header_only_is_empty_result(tmp_path):
    assert read_billing(write_csv(tmp_path, [])) == ([], [])


def test_missing_file(tmp_path):
    with pytest.raises(BillingFileError):
        read_billing(tmp_path / "nope.csv")


def test_empty_file(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_bytes(b"")
    with pytest.raises(BillingFileError):
        read_billing(path)


def test_headerless_file(tmp_path):
    path = write_csv(tmp_path, ["2026-09-01 09:32:08,sms,+996700188574,0,0,1.00"], header=False)
    with pytest.raises(BillingFileError):
        read_billing(path)


def test_binary_file(tmp_path):
    path = tmp_path / "picture.csv"
    path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xff\xfe")
    with pytest.raises(BillingFileError):
        read_billing(path)


@pytest.mark.parametrize("text, value", [
    ("1.20", Decimal("1.20")), ("1,20", Decimal("1.20")), (" 7 ", Decimal("7")), ("0", Decimal("0"))])
def test_parse_amount_ok(text, value):
    assert parse_amount(text) == value


@pytest.mark.parametrize("text", ["", "  ", "abc", "NaN", "nan", "Infinity", "-inf", "-1", "-0.01", "1,2,3"])
def test_parse_amount_rejects(text):
    assert parse_amount(text) is None


def test_format_som_russian():
    assert format_som(Decimal("2106.02")) == "2\u00a0106,02"
    assert format_som(Decimal("0.125")) == "0,13"
    assert format_som(Decimal("8285.42")) == "8\u00a0285,42"


def test_money_rounds_half_up():
    assert money(Decimal("0.125")) == 0.13
    assert money(Decimal("2.675")) == 2.68
    assert money(Decimal("1230.164999")) == 1230.16
