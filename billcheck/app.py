"""Приложение «Акчам кайда?»: данные для экрана, разбор загрузки, печатный HTML и Markdown-отчёт.

Экран (templates/app.html) работает в двух режимах: с сервером (`run.bat --serve`, API ниже) и без
него — на снимке семьи, который вшивается в out/index.html. Все числа считает одно ядро analyze().
"""
import base64
import binascii
import html
import json
import tempfile
from pathlib import Path

from .anomalies import DEFAULT_RULES, Rules
from .family import load_family
from .html import LESS_THAN_ESCAPE, TEMPLATES
from .parse import BillingFileError
from .pdf import pdf_to_csv
from .pipeline import analyze
from .rich import checks, radar, rich_report

SNAPSHOT_PLACEHOLDER = "/*__SNAPSHOT__*/null"
MAX_UPLOAD = 5 * 1024 * 1024
TYPE_TITLES = {"night_charge": "Ночное платное списание", "new_subscription": "Новая подписка",
               "duplicate_charge": "Двойное списание", "international_rate": "Дорогой звонок за границу",
               "day_spike": "Всплеск трат за день"}
CATEGORY_NAMES = {"call": "Звонки", "sms": "SMS", "data": "Интернет", "subscription": "Подписки", "content": "Контент"}


def _expected(path: Path) -> dict | None:
    target = path.with_name(f"{path.stem}_expected.json")
    try:
        return json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def member_payload(path: Path, info: dict, rules: Rules = DEFAULT_RULES, with_content: bool = True) -> dict:
    result = analyze(path, rules)
    report = rich_report(result)
    expected = _expected(path)
    member = {"id": path.stem, "name": info.get("name") or path.stem, "role": info.get("role", ""),
              "msisdn": info.get("msisdn", ""), "filename": path.name, "report": report,
              "checks": checks(report, expected)}
    if with_content:  # для «добавить дубль вживую» и пересчёта с другими порогами
        member["content"] = path.read_text(encoding="utf-8-sig")
        if expected is not None:
            member["expected"] = expected
    return member


def family_snapshot(data_dir: Path, rules: Rules = DEFAULT_RULES, with_content: bool = True,
                    files: list[Path] | None = None) -> dict:
    """Семья из data/family.json (или просто все billing_*.csv) + радар коротких номеров."""
    data_dir = Path(data_dir)
    family = load_family(data_dir)
    known = {m["file"]: m for m in family["members"]}
    if files is None:
        files = [data_dir / m["file"] for m in family["members"] if (data_dir / m["file"]).is_file()]
        files += [p for p in sorted(data_dir.glob("billing_*.csv")) if p.name not in known]
    members = [member_payload(p, known.get(p.name, {}), rules, with_content) for p in files]
    return {"family": family["family"] or "Моя семья", "members": members,
            "radar": radar([{"name": m["name"], "report": m["report"]} for m in members], rules)}


def render_app(snapshot: dict | None) -> str:
    """Страница приложения; снимок вшит JSON-ом (каждый «<» экранирован), без сервера всё работает на нём."""
    page = (TEMPLATES / "app.html").read_text(encoding="utf-8")
    payload = json.dumps(snapshot, ensure_ascii=False).replace("<", LESS_THAN_ESCAPE) if snapshot else "null"
    return page.replace(SNAPSHOT_PLACEHOLDER, payload)


