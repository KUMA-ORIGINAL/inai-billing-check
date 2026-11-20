"""Общие помощники тестов: запись маленьких CSV и списаний."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from billcheck.parse import Charge

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HEADER = "datetime,type,number,duration_sec,mb,cost_som"


def write_csv(tmp_path: Path, rows: list[str], newline: str = "\n", bom: bool = False,
              name: str = "billing.csv", header: bool = True) -> Path:
    lines = ([HEADER] if header else []) + rows
    data = newline.join(lines) + newline
    path = tmp_path / name
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data.encode("utf-8"))
    return path


def ch(dt: str, type_: str, number: str, dur, mb, cost, line: int = 0) -> Charge:
    return Charge(line=line, dt=datetime.fromisoformat(dt), type=type_, number=number,
                  duration_sec=Decimal(str(dur)), mb=Decimal(str(mb)), cost=Decimal(str(cost)))
