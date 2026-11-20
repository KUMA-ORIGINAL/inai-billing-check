"""Telegram-бот на поддельном транспорте: сеть не нужна."""
import pytest
from helpers import DATA_DIR

from billcheck import bot
from billcheck.bot import Bot, TelegramError, Transport, multipart


class FakeTransport(Transport):
    def __init__(self, files: dict[str, bytes] | None = None, updates: list | None = None):
        self.files = files or {}
        self.updates = list(updates or [])
        self.calls: list[tuple[str, dict, dict | None]] = []

    def call(self, method, params=None, files=None):
        self.calls.append((method, params or {}, files))
        if method == "getMe":
            return {"username": "akcham_test_bot"}
        if method == "getFile":
            return {"file_path": f"documents/{params['file_id']}"}
        if method == "getUpdates":
            return self.updates.pop(0) if self.updates else []
        return {"message_id": 1}

    def download(self, file_path):
        return self.files[file_path.split("/")[-1]]

    def sent(self, method):
        return [(p, f) for m, p, f in self.calls if m == method]


def _doc_update(update_id, name, file_id="f1", size=None):
    doc = {"file_id": file_id, "file_name": name}
    if size is not None:
        doc["file_size"] = size
    return {"update_id": update_id, "message": {"chat": {"id": 42}, "document": doc}}


def _text_update(update_id, text):
    return {"update_id": update_id, "message": {"chat": {"id": 42}, "text": text}}


def test_start_greets_in_ru_and_ky():
    fake = FakeTransport()
    Bot(fake).handle(_text_update(1, "/start"))
    [(params, _)] = fake.sent("sendMessage")
    assert params["chat_id"] == 42
    assert "Детализация" in params["text"] and "CSV" in params["text"]
    assert "Саламатсызбы" in params["text"] and "жөнөтүңүз" in params["text"]


def test_plain_text_gets_hint():
    fake = FakeTransport()
    Bot(fake).handle(_text_update(1, "привет"))
    assert "файлом" in fake.sent("sendMessage")[0][0]["text"]


def test_csv_upload_gives_summary_and_claim():
    raw = (DATA_DIR / "billing_03.csv").read_bytes()
    fake = FakeTransport({"f1": raw})
    Bot(fake, app_url="https://example.test/app").handle(_doc_update(7, "billing_03.csv", size=len(raw)))
    [(params, _)] = fake.sent("sendMessage")
    text = params["text"]
    assert "К возврату: 65,00 сом" in text
    assert "Потрачено:" in text and "Находок: 5" in text
    assert "Дорогой звонок за границу" in text and "41,00 сом" in text and "2026-09-07 17:54:43" in text
    assert "https://example.test/app" in text
    [(doc_params, files)] = fake.sent("sendDocument")
    name, content = files["document"]
    assert doc_params["chat_id"] == 42 and name.endswith(".txt")
    claim = content.decode("utf-8")
    assert "ЗАЯВЛЕНИЕ" in claim and "65,00 сом" in claim


def test_tariff_saving_in_summary():
    reply = bot.answer_file((DATA_DIR / "billing_03.csv").read_bytes(), "billing_03.csv")
    assert "экономия" in reply.text and "сом в месяц" in reply.text


@pytest.mark.parametrize("name, raw, expected", [
    ("photo.jpg", b"\xff\xd8\xff", "не подходит"),
    ("billing.csv", b"\xff\xd8\xff\xe0garbage", "не текст в UTF-8"),
    ("billing.csv", b"hello,world\n1,2\n", "заголовка"),
    ("billing.csv", b"", "пуст"),
])
def test_bad_files_get_friendly_error(name, raw, expected):
    fake = FakeTransport({"f1": raw})
    Bot(fake).handle(_doc_update(1, name))
    [(params, _)] = fake.sent("sendMessage")
    assert expected in params["text"]
    assert not fake.sent("sendDocument")