def analyze_upload(body: dict) -> dict:
    """POST /api/analyze: {filename, content | content_b64, settings?, expected?} → {report, checks}."""
    if not isinstance(body, dict):
        raise BillingFileError("Ожидался JSON-объект с полями filename и content.")
    name = Path(str(body.get("filename") or "billing.csv")).name or "billing.csv"
    rules = Rules.from_dict(body.get("settings"))
    if body.get("content_b64"):
        try:
            raw = base64.b64decode(str(body["content_b64"]), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise BillingFileError("Файл повреждён при загрузке (base64).") from exc
        if len(raw) > MAX_UPLOAD:
            raise BillingFileError("Файл больше 5 МБ — это не похоже на детализацию за месяц.")
        try:
            text = pdf_to_csv(raw, name) if name.lower().endswith(".pdf") else raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise BillingFileError(f"Файл {name} — не текст в UTF-8. Нужна детализация в CSV.") from exc
    else:
        text = body.get("content")
        if not isinstance(text, str) or not text.strip():
            raise BillingFileError(f"Файл пуст: {name}")
        if len(text.encode("utf-8")) > MAX_UPLOAD:
            raise BillingFileError("Файл больше 5 МБ — это не похоже на детализацию за месяц.")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / (Path(name).stem + ".csv")
        path.write_text(text, encoding="utf-8")
        result = analyze(path, rules)
        result = type(result)(Path(name), result.charges, result.dropped, result.anomalies, result.report, rules)
        report = rich_report(result)
    expected = body.get("expected") if isinstance(body.get("expected"), (dict, list)) else None
    return {"report": report, "checks": checks(report, expected)}


def _money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def render_markdown(report: dict, title: str = "") -> str:
    """Отчёт в Markdown (ТЗ: «консоль, HTML или Markdown»)."""
    s = report.get("summary", {})
    period = report.get("meta", {}).get("period", ["", ""])
    lines = [f"# Акчам кайда? — {title or report.get('meta', {}).get('source', 'детализация')}", "",
             f"Период: {period[0]} — {period[1]}. Строк: {report['valid_rows']} разобрано, "
             f"{report['dropped_rows']} пропущено.", "",
             f"- **Потрачено:** {_money(report['total_som'])} сом",
             f"- **К возврату:** {_money(s.get('reclaimable_som', 0))} сом",
             f"- **Находок:** {len(report['anomalies'])}", "",
             "## Находки", "", "| Когда | Что | Номер | Сумма, сом | Пояснение |", "|---|---|---|---:|---|"]
    for a in report["anomalies"]:
        text = str(a.get("explanation", a.get("reason", ""))).replace("|", "/")
        lines.append(f"| {a['datetime']} | {TYPE_TITLES.get(a['anomaly_type'], a['anomaly_type'])} | "
                     f"{a.get('number') or '—'} | {_money(a['amount_som'])} | {text} |")
    lines += ["", "## Куда ушли деньги", "", "| Категория | Сом |", "|---|---:|"]
    lines += [f"| {CATEGORY_NAMES.get(k, k)} | {_money(v)} |" for k, v in report["by_category"].items()]
    lines += ["", "## Топ-5 номеров", "", "| Номер | Сом |", "|---|---:|"]
    lines += [f"| {t['number']} | {_money(t['cost_som'])} |" for t in report["top5_numbers"]]
    lines += ["", "## Траты по дням", "", "| День | Сом |", "|---|---:|"]
    lines += [f"| {day} | {_money(v)} |" for day, v in report["by_day"].items()]
    tariff = report.get("tariff")
    if tariff and tariff.get("worth"):
        lines += ["", "## Можно платить меньше", "",
                  f"Тот же месяц на тарифе {tariff['best_name']}: {_money(tariff['best_som'])} сом вместо "
                  f"{_money(tariff['paid_som'])} — экономия {_money(tariff['savings_som'])} сом в месяц "
                  f"(оценка по одному месяцу, тарифы ТЗ 2)."]
    if report.get("dropped_log"):
        lines += ["", "## Пропущенные строки", "", "| Строка | Причина |", "|---:|---|"]
        lines += [f"| {d['line']} | {d['reason']} |" for d in report["dropped_log"]]
    return "\n".join(lines) + "\n"


def render_print(report: dict, complaint: str = "") -> str:
    """POST /api/render: самодостаточный HTML-отчёт для печати или отправки (без скриптов)."""
    esc = html.escape
    s = report.get("summary", {})
    period = report.get("meta", {}).get("period", ["", ""])
    rows = "".join(f"<tr><td>{esc(a['datetime'])}</td><td>{esc(TYPE_TITLES.get(a['anomaly_type'], ''))}</td>"
                   f"<td>{esc(a.get('number') or '—')}</td><td class=n>{_money(a['amount_som'])}</td>"
                   f"<td>{esc(str(a.get('explanation', '')))}</td></tr>" for a in report.get("anomalies", []))
    cats = "".join(f"<tr><td>{CATEGORY_NAMES.get(k, k)}</td><td class=n>{_money(v)}</td></tr>"
                   for k, v in report.get("by_category", {}).items())
    top = "".join(f"<tr><td>{esc(t['number'])}</td><td class=n>{_money(t['cost_som'])}</td></tr>"
                  for t in report.get("top5_numbers", []))
    letter = f"<h2>Претензия оператору</h2><pre>{esc(complaint)}</pre>" if complaint.strip() else ""
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Акчам кайда? — отчёт</title>
<style>body{{font:15px/1.55 system-ui,sans-serif;max-width:860px;margin:32px auto;padding:0 16px;color:#17191C}}
h1{{font-size:26px;margin:0 0 4px}}h2{{margin-top:28px;font-size:18px}}table{{width:100%;border-collapse:collapse}}
td,th{{text-align:left;padding:6px 8px;border-bottom:1px solid #ddd;vertical-align:top}}.n{{text-align:right;white-space:nowrap}}
.kpi{{display:flex;gap:28px;margin:14px 0}}.kpi b{{display:block;font-size:24px}}pre{{white-space:pre-wrap;background:#F6F2E8;padding:16px;border-radius:8px}}
</style></head><body>
<h1>Акчам кайда? · {esc(report.get('meta', {}).get('source', ''))}</h1>
<p>Период {esc(period[0])} — {esc(period[1])}. Разобрано {report.get('valid_rows', 0)} строк, пропущено {report.get('dropped_rows', 0)}.</p>
<div class="kpi"><div><b>{_money(report.get('total_som', 0))}</b>сом потрачено</div>
<div><b style="color:#C2410C">{_money(s.get('reclaimable_som', 0))}</b>сом к возврату</div>
<div><b>{len(report.get('anomalies', []))}</b>находок</div></div>
<h2>Находки</h2><table><tr><th>Когда</th><th>Что</th><th>Номер</th><th class=n>Сом</th><th>Пояснение</th></tr>{rows}</table>
<h2>По категориям</h2><table>{cats}</table><h2>Топ-5 номеров</h2><table>{top}</table>{letter}
<p style="color:#666;font-size:13px;margin-top:28px">INAI Mobile — учебный оператор хакатона. Решение о возврате принимает оператор.</p>
</body></html>"""
