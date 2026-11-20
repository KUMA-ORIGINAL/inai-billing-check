"""Бонус ТЗ: PDF-детализация → тот же CSV, что разбирает ядро.

Читаем текстовый слой PDF (pdfplumber, необязательная зависимость: pip install pdfplumber). Строка
детализации узнаётся по дате в начале — любой из двух форматов ТЗ; дальше колонки как в CSV:
datetime, type, number, duration_sec, mb, cost_som. Всё, что не похоже на строку детализации
(шапка, итоги, номера страниц), пропускается. Скан без текстового слоя прочитать нельзя — скажем об этом.
"""
import csv
import io
import re

from .parse import COLUMNS, TYPES, BillingFileError

ROW = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}|\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<type>" + "|".join(TYPES) + r")\s+(?P<rest>.*)$")
NUMBER = r"-?\d+(?:[.,]\d+)?"


def text_to_csv(text: str) -> str:
    """Строки детализации из текста PDF → CSV с заголовком ТЗ. У data номер пустой."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for line in text.splitlines():
        match = ROW.match(line.strip())
        if not match:
            continue
        parts = match["rest"].split()
        if len(parts) == 3:  # у интернета номера нет
            number, values = "", parts
        elif len(parts) == 4:
            number, values = parts[0], parts[1:]
        else:
            continue
        if not all(re.fullmatch(NUMBER, v) for v in values):
            continue
        writer.writerow([match["dt"], match["type"], number, *values])
    return out.getvalue()


def pdf_to_csv(raw: bytes, name: str = "детализация.pdf") -> str:
    try:
        import pdfplumber
    except ImportError as exc:
        raise BillingFileError(
            f"{name}: для PDF-детализации нужен пакет pdfplumber (pip install pdfplumber). "
            "CSV из личного кабинета читается без него.") from exc
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as exc:  # битый файл, пароль, не PDF
        raise BillingFileError(f"{name}: не удалось открыть PDF ({type(exc).__name__}).") from exc
    data = text_to_csv(text)
    if data.count("\n") <= 1:
        raise BillingFileError(f"{name}: в PDF нет строк детализации. Если это скан — нужен CSV из личного кабинета.")
    return data
