"""Локальное веб-демо «Акчам кайда?»: приложение на «/», его API и классические страницы на «/classic».

Слушает только 127.0.0.1. Загруженный файл разбирается тем же analyze(), что и в CLI.

API приложения (JSON):
  GET  /api/health   — живой ли сервер и настроен ли ИИ
  GET  /api/demo     — семья из data/family.json: расширенные отчёты, сверка с эталоном, радар
  POST /api/analyze  — {filename, content | content_b64, settings?, expected?} → {report, checks}
  POST /api/radar    — {members: [{name, report}], settings?} → {radar}
  POST /api/explain  — {anomaly, lang} → {text, source: llm | template}
  POST /api/render   — {report, complaint?} → HTML-отчёт для печати
"""
import json
import re
import tempfile
import threading
import uuid
from collections import OrderedDict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .anomalies import Rules
from .app import analyze_upload, family_snapshot, render_app, render_print
from .explain import load_faq
from .family import load_profiles, profile_name
from .html import embed, render_family, render_report
from .llm import explain_anomaly, llm_summary, pick_provider, template_explanation
from .parse import BillingFileError
from .pipeline import analyze
from .rich import radar

MAX_UPLOAD = 5 * 1024 * 1024
MAX_JSON = 8 * 1024 * 1024  # 5 МБ файла в base64 и запас на отчёты семьи в /api/radar
VERSION = "2.0"
SAFE_NAME = re.compile(r"[^\w.\-]+", re.UNICODE)
FAMILY_BACK = {"href": "/family", "label": "← Вся семья"}
UPLOAD_BACK = {"href": "/classic", "label": "← Другой файл"}
HOW_TO_FAQ_ID = 15  # FAQ оператора: «Как получить детализацию расходов?»


def billing_files(data_dir: Path) -> dict[str, Path]:
    """Профили, которые можно открыть по ссылке: только billing_*.csv из папки данных."""
    return {p.name: p for p in sorted(Path(data_dir).glob("billing_*.csv"))}


def upload_name(header: str | None) -> str:
    """Безопасное имя загруженного файла: без пути и спецсимволов, расширение как у пользователя."""
    name = Path(unquote(header or "")).name
    return SAFE_NAME.sub("_", name).strip("._") or "billing.csv"


class ReportStore:
    """Последние проверенные отчёты в памяти сервера: у каждого свой адрес /report/<id>."""

    def __init__(self, limit: int = 20):
        self.limit = limit
        self.pages: OrderedDict[str, str] = OrderedDict()
        self.lock = threading.Lock()

    def add(self, page: str) -> str:
        key = uuid.uuid4().hex
        with self.lock:
            self.pages[key] = page
            while len(self.pages) > self.limit:
                self.pages.popitem(last=False)
        return key

    def get(self, key: str) -> str | None:
        with self.lock:
            return self.pages.get(key)


