"""Бот на webhook внутри веб-сервера и лимит запросов к ИИ: сеть не нужна."""
import json
import threading
import time
import urllib.error
import urllib.request

from helpers import DATA_DIR
from test_bot import FakeTransport, _doc_update, _text_update

from billcheck.bot import Bot, WebhookBot, webhook_from_env, webhook_secret
from billcheck.server import RateLimit, make_server


def _post(url: str, body: dict, headers: dict | None = None) -> int:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def _wait(predicate, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_secret_is_stable_and_hides_token():
    secret = webhook_secret("123:ABC")
    assert secret == webhook_secret("123:ABC") and secret != webhook_secret("123:ABD")
    assert "ABC" not in secret and len(secret) == 40


def test_webhook_from_env_registers_url_without_token():
    fake = FakeTransport()
    hook = webhook_from_env({"TELEGRAM_BOT_TOKEN": "123:ABC", "PUBLIC_URL": "https://akcham.example/"}, fake)
    [(params, _)] = fake.sent("setWebhook")
    assert params["url"] == "https://akcham.example/tg/" + webhook_secret("123:ABC")
    assert params["secret_token"] == webhook_secret("123:ABC") and "123:ABC" not in params["url"]
    assert hook.bot.app_url == "https://akcham.example/"
    assert webhook_from_env({"TELEGRAM_BOT_TOKEN": "123:ABC"}, fake) is None
    assert webhook_from_env({"PUBLIC_URL": "https://x"}, fake) is None


def test_server_accepts_only_signed_updates_and_replies_in_background():
    fake = FakeTransport({"f1": (DATA_DIR / "billing_03.csv").read_bytes()})
    hook = WebhookBot(Bot(fake, "https://akcham.example", log=lambda m: None), "s3cret")
    srv = make_server(DATA_DIR, port=0, telegram=hook)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert _post(base + "/tg/s3cret", _text_update(1, "/start")) == 404  # без заголовка Telegram
        assert _post(base + "/tg/wrong", _text_update(1, "/start"), {"X-Telegram-Bot-Api-Secret-Token": "s3cret"}) == 404
        assert _post(base + "/tg/s3cret", _doc_update(2, "billing_03.csv"),
                     {"X-Telegram-Bot-Api-Secret-Token": "s3cret"}) == 200
        assert _wait(lambda: fake.sent("sendDocument"))
        assert "65,00" in fake.sent("sendMessage")[0][0]["text"]
    finally:
        srv.shutdown()
        srv.server_close()


def test_server_without_bot_has_no_telegram_route():
    srv = make_server(DATA_DIR, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert _post(f"http://127.0.0.1:{srv.server_address[1]}/tg/x", {}) == 404
    finally:
        srv.shutdown()
        srv.server_close()


def test_rate_limit_per_client():
    now = [0.0]
    limit = RateLimit(limit=2, window=60, clock=lambda: now[0])
    assert limit.allow("a") and limit.allow("a") and not limit.allow("a")
    assert limit.allow("b")
    now[0] = 61
    assert limit.allow("a")


def test_explain_falls_back_to_template_over_limit(monkeypatch):
    import billcheck.server as server_module
    monkeypatch.setattr(server_module, "explain_anomaly", lambda a, lang: {"text": "ИИ", "source": "llm"})
    srv = make_server(DATA_DIR, port=0, use_llm=True, explain_limit=RateLimit(limit=1, window=60))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/api/explain"
    anomaly = {"explanation": "Шаблон.", "advice": "Совет."}

    def ask():
        request = urllib.request.Request(url, data=json.dumps({"anomaly": anomaly}).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode())
    try:
        assert ask()["source"] == "llm"
        second = ask()
        assert second["source"] == "template" and "лимит" in second["note"]
    finally:
        srv.shutdown()
        srv.server_close()
