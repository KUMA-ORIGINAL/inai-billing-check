"""CLI: python analyze.py [billing.csv …] [--out out]   ·   из Python: analyze.analyze("billing.csv")

Один файл → out/report.json, out/anomalies.json, out/dropped_rows.csv, out/report.html, out/report.md.
Несколько файлов (или ни одного — тогда все data/billing_*.csv) → out/<имя>/…, out/index.html (приложение
«Акчам кайда?», работает без сервера) и out/family.html (классическая семейная страница).
--llm добавляет письмо абоненту от Claude (нужны пакет anthropic и доступ к API; иначе — шаблоны).
--validate [папка] сверяет все billing_XX.csv с эталонами, --bot запускает Telegram-бота,
--make-pdf CSV PDF печатает детализацию в демо-PDF.
Коды возврата: 0 — успех, 1 — --validate нашёл незачёт, 2 — проблема с входным файлом или нет токена бота
(run.bat / run.sh: 3 — не найден Python).
"""
import argparse
import os
import sys
import webbrowser
from pathlib import Path

if sys.version_info < (3, 10):  # до импорта billcheck: там синтаксис 3.10
    sys.exit("Нужен Python 3.10 или новее, а запущен " + sys.version.split()[0] + ".")

from billcheck.app import family_snapshot, render_app, render_markdown
from billcheck.explain import possible_overpay
from billcheck.family import load_profiles, profile_name
from billcheck.html import render_family
from billcheck.llm import llm_summary
from billcheck.parse import BillingFileError
from billcheck.pipeline import Result, write_outputs
from billcheck.rich import rich_report
from billcheck.pipeline import analyze as analyze_billing

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
EXIT_OK, EXIT_INPUT = 0, 2
FAMILY_BACK_LINK = {"href": "../family.html", "label": "← Вся семья"}


def analyze(file: str | Path, out: str | Path = "out") -> dict:
    """Интерфейс из ТЗ: analyze(file) → отчёт + anomalies.json (а также report.json, dropped_rows.csv, report.html).

    Возвращает отчёт в формате эталона организаторов. Ошибка входного файла — BillingFileError.
    """
    result = analyze_billing(file)
    name = profile_name(load_profiles(result.source.parent), result.source)
    write_outputs(result, Path(out), name)
    write_markdown(result, Path(out), name)
    return result.report


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


def write_markdown(result: Result, out_dir: Path, title: str) -> Path:
    path = Path(out_dir) / "report.md"
    path.write_text(render_markdown(rich_report(result), title), encoding="utf-8")
    return path


def write_family_index(results: list[Result], out_dir: Path) -> Path:
    """index.html — приложение «Акчам кайда?» со вшитым снимком семьи; family.html — классическая страница."""
    data_dir = results[0].source.parent
    links = [f"{r.source.stem}/report.html" for r in results]
    (out_dir / "family.html").write_text(render_family(results, load_profiles(data_dir), links, data_dir),
                                         encoding="utf-8")
    path = out_dir / "index.html"
    snapshot = family_snapshot(data_dir, with_content=False, files=[r.source for r in results])
    path.write_text(render_app(snapshot), encoding="utf-8")
    return path


def serve(port: int, open_browser: bool, use_llm: bool = False, host: str = "127.0.0.1") -> int:
    from billcheck.server import make_server

    try:
        server = make_server(DATA_DIR, port, use_llm=use_llm, host=host)
    except OSError as exc:
        print(f"Ошибка: порт {port} занят ({exc}). Запустите с --port 8001.", file=sys.stderr)
        return EXIT_INPUT
    shown = "127.0.0.1" if host in ("0.0.0.0", "") else host
    url = f"http://{shown}:{server.server_address[1]}"
    print(f"Веб-демо: {url}  (остановить — Ctrl+C)", flush=True)
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
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT") or 8000),
                        help="порт веб-демо (по умолчанию 8000 или переменная PORT, как на Render)")
    parser.add_argument("--host", default=os.environ.get("HOST") or "127.0.0.1",
                        help="адрес веб-демо: 127.0.0.1 — только этот компьютер (по умолчанию), 0.0.0.0 — хостинг")
    parser.add_argument("--llm", action="store_true", help="письмо абоненту от Claude по посчитанным числам (бонус)")
    parser.add_argument("--validate", nargs="?", const=str(DATA_DIR), metavar="ПАПКА",
                        help="сверить все billing_XX.csv папки с эталонами (по умолчанию data)")
    parser.add_argument("--bot", action="store_true", help="Telegram-бот (токен в TELEGRAM_BOT_TOKEN)")
    parser.add_argument("--make-pdf", nargs=2, metavar=("CSV", "PDF"), help="напечатать детализацию в демо-PDF")
    return parser


def make_pdf(source: str, target: str) -> int:
    from billcheck.pdf import csv_to_pdf

    try:
        data = csv_to_pdf(Path(source).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, BillingFileError) as exc:
        print(f"Ошибка: не удалось прочитать {source} ({exc}).", file=sys.stderr)
        return EXIT_INPUT
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"PDF: {path.resolve()} ({len(data) // 1024 + 1} КБ)")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    args = build_parser().parse_args(argv)
    if args.serve:
        return serve(args.port, args.open, args.llm, args.host)
    if args.validate:
        from billcheck.validate import main as validate

        return validate(args.validate)
    if args.bot:
        from billcheck.bot import main as run_bot

        return run_bot()
    if args.make_pdf:
        return make_pdf(*args.make_pdf)
    files = resolve_inputs(args.files)
    if not files:
        print("Ошибка: не найдено ни одной детализации (billing_*.csv).", file=sys.stderr)
        return EXIT_INPUT
    try:
        results = [analyze_billing(path) for path in files]
    except BillingFileError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return EXIT_INPUT
    out = Path(args.out)
    if len(results) == 1:
        result = results[0]
        name = profile_name(load_profiles(result.source.parent), result.source)
        write_outputs(result, out, name, llm_summary(result) if args.llm else None)
        write_markdown(result, out, name)
        print_summary(result, out)
        page = out / "report.html"
    else:
        for result in results:
            name = profile_name(load_profiles(result.source.parent), result.source)
            write_outputs(result, out / result.source.stem, name, llm_summary(result) if args.llm else None,
                          back_link=FAMILY_BACK_LINK)
            write_markdown(result, out / result.source.stem, name)
            print_summary(result, out / result.source.stem)
        page = write_family_index(results, out)
        print(f"Сводка: {page}")
    print(f"Отчёт: {page.resolve()}")
    if args.open:
        webbrowser.open(page.resolve().as_uri())
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
