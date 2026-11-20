"""CLI: python analyze.py [billing.csv …] [--out out]

Один файл → out/report.json, out/anomalies.json, out/dropped_rows.csv.
Несколько файлов (или ни одного — тогда все data/billing_*.csv) → out/<имя>/… и out/index.html.
Коды возврата: 0 — успех, 2 — проблема с входным файлом, 3 — не хватает зависимостей.
"""
import argparse
import html
import sys
from pathlib import Path

from billcheck.explain import possible_overpay
from billcheck.parse import BillingFileError
from billcheck.pipeline import Result, analyze, write_outputs

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
EXIT_OK, EXIT_INPUT, EXIT_DEPS = 0, 2, 3


def utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def resolve_inputs(args: list[str]) -> list[Path]:
    if not args:
        return sorted(DATA_DIR.glob("billing_*.csv"))
    files: list[Path] = []
    for arg in args:
        path = Path(arg)
        if path.is_dir():
            files += sorted(path.glob("billing_*.csv")) or sorted(path.glob("*.csv"))
        else:
            files.append(path)
    return files


def print_summary(result: Result, out_dir: Path) -> None:
    report = result.report
    print(f"{result.source.name}: списаний {report['valid_rows']}, отброшено строк {report['dropped_rows']}, "
          f"потрачено {report['total_som']:.2f} сом")
    print(f"  аномалий: {len(result.anomalies)}, возможно лишнее: {possible_overpay(result.anomalies):.2f} сом")
    for a in result.anomalies:
        row = a.as_dict()
        print(f"  {row['datetime']}  {a.anomaly_type:<18} {row['amount_som']:>8.2f} сом  {a.reason}")
    print(f"  → {out_dir / 'anomalies.json'}")


def write_index(results: list[Result], out_dir: Path) -> Path:
    links = "\n".join(f'<li><a href="{html.escape(r.source.stem)}/report.json">{html.escape(r.source.name)}</a>'
                      f" — {len(r.anomalies)} аномалий</li>" for r in results)
    path = out_dir / "index.html"
    path.write_text(f'<!doctype html><meta charset="utf-8"><title>Детализации</title><ul>{links}</ul>\n',
                    encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Расшифровщик детализации: отчёт и аномалии (ТЗ 4).")
    parser.add_argument("files", nargs="*",
                        help="CSV-детализации или папки с ними (по умолчанию data/billing_*.csv)")
    parser.add_argument("--out", default="out", help="папка для результатов (по умолчанию out)")
    return parser


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    args = build_parser().parse_args(argv)
    files = resolve_inputs(args.files)
    if not files:
        print("Ошибка: не найдено ни одной детализации (billing_*.csv).", file=sys.stderr)
        return EXIT_INPUT
    try:
        results = [analyze(path) for path in files]
    except BillingFileError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return EXIT_INPUT
    out = Path(args.out)
    if len(results) == 1:
        write_outputs(results[0], out)
        print_summary(results[0], out)
    else:
        for result in results:
            write_outputs(result, out / result.source.stem)
            print_summary(result, out / result.source.stem)
        print(f"Сводка: {write_index(results, out)}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
