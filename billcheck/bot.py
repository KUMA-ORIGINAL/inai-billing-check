"""Telegram-бот «Акчам кайда?»: переслал детализацию — получил сводку и готовую претензию.

Только стандартная библиотека: long polling к https://api.telegram.org через urllib.
Токен — из переменной TELEGRAM_BOT_TOKEN (выдаёт @BotFather), в логи и сообщения он не попадает.
APP_URL (необязательно) — ссылка на веб-приложение, её бот добавляет в конец ответа.

Считает то же ядро, что и CLI: pipeline.analyze → rich_report (сводка) и claim.build_claim (претензия).
Сетевой слой — Transport: в тестах его заменяет поддельный, сеть не нужна.
"""
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from .app import MAX_UPLOAD, TYPE_TITLES, _money
from .claim import build_claim, claim_positions
from .parse import BillingFileError
from .pdf import pdf_to_csv
from .pipeline import Result, analyze
from .rich import rich_report

API = "https://api.telegram.org"
POLL_TIMEOUT = 30
TOP_FINDINGS = 5
SUFFIXES = (".csv", ".txt", ".pdf")

GREETING = (
    "Саламатсызбы! Я «Акчам кайда?» — читаю детализацию мобильной связи и показываю, "
    "куда ушли деньги и что можно вернуть.\n\n"
    "Как получить файл: личный кабинет INAI Mobile → «Расходы» → «Детализация» → скачать CSV "
    "(PDF тоже подойдёт, если на сервере стоит pdfplumber). Пришлите файл сюда документом — "
    "отвечу сводкой и готовой претензией оператору.\n\n"
    "Детализацияны CSV файл катары жөнөтүңүз — акча кайда кеткенин жана эмнени кайтарса болорун "
    "көрсөтөм, операторго даяр арызды да берем.")
HINT = "Пришлите детализацию файлом (CSV из личного кабинета), и я её разберу. /start — подсказка."
TOO_BIG = "Файл больше 5 МБ — это не похоже на детализацию за месяц. Пришлите CSV за один месяц."
WRONG_KIND = "Я читаю детализацию в CSV (или PDF с текстовым слоем). Этот файл — {name} — не подходит."


class TelegramError(RuntimeError):
    """Ответ Telegram с ok=false или сетевая ошибка (без токена в тексте)."""


class Transport:
    """Сетевой слой бота. Тесты подставляют свой с теми же двумя методами."""

    def call(self, method: str, params: dict | None = None, files: dict | None = None) -> object:
        raise NotImplementedError

    def download(self, file_path: str) -> bytes:
        raise NotImplementedError


class UrllibTransport(Transport):
    """Bot API через urllib. files: {поле: (имя файла, bytes)} → multipart/form-data."""

    def __init__(self, token: str, base: str = API):
        self._token, self._base = token, base.rstrip("/")

    def _open(self, request: urllib.request.Request, timeout: float, api: bool = True) -> bytes:
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if api:  # у методов API в теле ошибки — JSON с description
                return exc.read()
            raise TelegramError(f"Telegram ответил HTTP {exc.code}") from None
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise TelegramError(f"нет связи с Telegram ({type(reason).__name__})") from None

    def call(self, method: str, params: dict | None = None, files: dict | None = None) -> object:
        url = f"{self._base}/bot{self._token}/{method}"
        params = params or {}
        if files:
            body, content_type = multipart(params, files)
        else:
            body, content_type = json.dumps(params).encode("utf-8"), "application/json"
        request = urllib.request.Request(url, data=body, headers={"Content-Type": content_type})
        raw = self._open(request, timeout=POLL_TIMEOUT + 15)
        try:
            data = json.loads(raw)
        except ValueError:
            raise TelegramError(f"{method}: Telegram прислал не JSON") from None
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description', 'ошибка Telegram')}")
        return data.get("result")

    def download(self, file_path: str) -> bytes:
        request = urllib.request.Request(f"{self._base}/file/bot{self._token}/{file_path}")
        return self._open(request, timeout=60, api=False)


