"""Бонус ТЗ: короткое письмо абоненту, написанное языковой моделью по уже посчитанным числам.

Модель ничего не считает сама: получает готовые факты и только пересказывает их. Ответ с суммой
или номером, которых нет в фактах, отбрасывается — тогда в отчёте остаются шаблонные пояснения.

Провайдер выбирается по переменным окружения, бесплатные — первыми:
  1. GEMINI_API_KEY (или GOOGLE_API_KEY) — Gemini, бесплатный ключ из Google AI Studio;
     модель — GEMINI_MODEL, по умолчанию gemini-flash-latest.
  2. LLM_BASE_URL + LLM_MODEL (+ LLM_API_KEY) — любой OpenAI-совместимый сервис:
     локальная Ollama (http://localhost:11434/v1, без ключа и без интернета), Groq, OpenRouter.
  3. ANTHROPIC_API_KEY — Claude через пакет anthropic (requirements-llm.txt).
Без провайдера или при любой ошибке возвращается None — отчёт строится как обычно.
"""
import json
import os
import re
import sys
from collections.abc import Callable
from decimal import Decimal
from urllib.request import Request, urlopen

from .explain import disputed, explain, possible_overpay
from .html import anomaly_title
from .money import format_som
from .pipeline import Result

Generate = Callable[[str, str], str | None]

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_DEFAULT_MODEL = "gemini-flash-latest"
CLAUDE_MODEL = "claude-opus-5-5"
TIMEOUT_SEC = 60

SYSTEM = (
    "Ты пишешь короткое письмо абоненту учебного оператора связи INAI Mobile по итогам проверки его "
    "детализации. Пиши по-русски, на «вы», 4–6 предложений, без заголовков, списков и markdown. "
    "Используй только факты из сообщения: суммы, даты и номера переписывай дословно, ничего не добавляй "
    "и не пересчитывай. Начни с главного — сколько денег, возможно, списано лишнего. Назови самые крупные "
    "спорные списания и предложи подать заявление на перерасчёт: оно уже подготовлено ниже на странице. "
    "Необычные дни упомяни отдельно и не прибавляй к сумме возврата. Не обещай, что деньги вернут: "
    "решение принимает оператор."
)
MONEY = re.compile(r"(\d{1,3}(?:\s\d{3})+|\d+)[.,](\d{2})(?!\d)")  # \s — и неразрывные пробелы разрядов
PHONE = re.compile(r"\+?\d{5,}")
THINK = re.compile(r"<think>.*?</think>", re.S)  # рассуждения reasoning-моделей (deepseek-r1 и др.)
LINK = re.compile(r"https?://|www\.", re.I)
MAX_LATIN_SHARE = 0.15


def summary_facts(result: Result) -> dict:
    """Только посчитанные числа — то, что модели разрешено пересказать."""
    rows = sorted(disputed(result.anomalies).values(), key=lambda a: a.dt)
    spikes = [a for a in result.anomalies if a.anomaly_type == "day_spike"]
    return {
        "файл": result.source.name,
        "потрачено_сом": format_som(Decimal(str(result.report["total_som"]))),
        "возможно_лишнее_сом": format_som(possible_overpay(result.anomalies)),
        "спорные_списания": [{"тип": anomaly_title(a.anomaly_type, a.type), "когда": f"{a.dt:%d.%m.%Y %H:%M}",
                              "номер": a.charge.number, "к_возврату_сом": format_som(a.amount),
                              "пояснение": explain(a)} for a in rows],
        "необычные_дни": [{"дата": f"{a.dt:%d.%m.%Y}", "пояснение": explain(a)} for a in spikes],
    }


def _money_tokens(text: str) -> set[str]:
    return {re.sub(r"\s", "", whole) + "," + cents for whole, cents in MONEY.findall(text)}


def rejection_reason(text: str, facts: dict, facts_text: str) -> str | None:
    """Почему ответ модели нельзя показать абоненту (None — можно)."""
    if LINK.search(text):
        return "в тексте есть ссылка"
    letters = [ch for ch in PHONE.sub("", text) if ch.isalpha()]
    if letters and sum(ch.isascii() for ch in letters) / len(letters) > MAX_LATIN_SHARE:
        return "текст не на русском"
    if _money_tokens(facts["возможно_лишнее_сом"]) - _money_tokens(text):
        return "нет главной суммы — возможно лишнего"
    if not _money_tokens(text) <= _money_tokens(facts_text):
        return "сумма, которой нет в расчёте"
    if not set(PHONE.findall(text)) <= set(PHONE.findall(facts_text)):
        return "номер, которого нет в детализации"
    return None


