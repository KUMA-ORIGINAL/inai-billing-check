"""Демо-PDF из CSV (csv_to_pdf) и обратно в CSV — без сторонних пакетов."""
import re
import zlib

import pytest
from helpers import DATA_DIR, write_csv

from billcheck.pdf import PDF_TITLE, csv_to_pdf, text_to_csv
from billcheck.pipeline import analyze

SAME_FIELDS = ("valid_rows", "total_som", "by_category", "by_day", "top5_numbers", "anomalies")


def pdf_text(raw: bytes) -> str:
    """Текст нашего простого PDF: строки из операторов Tj во всех потоках."""
    lines = []
    for stream in re.findall(rb"stream\n(.*?)\nendstream", raw, re.S):
        for item in re.findall(rb"\(((?:\\.|[^\\)])*)\) Tj", zlib.decompress(stream)):
            lines.append(re.sub(rb"\\(.)", rb"\1", item).decode("latin-1"))
    return "\n".join(lines)


def test_pdf_structure():
    raw = csv_to_pdf((DATA_DIR / "billing_03.csv").read_text(encoding="utf-8-sig"))
    assert raw.startswith(b"%PDF-1.4") and raw.rstrip().endswith(b"%%EOF")
    assert len(raw) < 200 * 1024
    xref = int(raw.rsplit(b"startxref\n", 1)[1].split()[0])
    assert raw[xref:xref + 4] == b"xref"
    assert PDF_TITLE in pdf_text(raw)


@pytest.mark.parametrize("n", range(1, 6))
def test_round_trip_gives_same_report(n, tmp_path):
    source = DATA_DIR / f"billing_0{n}.csv"
    text = text_to_csv(pdf_text(csv_to_pdf(source.read_text(encoding="utf-8-sig"))))
    back = write_csv(tmp_path, text.splitlines()[1:], name=f"billing_0{n}.csv")
    want, got = analyze(source).report, analyze(back).report
    assert {k: got[k] for k in SAME_FIELDS} == {k: want[k] for k in SAME_FIELDS}


def test_columns_reordered_and_brackets_escaped():
    raw = csv_to_pdf("cost_som,type,datetime,number,duration_sec,mb\n2.00,sms,2026-09-01 01:00:00,(7575),0,0\n")
    text = pdf_text(raw)
    assert "2026-09-01 01:00:00 sms (7575) 0 0 2.00" in text


def test_sample_pdf_in_data_is_billing_03():
    sample = DATA_DIR / "billing_03_sample.pdf"
    assert sample.is_file()
    assert sample.read_bytes() == csv_to_pdf((DATA_DIR / "billing_03.csv").read_text(encoding="utf-8-sig"))


def test_real_pdf_reader_round_trip():
    pytest.importorskip("pdfplumber")
    import base64

    from billcheck.app import analyze_upload
    raw = (DATA_DIR / "billing_03_sample.pdf").read_bytes()
    report = analyze_upload({"filename": "billing_03.pdf", "content_b64": base64.b64encode(raw).decode()})["report"]
    assert report["summary"]["reclaimable_som"] == 65.0 and report["valid_rows"] == 596


def test_make_pdf_cli(tmp_path, capsys):
    import analyze as cli
    target = tmp_path / "out" / "b.pdf"
    assert cli.main(["--make-pdf", str(DATA_DIR / "billing_01.csv"), str(target)]) == 0
    assert target.read_bytes().startswith(b"%PDF")
    assert cli.main(["--make-pdf", str(tmp_path / "nope.csv"), str(target)]) == 2
