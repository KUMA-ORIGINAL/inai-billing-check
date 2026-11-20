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
DIGITS = re.compile(r"\d+")  # каждое число в письме (суммы, номера, даты) должно встречаться в фактах…
MAX_FREE_COUNT = 10  # …кроме маленьких счётчиков вроде «4 спорных списания»
PROMISE = re.compile(r"\b(верн[её]м|верн[её]т|вернут|гарантир\w*)\b", re.I)


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
    invented = {run for run in DIGITS.findall(text) if int(run) > MAX_FREE_COUNT} - set(DIGITS.findall(facts_text))
    if invented:
        return "число, которого нет в расчёте: " + ", ".join(sorted(invented))
    if PROMISE.search(text):
        return "обещание вернуть деньги — решает оператор"
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


EXPLAIN_SYSTEM = {
    "ru": ("Ты объясняешь абоненту учебного оператора INAI Mobile одно подозрительное списание из его детализации. "
           "Пиши по-русски, на «вы», 2–3 коротких предложения простыми словами, как пожилому человеку, без списков "
           "и markdown. Используй только факты из сообщения: числа и номера переписывай дословно, ничего не "
           "пересчитывай и не обещай вернуть деньги — решает оператор. Закончи одним понятным шагом, что сделать."),
    "ky": ("Сен INAI Mobile окуу операторунун абонентине анын детализациясындагы бир шектүү төлөмдү түшүндүрөсүң. "
           "Кыргызча, «сиз» деп, 2–3 кыска сүйлөм менен, карыя адамга түшүндүргөндөй жөнөкөй сөздөр менен жаз, "
           "тизмесиз жана markdownсыз. Билдирүүдөгү фактыларды гана колдон: сандарды жана номерлерди так көчүр, "
           "эч нерсени кайра эсептебе жана акчаны кайтарабыз деп убада бербе — оператор чечет. "
           "Акырында эмне кылуу керектигин бир кадам менен айт."),
}
MASK = re.compile(r"\+?\d{9,}")


def mask_number(number: str) -> str:
    """+996777165026 → +99677••••26: в модель не уходят полные номера абонента и его собеседников."""
    if not number or len(re.sub(r"\D", "", number)) < 9:
        return number
    return number[:6] + "••••" + number[-2:]


def anomaly_facts(anomaly: dict, lang: str) -> dict:
    """Факты одной находки для модели: только посчитанные числа, номера замаскированы."""
    ky = lang == "ky"
    return {
        "что_нашли": anomaly.get("reason_ky" if ky else "reason") or anomaly.get("reason", ""),
        "когда": anomaly.get("datetime", ""),
        "номер": mask_number(str(anomaly.get("number") or "")),
        "сумма_сом": anomaly.get("amount_som"),
        "к_возврату": bool(anomaly.get("reclaimable")),
        "пояснение": MASK.sub(lambda m: mask_number(m.group()),
                              str(anomaly.get("explanation_ky" if ky else "explanation") or "")),
        "что_делать": str(anomaly.get("advice_ky" if ky else "advice") or ""),
    }


def explain_rejection(text: str, facts_text: str, lang: str) -> str | None:
    if LINK.search(text):
        return "в тексте есть ссылка"
    letters = [ch for ch in text if ch.isalpha()]
    if letters and sum(ch.isascii() for ch in letters) / len(letters) > MAX_LATIN_SHARE:
        return "текст не на кириллице"
    invented = {run for run in DIGITS.findall(text) if int(run) > MAX_FREE_COUNT} - set(DIGITS.findall(facts_text))
    if invented:
        return "число, которого нет в фактах: " + ", ".join(sorted(invented))
    if lang == "ru" and PROMISE.search(text):
        return "обещание вернуть деньги — решает оператор"
    return None


def template_explanation(anomaly: dict, lang: str = "ru") -> dict:
    """Пояснение без ИИ: готовый текст отчёта и шаг «что делать» на нужном языке."""
    ky = lang == "ky"
    text = str(anomaly.get("explanation_ky" if ky else "explanation") or anomaly.get("explanation") or "")
    advice = str(anomaly.get("advice_ky" if ky else "advice") or "")
    return {"text": (text + (" " + advice if advice else "")).strip(), "source": "template"}


def explain_anomaly(anomaly: dict, lang: str = "ru", generate: Generate | None = None) -> dict:
    """«Объяснить проще»: {"text", "source": "llm" | "template"}. Без ключа, сети или при выдумке — шаблон."""
    lang = "ky" if lang == "ky" else "ru"
    fallback = template_explanation(anomaly, lang)
    if generate is None:
        provider = pick_provider()
        if provider is None:
            return fallback
        generate = provider[1]
    facts_text = json.dumps(anomaly_facts(anomaly, lang), ensure_ascii=False, indent=1)
    try:
        text = THINK.sub("", generate(EXPLAIN_SYSTEM[lang], "Факты:\n" + facts_text) or "").strip()
    except Exception as exc:  # сеть, лимиты, неверный ключ → шаблон
        print(f"ИИ-пояснение недоступно ({type(exc).__name__}): шаблон.", file=sys.stderr)
        return fallback
    reason = explain_rejection(text, facts_text, lang) if text else "пустой ответ"
    if reason:
        print(f"ИИ-пояснение отброшено ({reason}): шаблон.", file=sys.stderr)
        return fallback
    return {"text": text, "source": "llm"}