def _post_json(url: str, body: dict, headers: dict[str, str]) -> dict:
    request = Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
                      headers={"Content-Type": "application/json", **headers})
    with urlopen(request, timeout=TIMEOUT_SEC) as response:
        return json.loads(response.read().decode("utf-8"))


def gemini_generate(api_key: str, model: str = GEMINI_DEFAULT_MODEL) -> Generate:
    def generate(system: str, user: str) -> str | None:
        answer = _post_json(GEMINI_URL.format(model=model),
                            {"system_instruction": {"parts": [{"text": system}]},
                             "contents": [{"role": "user", "parts": [{"text": user}]}]},
                            {"x-goog-api-key": api_key})  # ключ в заголовке, не в адресе
        candidates = answer.get("candidates") or []
        if not candidates:  # ответ заблокирован фильтрами — шаблоны
            return None
        return "".join(part.get("text", "") for part in candidates[0].get("content", {}).get("parts", []))
    return generate


def openai_compatible_generate(base_url: str, model: str, api_key: str | None = None) -> Generate:
    def generate(system: str, user: str) -> str | None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        answer = _post_json(base_url.rstrip("/") + "/chat/completions",
                            {"model": model, "messages": [{"role": "system", "content": system},
                                                          {"role": "user", "content": user}]}, headers)
        choices = answer.get("choices") or []
        return choices[0].get("message", {}).get("content") if choices else None
    return generate


def claude_generate(client) -> Generate:
    def generate(system: str, user: str) -> str | None:
        response = client.beta.messages.create(
            model=CLAUDE_MODEL, max_tokens=8000, output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            system=system, messages=[{"role": "user", "content": user}])
        if response.stop_reason == "refusal":
            return None
        return "".join(block.text for block in response.content if block.type == "text")
    return generate


def pick_provider() -> tuple[str, Generate] | None:
    """(название, функция) первого настроенного провайдера; бесплатные — первыми."""
    env = os.environ
    gemini_key = env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")
    if gemini_key:
        model = env.get("GEMINI_MODEL") or GEMINI_DEFAULT_MODEL
        return f"Gemini ({model})", gemini_generate(gemini_key, model)
    if env.get("LLM_BASE_URL") and env.get("LLM_MODEL"):
        return (f"{env['LLM_MODEL']} через {env['LLM_BASE_URL']}",
                openai_compatible_generate(env["LLM_BASE_URL"], env["LLM_MODEL"], env.get("LLM_API_KEY")))
    if env.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
        except ImportError:
            print("ИИ-письмо: для Claude нужен пакет anthropic (pip install -r requirements-llm.txt).",
                  file=sys.stderr)
            return None
        return f"Claude ({CLAUDE_MODEL})", claude_generate(anthropic.Anthropic())
    return None


def llm_summary(result: Result, generate: Generate | None = None) -> str | None:
    if generate is None:
        provider = pick_provider()
        if provider is None:
            print("ИИ-письмо: провайдер не настроен (GEMINI_API_KEY или LLM_BASE_URL + LLM_MODEL) — "
                  "отчёт с шаблонными пояснениями.", file=sys.stderr)
            return None
        generate = provider[1]
    facts = summary_facts(result)
    facts_text = json.dumps(facts, ensure_ascii=False, indent=1)
    try:
        text = generate(SYSTEM, "Факты проверки детализации:\n" + facts_text)
    except Exception as exc:  # бонус не должен ломать отчёт: сеть, лимиты, неверный ключ → шаблоны
        print(f"ИИ-письмо недоступно ({type(exc).__name__}): отчёт с шаблонными пояснениями.", file=sys.stderr)
        return None
    text = THINK.sub("", text or "").strip()
    reason = rejection_reason(text, facts, facts_text) if text else "модель вернула пустой ответ"
    if reason:
        print(f"ИИ-письмо отброшено ({reason}): отчёт с шаблонными пояснениями.", file=sys.stderr)
        return None
    return text
