"""Бонус ТЗ: PDF-детализация → тот же CSV, что разбирает ядро.

Читаем текстовый слой PDF (pdfplumber, необязательная зависимость: pip install pdfplumber). Строка
детализации узнаётся по дате в начале — любой из двух форматов ТЗ; дальше колонки как в CSV:
datetime, type, number, duration_sec, mb, cost_som. Всё, что не похоже на строку детализации
(шапка, итоги, номера страниц), пропускается. Скан без текстового слоя прочитать нельзя — скажем об этом.
Для демо есть и обратное: csv_to_pdf() печатает CSV в простой PDF без сторонних пакетов.
"""
import csv
import io
import re
import zlib

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


# ---------- демо: свой PDF из CSV (только стандартная библиотека)
PDF_TITLE = "INAI MOBILE - DETALIZACIYA"
PDF_LINES_PER_PAGE = 62


def _pdf_line(row: list[str]) -> str:
    """Строка детализации в порядке колонок ТЗ, через пробелы; пустой номер (интернет) пропускается."""
    return " ".join(v.strip() for v in row if v.strip())


def _pdf_escape(text: str) -> bytes:
    raw = text.encode("latin-1", "replace")  # стандартный шрифт Type1: только латиница
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _pdf_page(lines: list[str], page: int, pages: int) -> bytes:
    out = [b"BT /F1 8 Tf 10 TL 40 800 Td"]
    for text in lines + ["", f"page {page} / {pages}"]:
        out.append(b"(" + _pdf_escape(text) + b") Tj T*")
    out.append(b"ET")
    return b"\n".join(out)


def csv_to_pdf(text: str, title: str = PDF_TITLE) -> bytes:
    """CSV-детализация → простой текстовый PDF (A4, Courier), который читает pdf_to_csv.

    Колонки переставляются в порядок ТЗ по заголовку; строки, которые не разбить на 6 колонок,
    печатаются как есть — в настоящем PDF оператора тоже бывает мусор, text_to_csv его пропустит.
    """
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    if not rows:
        raise BillingFileError("CSV пуст — нечего печатать в PDF.")
    header = [h.strip().lower() for h in rows[0]]
    order = [header.index(c) for c in COLUMNS] if all(c in header for c in COLUMNS) else None
    body = [_pdf_line([r[i] for i in order] if order and len(r) == len(header) else r) for r in rows[1:]]
    lines = [title, "", "  ".join(COLUMNS), ""] + body
    chunks = [lines[i:i + PDF_LINES_PER_PAGE] for i in range(0, len(lines), PDF_LINES_PER_PAGE)]
    font, pages_id = 3, 2
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        font: b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
    }
    kids = []
    for n, chunk in enumerate(chunks):
        page_id, content_id = 4 + 2 * n, 5 + 2 * n
        stream = zlib.compress(_pdf_page(chunk, n + 1, len(chunks)))
        objects[content_id] = (b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream)
                               + stream + b"\nendstream")
        objects[page_id] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % content_id)
        kids.append(b"%d 0 R" % page_id)
    objects[pages_id] = b"<< /Type /Pages /Kids [" + b" ".join(kids) + b"] /Count %d >>" % len(kids)
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for oid in sorted(objects):
        offsets[oid] = len(pdf)
        pdf += b"%d 0 obj\n" % oid + objects[oid] + b"\nendobj\n"
    xref = len(pdf)
    size = max(objects) + 1
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % size
    pdf += b"".join(b"%010d 00000 n \n" % offsets[i] for i in range(1, size))
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, xref)
    return bytes(pdf)
