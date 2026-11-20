import io
import json
import re
import sys
from types import SimpleNamespace

import pytest

from billcheck import llm
from billcheck.html import render_report
from billcheck.llm import llm_summary, pick_provider, summary_facts
from billcheck.pipeline import analyze
from helpers import DATA_DIR

LETTER = ("По детализации за сентябрь возможно лишнее списано 65,00 сом. Самое крупное — звонок на +971517547668: "
          "переплата 41,00 сом. Заявление на перерасчёт готово ниже.")
ENV = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL",
       "ANTHROPIC_API_KEY")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="module")
def grandma():
    return analyze(DATA_DIR / "billing_03.csv")


def fake(text: str | None = LETTER, error: Exception | None = None):
    calls = []

    def generate(system: str, user: str) -> str | None:
        calls.append((system, user))
        if error:
            raise error
        return text
    generate.calls = calls
    return generate


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def capture_http(monkeypatch, answer: dict) -> list:
    requests = []

    def urlopen(request, timeout):
        requests.append(request)
        return FakeResponse(json.dumps(answer).encode("utf-8"))
    monkeypatch.setattr(llm, "urlopen", urlopen)
    return requests


def test_no_provider_returns_none(grandma, monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)
    assert pick_provider() is None
    assert llm_summary(grandma) is None


def test_letter_goes_into_report(grandma):
    text = llm_summary(grandma, generate=fake())
    assert text == LETTER
    page = render_report(grandma, "Бабушка", llm_text=text)
    data = json.loads(re.search(r'<script id="bill-data" type="application/json">(.*?)</script>', page, re.S).group(1))
    assert data["llm"] == LETTER


def test_numbers_in_prompt(grandma):
    generate = fake()
    llm_summary(grandma, generate=generate)
    system, user = generate.calls[0]
    assert "INAI Mobile" in system
    assert "65,00" in user and "62626" in user and "41,00" in user


def test_invented_sum_is_rejected(grandma):
    assert llm_summary(grandma, generate=fake("Вам вернут 99,99 сом.")) is None


def test_errors_and_empty_answers_return_none(grandma):
    assert llm_summary(grandma, generate=fake(error=OSError("network down"))) is None
    assert llm_summary(grandma, generate=fake(text=None)) is None


def test_gemini_is_free_default(grandma, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    requests = capture_http(monkeypatch, {"candidates": [{"content": {"parts": [{"text": LETTER}]}}]})
    name, generate = pick_provider()
    assert name.startswith("Gemini")
    assert llm_summary(grandma, generate=generate) == LETTER
    request = requests[0]
    assert request.full_url.endswith("/models/gemini-flash-latest:generateContent")
    assert request.get_header("X-goog-api-key") == "test-key" and "test-key" not in request.full_url
    body = json.loads(request.data)
    assert "INAI Mobile" in body["system_instruction"]["parts"][0]["text"]
    assert "65,00" in body["contents"][0]["parts"][0]["text"]


def test_gemini_blocked_answer_returns_none(grandma, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    capture_http(monkeypatch, {"promptFeedback": {"blockReason": "OTHER"}})
    assert llm_summary(grandma, generate=pick_provider()[1]) is None


def test_openai_compatible_local_ollama(grandma, monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1/")
    monkeypatch.setenv("LLM_MODEL", "qwen2.5")
    requests = capture_http(monkeypatch, {"choices": [{"message": {"content": LETTER}}]})
    name, generate = pick_provider()
    assert "qwen2.5" in name
    assert llm_summary(grandma, generate=generate) == LETTER
    request = requests[0]
    assert request.full_url == "http://localhost:11434/v1/chat/completions"
    assert request.get_header("Authorization") is None
    body = json.loads(request.data)
    assert body["model"] == "qwen2.5" and [m["role"] for m in body["messages"]] == ["system", "user"]


def test_openai_compatible_needs_model(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)
    monkeypatch.setenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    assert pick_provider() is None


def test_claude_used_only_with_explicit_key(grandma, monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=LETTER)])
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert llm_summary(grandma, generate=llm.claude_generate(client)) == LETTER
    assert calls[0]["model"] == "claude-opus-5-5"
    refusing = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(
        create=lambda **kw: SimpleNamespace(stop_reason="refusal", content=[]))))
    assert llm_summary(grandma, generate=llm.claude_generate(refusing)) is None


def test_facts_skip_day_spike_from_overpay(grandma):
    facts = summary_facts(grandma)
    assert facts["возможно_лишнее_сом"] == "65,00"
    assert [a["тип"] for a in facts["спорные_списания"]] == [
        "Дорогой международный звонок", "Двойное списание", "Платное SMS ночью", "Новая подписка"]
    assert facts["необычные_дни"][0]["дата"] == "29.09.2026"


def test_cli_llm_without_provider_still_writes_report(tmp_path, monkeypatch):
    import analyze as cli
    monkeypatch.setitem(sys.modules, "anthropic", None)
    out = tmp_path / "out"
    assert cli.main([str(DATA_DIR / "billing_03.csv"), "--out", str(out), "--llm"]) == 0
    assert (out / "report.html").is_file() and (out / "anomalies.json").is_file()


# Ответы маленьких локальных моделей, на которых проверяли живьём (Ollama gemma3:270m, deepseek-r1:1.5b)
GENERIC = "Чтобы я мог написать вам письмо, мне нужно знать, в каком формате вы хотите его получить."
ENGLISH = ("Possible extras due on a local basis: 65,00 rubles. Overpayment of 4 920.54 rubles was noted. "
           "Check [link](https://support.example.com)")


def test_reply_without_the_overpay_figure_is_rejected(grandma):
    assert llm_summary(grandma, generate=fake(GENERIC)) is None


def test_amount_checked_whatever_the_currency_word(grandma):
    assert llm_summary(grandma, generate=fake("Возможно лишнее — 65,00 сом, а ещё 4 920,54 рубля.")) is None


def test_english_or_links_rejected(grandma):
    assert llm_summary(grandma, generate=fake(ENGLISH)) is None
    assert llm_summary(grandma, generate=fake(LETTER + " Подробнее: https://example.com")) is None


def test_think_block_is_stripped(grandma):
    assert llm_summary(grandma, generate=fake("<think>считаю 4 920,54</think>\n" + LETTER)) == LETTER
