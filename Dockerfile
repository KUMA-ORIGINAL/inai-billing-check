# «Акчам кайда?» в контейнере: веб-приложение, API, ИИ-пояснения и Telegram-бот на webhook.
# Ядро работает на стандартной библиотеке; pdfplumber — только для загрузки PDF.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app
RUN pip install --no-cache-dir "pdfplumber==0.11.*" \
 && useradd --create-home --uid 10001 akcham
COPY --chown=akcham:akcham . .
USER akcham

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# --llm: ИИ включается, только если задан ключ (GEMINI_API_KEY и др.), иначе шаблоны.
# Telegram-бот на webhook включается, если заданы TELEGRAM_BOT_TOKEN и PUBLIC_URL.
CMD ["python", "analyze.py", "--serve", "--llm"]