def make_server(data_dir: Path, port: int = 8000, use_llm: bool = False,
                host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """По умолчанию слушаем только этот компьютер; на хостинге (Render) — host="0.0.0.0"."""
    data_dir = Path(data_dir)
    reports = ReportStore()
    cache: dict[str, str] = {}
    cache_lock = threading.Lock()

    def app_page() -> str:
        """Главная: приложение со вшитым снимком семьи (на случай, если API недоступен)."""
        with cache_lock:
            if "app" not in cache:
                cache["app"] = render_app(family_snapshot(data_dir, with_content=False))
            return cache["app"]

    def letter(result) -> str | None:
        return llm_summary(result) if use_llm else None

    class Handler(BaseHTTPRequestHandler):
        server_version = "GdeMoiDengi/1.0"

        def log_message(self, format: str, *args) -> None:  # тихий сервер: в консоли только адрес
            return

        def _send(self, status: int, body: str, content_type: str = "text/html; charset=utf-8",
                  headers: dict[str, str] | None = None) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status: int, message: str) -> None:
            self._send(status, json.dumps({"error": message}, ensure_ascii=False), "application/json; charset=utf-8")

        def _drain(self, length: int) -> None:
            """Дочитать слишком большое тело (до 64 МБ), чтобы клиент получил ответ, а не обрыв соединения."""
            if length > 64 * 1024 * 1024:
                self.close_connection = True
                return
            while length > 0:
                chunk = self.rfile.read(min(length, 1024 * 1024))
                if not chunk:
                    break
                length -= len(chunk)

        def _json(self, data, status: int = HTTPStatus.OK) -> None:
            self._send(status, json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8")

        def _read_json(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_JSON:
                self._drain(length)
                self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Слишком большой запрос: файл больше 5 МБ.")
                return None
            try:
                return json.loads(self.rfile.read(length).decode("utf-8") or "null")
            except (UnicodeDecodeError, ValueError):
                self._error(HTTPStatus.BAD_REQUEST, "Тело запроса — не JSON.")
                return None

        def do_GET(self) -> None:  # noqa: N802 — имя задаёт http.server
            path = unquote(urlparse(self.path).path)
            files = billing_files(data_dir)
            profiles = load_profiles(data_dir)
            if path in ("/", "/index.html"):
                self._send(HTTPStatus.OK, app_page())
            elif path == "/api/health":
                provider = pick_provider() if use_llm else None
                self._json({"ok": True, "version": VERSION, "llm": provider[0] if provider else None})
            elif path == "/api/demo":
                self._json(family_snapshot(data_dir))
            elif path == "/classic":
                payload = {"profiles": [{"file": name, "name": profile_name(profiles, p)} for name, p in files.items()],
                           "limit_mb": MAX_UPLOAD // (1024 * 1024),
                           "how_to": load_faq().get(HOW_TO_FAQ_ID, {}).get("answer_ru", "")}
                self._send(HTTPStatus.OK, embed("upload.html", payload))
            elif path == "/family" and files:
                results = [analyze(p) for p in files.values()]
                links = [f"/profile/{name}" for name in files]
                self._send(HTTPStatus.OK, render_family(results, profiles, links, data_dir))
            elif path.startswith("/report/") and reports.get(path[len("/report/"):]):
                self._send(HTTPStatus.OK, reports.get(path[len("/report/"):]))
            elif path.startswith("/profile/") and path[len("/profile/"):] in files:
                source = files[path[len("/profile/"):]]
                result = analyze(source)
                page = render_report(result, profile_name(profiles, source), letter(result), back_link=FAMILY_BACK)
                self._send(HTTPStatus.OK, page)
            else:
                self._error(HTTPStatus.NOT_FOUND, "Такой страницы нет.")

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            is_json = "json" in (self.headers.get("Content-Type") or "")
            if path in ("/api/radar", "/api/explain", "/api/render") or (path == "/api/analyze" and is_json):
                body = self._read_json()
                if body is not None:
                    self._api(path, body)
                return
            if path != "/api/analyze":
                self._error(HTTPStatus.NOT_FOUND, "Такой страницы нет.")
                return
            self._classic_upload()

        def _api(self, path: str, body) -> None:
            body = body if isinstance(body, dict) else {}
            if path == "/api/analyze":
                try:
                    self._json(analyze_upload(body))
                except BillingFileError as exc:
                    self._error(HTTPStatus.BAD_REQUEST, str(exc))
            elif path == "/api/radar":
                members = [m for m in body.get("members") or [] if isinstance(m, dict) and isinstance(m.get("report"), dict)]
                members = [{"name": str(m.get("name") or "?"), "report": m["report"]} for m in members]
                try:
                    self._json({"radar": radar(members, Rules.from_dict(body.get("settings")))})
                except (KeyError, TypeError, ValueError, IndexError):
                    self._error(HTTPStatus.BAD_REQUEST, "Отчёты в запросе не в формате /api/analyze.")
            elif path == "/api/explain":
                anomaly = body.get("anomaly")
                if not isinstance(anomaly, dict):
                    self._error(HTTPStatus.BAD_REQUEST, "Нужно поле anomaly из отчёта.")
                    return
                lang = "ky" if body.get("lang") == "ky" else "ru"
                self._json(explain_anomaly(anomaly, lang) if use_llm else template_explanation(anomaly, lang))
            elif path == "/api/render":
                report = body.get("report")
                if not isinstance(report, dict):
                    self._error(HTTPStatus.BAD_REQUEST, "Нужно поле report из /api/analyze.")
                    return
                try:
                    self._send(HTTPStatus.OK, render_print(report, str(body.get("complaint") or "")))
                except (KeyError, TypeError, ValueError):
                    self._error(HTTPStatus.BAD_REQUEST, "Отчёт в запросе не в формате /api/analyze.")

        def _classic_upload(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_UPLOAD:
                self._drain(length)
                self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Файл больше 5 МБ — это не похоже на детализацию за месяц.")
                return
            body = self.rfile.read(length)
            name = upload_name(self.headers.get("X-Filename"))
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / name
                path.write_bytes(body)
                try:
                    result = analyze(path)
                except BillingFileError as exc:
                    self._error(HTTPStatus.BAD_REQUEST, str(exc))
                    return
                page = render_report(result, profile_name(load_profiles(data_dir), path), letter(result),
                                     back_link=UPLOAD_BACK, expected_dir=data_dir)
            self._send(HTTPStatus.OK, page, headers={"X-Report-Url": f"/report/{reports.add(page)}"})

    return ThreadingHTTPServer((host, port), Handler)
