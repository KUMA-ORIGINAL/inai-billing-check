"""Разбор грязной детализации: каждая плохая строка отбрасывается целиком с причиной."""
import csv
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterator

from .money import parse_amount

TYPES = ("call", "sms", "data", "subscription", "content")
COLUMNS = ("datetime", "type", "number", "duration_sec", "mb", "cost_som")

# Порядок проверок = порядок причин в уточнениях организаторов.
EMPTY_LINE, COLUMN_COUNT, UNKNOWN_TYPE, BAD_DATETIME, BAD_NUMBER = (
    "empty_line", "column_count", "unknown_type", "bad_datetime", "bad_number")

_DATE_FORMATS = (
    (re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"), "%Y-%m-%d %H:%M:%S"),
    (re.compile(r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2}"), "%d.%m.%Y %H:%M:%S"),
)


class BillingFileError(Exception):
    """Файл нельзя разобрать целиком: нет файла, он пуст, не текст или без заголовка."""


@dataclass(frozen=True)
class Charge:
    line: int
    dt: datetime
    type: str
    number: str
    duration_sec: Decimal
    mb: Decimal
    cost: Decimal


@dataclass(frozen=True)
class Dropped:
    line: int
    reason: str
    raw: str


def parse_datetime(text: str) -> datetime | None:
    text = text.strip()
    for pattern, fmt in _DATE_FORMATS:
        if pattern.fullmatch(text):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:  # 2026-09-31 и подобные несуществующие даты
                return None
    return None


def _records(lines: Iterator[str]) -> Iterator[tuple[int, list[str], str]]:
    """(номер первой физической строки, поля, исходный текст) для каждой записи CSV."""
    consumed: list[str] = []

    def tap() -> Iterator[str]:
        for physical in lines:
            consumed.append(physical)
            yield physical

    reader = csv.reader(tap())
    line_no = 1
    for row in reader:
        raw = "".join(consumed).rstrip("\r\n")
        yield line_no, row, raw
        line_no += len(consumed)
        consumed.clear()


def _classify(row: list[str], columns: dict[str, int], width: int) -> tuple[str | None, tuple]:
    if not row:
        return EMPTY_LINE, ()
    if len(row) != width:
        return COLUMN_COUNT, ()
    get = lambda name: row[columns[name]].strip()  # noqa: E731
    type_ = get("type")
    if type_ not in TYPES:
        return UNKNOWN_TYPE, ()
    dt = parse_datetime(get("datetime"))
    if dt is None:
        return BAD_DATETIME, ()
    numbers = [parse_amount(get(name)) for name in ("duration_sec", "mb", "cost_som")]
    if any(value is None for value in numbers):
        return BAD_NUMBER, ()
    return None, (dt, type_, get("number"), *numbers)


def _header_columns(header: list[str]) -> dict[str, int]:
    names = [cell.strip().lower() for cell in header]
    missing = [name for name in COLUMNS if name not in names]
    if missing:
        raise BillingFileError(
            "В первой строке нет заголовка детализации. Нужны колонки: " + ",".join(COLUMNS)
            + (f" (не найдены: {', '.join(missing)})" if len(missing) < len(COLUMNS) else ""))
    return {name: names.index(name) for name in COLUMNS}


def read_billing(path: str | Path) -> tuple[list[Charge], list[Dropped]]:
    """Корректные списания и отброшенные строки. Заголовок — строка 1, в отброшенные не входит."""
    path = Path(path)
    if not path.is_file():
        raise BillingFileError(f"Файл не найден: {path}")
    charges: list[Charge] = []
    dropped: list[Dropped] = []
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            records = _records(handle)
            first = next(records, None)
            if first is None:
                raise BillingFileError(f"Файл пуст: {path.name}")
            columns = _header_columns(first[1])
            width = len(first[1])
            for line_no, row, raw in records:
                reason, fields = _classify(row, columns, width)
                if reason:
                    dropped.append(Dropped(line_no, reason, raw))
                else:
                    charges.append(Charge(line_no, *fields))
    except UnicodeDecodeError as exc:
        raise BillingFileError(f"Файл {path.name} — не текст в UTF-8. Нужна детализация в CSV.") from exc
    except csv.Error as exc:
        raise BillingFileError(f"Не удалось прочитать CSV {path.name}: {exc}") from exc
    return charges, dropped