def multipart(params: dict, files: dict) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    chunks: list[bytes] = []
    for key, value in params.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'
                      .encode("utf-8"))
    for key, (filename, content) in files.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'
                      f"Content-Type: application/octet-stream\r\n\r\n".encode("utf-8") + content + b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


# ---------- разбор файла и ответ
def read_upload(raw: bytes, name: str) -> Result:
    """Байты документа → тот же Result, что у CLI. Ошибки входа — BillingFileError с понятным текстом."""
    if len(raw) > MAX_UPLOAD:
        raise BillingFileError(TOO_BIG)
    if name.lower().endswith(".pdf"):
        text = pdf_to_csv(raw, name)
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise BillingFileError(f"Файл {name} — не текст в UTF-8. Нужна детализация в CSV.") from None
    if not text.strip():
        raise BillingFileError(f"Файл пуст: {name}")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / (Path(name).stem + ".csv")
        path.write_text(text, encoding="utf-8")
        result = analyze(path)
    if not result.charges:
        raise BillingFileError(f"В файле {name} нет ни одной строки детализации.")
    return replace(result, source=Path(name))


def summary_text(report: dict, app_url: str = "") -> str:
    """Короткая сводка по-русски: потрачено, к возврату, главные находки, тариф."""
    s = report["summary"]
    period = report["meta"]["period"]
    lines = [f"Акчам кайда? — {report['meta']['source']}",
             f"Период: {period[0]} — {period[1]}, строк разобрано {report['valid_rows']}, "
             f"пропущено {report['dropped_rows']}.",
             "",
             f"Потрачено: {_money(report['total_som'])} сом",
             f"К возврату: {_money(s['reclaimable_som'])} сом",
             f"Находок: {len(report['anomalies'])}"]
    top = sorted(report["anomalies"], key=lambda a: -a["amount_som"])[:TOP_FINDINGS]
    if top:
        lines += ["", "Главное:"]
        lines += [f"{i}. {a['datetime']} — {TYPE_TITLES.get(a['anomaly_type'], a['anomaly_type'])}, "
                  f"номер {a.get('number') or '—'} — {_money(a['amount_som'])} сом"
                  for i, a in enumerate(top, start=1)]
        if len(report["anomalies"]) > TOP_FINDINGS:
            lines.append(f"…и ещё {len(report['anomalies']) - TOP_FINDINGS}.")
    else:
        lines += ["", "Подозрительных списаний не нашёл."]
    tariff = report.get("tariff")
    if tariff and tariff.get("worth"):
        lines += ["", f"Тариф: тот же месяц на {tariff['best_name']} стоил бы {_money(tariff['best_som'])} сом "
                      f"вместо {_money(tariff['paid_som'])} — экономия {_money(tariff['savings_som'])} сом в месяц."]
    if s["reclaimable_som"] > 0:
        lines += ["", "Претензия оператору — в файле ниже: впишите ФИО и номер и отправьте в поддержку."]
    if app_url:
        lines += ["", f"Подробно, с графиками и семьёй: {app_url}"]
    return "\n".join(lines)


@dataclass
class Reply:
    text: str
    document: tuple[str, bytes] | None = None  # (имя файла, содержимое)


def answer_file(raw: bytes, name: str, app_url: str = "") -> Reply:
    result = read_upload(raw, name)
    report = rich_report(result)
    document = None
    if claim_positions(result):
        document = (f"pretenziya_{Path(name).stem}.txt", build_claim(result).encode("utf-8"))
    return Reply(summary_text(report, app_url), document)