def test_too_big_file_is_not_downloaded():
    fake = FakeTransport()
    Bot(fake).handle(_doc_update(1, "billing.csv", size=6 * 1024 * 1024))
    assert "5 МБ" in fake.sent("sendMessage")[0][0]["text"]
    assert not fake.sent("getFile")


def test_download_failure_does_not_crash():
    class Broken(FakeTransport):
        def download(self, file_path):
            raise TelegramError("нет связи")

    fake = Broken()
    Bot(fake, log=lambda m: None).handle(_doc_update(1, "billing.csv"))
    assert "ещё раз" in fake.sent("sendMessage")[0][0]["text"]


def test_polling_moves_offset_and_retries_after_error():
    fake = FakeTransport({"f1": (DATA_DIR / "billing_01.csv").read_bytes()},
                         updates=[[_text_update(5, "/start"), _doc_update(6, "billing_01.csv")], []])
    calls = {"n": 0}
    original = fake.call

    def flaky(method, params=None, files=None):
        if method == "getUpdates" and calls["n"] == 0:
            calls["n"] += 1
            raise TelegramError("timeout")
        return original(method, params, files)

    fake.call = flaky
    slept = []
    Bot(fake, log=lambda m: None, sleep=slept.append).run(max_polls=3)
    assert slept == [1]
    offsets = [p.get("offset") for p, _ in fake.sent("getUpdates")]
    assert offsets == [None, 7]
    assert len(fake.sent("sendMessage")) == 2 and len(fake.sent("sendDocument")) == 1


def test_missing_token_exits_with_clear_error(capsys):
    assert bot.main(env={}) == 2
    err = capsys.readouterr().err
    assert "TELEGRAM_BOT_TOKEN" in err and "@BotFather" in err


def test_cli_bot_flag_without_token(monkeypatch, capsys):
    import analyze as cli
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert cli.main(["--bot"]) == 2
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err


def test_main_with_fake_transport_runs_and_stops():
    fake = FakeTransport(updates=[[_text_update(1, "/start")]])
    assert bot.main(env={"TELEGRAM_BOT_TOKEN": "x"}, transport=fake, max_polls=1) == 0
    assert fake.calls[0][0] == "getMe" and fake.sent("sendMessage")


def test_rejected_token_is_not_printed(capsys):
    class Rejecting(FakeTransport):
        def call(self, method, params=None, files=None):
            raise TelegramError("getMe: Unauthorized")

    secret = "123456:SECRET-TOKEN"
    assert bot.main(env={"TELEGRAM_BOT_TOKEN": secret}, transport=Rejecting()) == 2
    out = capsys.readouterr()
    assert "Unauthorized" in out.err and secret not in out.err + out.out


def test_urllib_transport_errors_hide_token(monkeypatch):
    import urllib.error
    import urllib.request

    def fail(request, timeout):
        raise urllib.error.URLError(ConnectionRefusedError("refused"))

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    secret = "123456:SECRET-TOKEN"
    with pytest.raises(TelegramError) as info:
        bot.UrllibTransport(secret).call("getMe")
    assert secret not in str(info.value)


def test_multipart_body_contains_fields_and_file():
    body, content_type = multipart({"chat_id": 42}, {"document": ("a.txt", "привет".encode("utf-8"))})
    boundary = content_type.split("boundary=")[1]
    assert body.startswith(f"--{boundary}".encode()) and body.rstrip().endswith(f"--{boundary}--".encode())
    assert b'name="chat_id"\r\n\r\n42' in body and 'привет'.encode("utf-8") in body
    assert b'filename="a.txt"' in body


def test_pdf_document_is_accepted_when_pdfplumber_present():
    pytest.importorskip("pdfplumber")
    from billcheck.pdf import csv_to_pdf
    raw = csv_to_pdf((DATA_DIR / "billing_03.csv").read_text(encoding="utf-8-sig"))
    reply = bot.answer_file(raw, "billing_03.pdf")
    assert "К возврату: 65,00 сом" in reply.text and reply.document

