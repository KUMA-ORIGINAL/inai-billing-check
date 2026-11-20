"""Локальное веб-демо: загрузка детализации перетаскиванием и готовые профили семьи.

Слушает только 127.0.0.1. Загруженный файл разбирается тем же analyze(), что и в CLI.
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

from .explain import load_faq
from .family import load_profiles, profile_name
from .html import embed, render_family, render_report
from .llm import llm_summary
from .parse import BillingFileError
from .pipeline import analyze

MAX_UPLOAD = 5 * 1024 * 1024
SAFE_NAME = re.compile(r"[^\w.\-]+", re.UNICODE)
FAMILY_BACK = {"href": "/family", "label": "← Вся семья"}
UPLOAD_BACK = {"href": "/", "label": "← Другой файл"}
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


def make_server(data_dir: Path, port: int = 8000, use_llm: bool = False) -> ThreadingHTTPServer:
    data_dir = Path(data_dir)
    reports = ReportStore()

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

        def do_GET(self) -> None:  # noqa: N802 — имя задаёт http.server
            path = unquote(urlparse(self.path).path)
            files = billing_files(data_dir)
            profiles = load_profiles(data_dir)
            if path == "/":
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
            if urlparse(self.path).path != "/api/analyze":
                self._error(HTTPStatus.NOT_FOUND, "Такой страницы нет.")
                return
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

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