# ---------- бот
class Bot:
    def __init__(self, transport: Transport, app_url: str = "", log=print, sleep=time.sleep):
        self.transport, self.app_url, self.log, self.sleep = transport, app_url.strip(), log, sleep

    def send(self, chat_id: int, reply: Reply) -> None:
        self.transport.call("sendMessage", {"chat_id": chat_id, "text": reply.text})
        if reply.document:
            self.transport.call("sendDocument", {"chat_id": chat_id, "caption": "Претензия оператору"},
                                files={"document": reply.document})

    def reply_to(self, message: dict) -> Reply | None:
        doc = message.get("document")
        if doc:
            return self.reply_to_document(doc)
        text = (message.get("text") or "").strip()
        if text.split("@")[0] in ("/start", "/help") or text.startswith("/start "):
            return Reply(GREETING)
        return Reply(HINT)

    def reply_to_document(self, doc: dict) -> Reply:
        name = Path(str(doc.get("file_name") or "billing.csv")).name
        if not name.lower().endswith(SUFFIXES):
            return Reply(WRONG_KIND.format(name=name))
        if int(doc.get("file_size") or 0) > MAX_UPLOAD:
            return Reply(TOO_BIG)
        try:
            info = self.transport.call("getFile", {"file_id": doc["file_id"]})
            raw = self.transport.download(info["file_path"])
            return answer_file(raw, name, self.app_url)
        except BillingFileError as exc:
            return Reply(f"Не получилось разобрать файл: {exc}\n\n{HINT}")

    def handle(self, update: dict) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message or "chat" not in message:
            return
        chat_id = message["chat"]["id"]
        try:
            reply = self.reply_to(message)
        except TelegramError as exc:
            self.log(f"Ошибка Telegram при разборе: {exc}")
            reply = Reply("Не смог скачать файл из Telegram. Попробуйте прислать его ещё раз.")
        except Exception as exc:  # бот не должен падать из-за одного файла
            self.log(f"Ошибка разбора: {type(exc).__name__}: {exc}")
            reply = Reply("Что-то пошло не так при разборе. Проверьте, что это детализация в CSV.")
        if reply:
            self.send(chat_id, reply)

    def poll_once(self, offset: int | None) -> int | None:
        params = {"timeout": POLL_TIMEOUT, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        for update in self.transport.call("getUpdates", params) or []:
            offset = update["update_id"] + 1
            try:
                self.handle(update)
            except TelegramError as exc:  # не смогли ответить — идём дальше, обновление не повторяем
                self.log(f"Не удалось ответить: {exc}")
        return offset

    def run(self, max_polls: int | None = None) -> None:
        offset, polls, delay = None, 0, 1
        while max_polls is None or polls < max_polls:
            polls += 1
            try:
                offset = self.poll_once(offset)
                delay = 1
            except TelegramError as exc:
                self.log(f"{exc}; повтор через {delay} с")
                self.sleep(delay)
                delay = min(delay * 2, 60)


def main(env: dict | None = None, transport: Transport | None = None, max_polls: int | None = None) -> int:
    """Запуск: python analyze.py --bot. 0 — остановлен Ctrl+C, 2 — нет токена или он не подошёл."""
    env = os.environ if env is None else env
    token = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token and transport is None:
        print("Ошибка: не задан TELEGRAM_BOT_TOKEN. Создайте бота у @BotFather (/newbot) и задайте токен:\n"
              '  PowerShell: $env:TELEGRAM_BOT_TOKEN = "123456:ABC..."\n'
              '  Linux/macOS: export TELEGRAM_BOT_TOKEN="123456:ABC..."', file=sys.stderr)
        return 2
    transport = transport or UrllibTransport(token)
    try:
        me = transport.call("getMe")
    except TelegramError as exc:
        print(f"Ошибка: Telegram не принял токен или недоступен ({exc}).", file=sys.stderr)
        return 2
    print(f"Бот @{(me or {}).get('username', '?')} запущен, жду файлы (остановить — Ctrl+C).", flush=True)
    try:
        Bot(transport, env.get("APP_URL", ""), log=lambda m: print(m, file=sys.stderr, flush=True)).run(max_polls)
    except KeyboardInterrupt:
        pass
    return 0
