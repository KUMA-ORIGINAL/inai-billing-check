"""CLI: python analyze.py [billing.csv …] [--out out]

Один файл → out/report.json, out/anomalies.json, out/dropped_rows.csv.
Несколько файлов (или ни одного — тогда все data/billing_*.csv) → out/<имя>/… и out/index.html.
--llm добавляет письмо абоненту от Claude (нужны пакет anthropic и доступ к API; иначе — шаблоны).
Коды возврата: 0 — успех, 2 — проблема с входным файлом.
"""
import argparse
import sys
import webbrowser
from pathlib import Path

from billcheck.explain import possible_overpay
from billcheck.family import load_profiles, profile_name
from billcheck.html import render_family
from billcheck.llm import llm_summary
from billcheck.parse import BillingFileError
from billcheck.pipeline import Result, analyze, write_outputs

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
EXIT_OK, EXIT_INPUT = 0, 2
FAMILY_BACK_LINK = {"href": "../index.html", "label": "← Вся семья"}


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


def write_family_index(results: list[Result], out_dir: Path) -> Path:
    """index.html — семейный экран со ссылками на отчёт каждого профиля."""
    data_dir = results[0].source.parent
    links = [f"{r.source.stem}/report.html" for r in results]
    path = out_dir / "index.html"
    path.write_text(render_family(results, load_profiles(data_dir), links, data_dir), encoding="utf-8")
    return path


def serve(port: int, open_browser: bool, use_llm: bool = False) -> int:
    from billcheck.server import make_server

    try:
        server = make_server(DATA_DIR, port, use_llm=use_llm)
    except OSError as exc:
        print(f"Ошибка: порт {port} занят ({exc}). Запустите с --port 8001.", file=sys.stderr)
        return EXIT_INPUT
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"Веб-демо: {url}  (остановить — Ctrl+C)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Расшифровщик детализации: отчёт и аномалии (ТЗ 4).")
    parser.add_argument("files", nargs="*",
                        help="CSV-детализации или папки с ними (по умолчанию data/billing_*.csv)")
    parser.add_argument("--out", default="out", help="папка для результатов (по умолчанию out)")
    parser.add_argument("--open", action="store_true", help="открыть отчёт в браузере")
    parser.add_argument("--serve", action="store_true", help="веб-демо: загрузка файла и профили семьи")
    parser.add_argument("--port", type=int, default=8000, help="порт веб-демо (по умолчанию 8000)")
    parser.add_argument("--llm", action="store_true", help="письмо абоненту от Claude по посчитанным числам (бонус)")
    return parser


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    args = build_parser().parse_args(argv)
    if args.serve:
        return serve(args.port, args.open, args.llm)
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
        result = results[0]
        write_outputs(result, out, profile_name(load_profiles(result.source.parent), result.source),
                      llm_summary(result) if args.llm else None)
        print_summary(result, out)
        page = out / "report.html"
    else:
        for result in results:
            name = profile_name(load_profiles(result.source.parent), result.source)
            write_outputs(result, out / result.source.stem, name, llm_summary(result) if args.llm else None,
                          back_link=FAMILY_BACK_LINK)
            print_summary(result, out / result.source.stem)
        page = write_family_index(results, out)
        print(f"Сводка: {page}")
    print(f"Отчёт: {page.resolve()}")
    if args.open:
        webbrowser.open(page.resolve().as_uri())
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
