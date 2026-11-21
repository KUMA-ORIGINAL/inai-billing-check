# Передача проекта «Акчам кайда?»

Состояние на 21.11.2026. Всё лежит в `main` на GitHub (последний коммит `4096a5f`). Ядро ТЗ 4 готово и проверено:
на открытых данных 5 из 5 отчётов совпадают с эталонами, 20 из 20 аномалий, 0 ложных. Тестов 252, CI зелёный.

## С чего начать (15 минут)

```bash
git clone https://github.com/KUMA-ORIGINAL/inai-billing-check.git
cd inai-billing-check
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt      # Linux/macOS: .venv/bin/pip …
.venv\Scripts\python -m pytest -q                       # 250 passed, 2 skipped
python analyze.py --validate data                       # ИТОГО 5/5 ЗАЧЁТ
run.bat --serve                                         # приложение на http://127.0.0.1:8000
```

Если у вас уже есть старая копия: `git pull` — локальный `main` мог остаться на `e145efa`.

Дальше прочитайте: [README.md](../README.md) (запуск, API, правила, параметры), [docs/demo.md](demo.md) (сценарий защиты на 3 минуты и ответы на вопросы жюри).

## Где что в коде

| Часть | Файлы | Тесты |
|---|---|---|
| Ядро ТЗ 4 (не ломать: это 40 баллов автопроверки) | `billcheck/parse.py`, `report.py`, `anomalies.py`, `money.py`, `explain.py`, `pipeline.py`, `analyze.py`, `check.py` | `test_parse`, `test_report`, `test_anomalies`, `test_check`, `test_app` (fuzz) |
| Расширенный отчёт для экрана: улики, тексты RU/KY, сводка, сверка с эталоном, радар | `billcheck/rich.py` | `test_app.py` |
| Приложение: снимок семьи, загрузка CSV/PDF, Markdown и печатный HTML | `billcheck/app.py`, `billcheck/templates/app.html` | `test_app.py`, `test_server.py` |
| Сервер и API (`/api/health`, `demo`, `analyze`, `radar`, `explain`, `render`) | `billcheck/server.py` | `test_server.py` |
| Тарифный советник (данные и правила ТЗ 2) | `billcheck/tariffs.py`, `data/tariffs.json`, `data/addons.json` | `test_tariffs.py` |
| ИИ: письмо и «Объяснить проще» | `billcheck/llm.py` | `test_llm.py`, `test_app.py` |
| Telegram-бот | `billcheck/bot.py` (`python analyze.py --bot`) | `test_bot.py` |
| PDF: чтение (pdfplumber) и демо-генерация | `billcheck/pdf.py`, `data/billing_03_sample.pdf` | `test_app.py`, `test_pdf_writer.py` |
| Самопроверка `--validate` | `billcheck/validate.py` | `test_validate.py` |
| Семья: имена, роли, номера | `data/family.json` | `test_family.py` |
| Старый интерфейс (`/classic`, `out/<файл>/report.html`, `out/family.html`) | `billcheck/html.py`, `claim.py`, `family.py`, `templates/report.html`, `family.html`, `upload.html` | `test_html.py`, `test_family_html.py`, `test_pages_js.py` |
| Деплой | `.github/workflows/pages.yml` (GitHub Pages), `.github/workflows/ci.yml`, `render.yaml` | — |

Важные решения, которые не стоит менять без причины:
- **Только стандартная библиотека Python.** Жюри запускает одной командой без установки. Необязательные пакеты (`pdfplumber`, `anthropic`) импортируются лениво.
- **В `anomalies.json` — строго пять правил ТЗ.** Радар, дневной контент 7575 и тариф — только на экране: лишние записи дают ложные срабатывания (допускается не больше 2).
- **«Новая подписка» — первая В ФАЙЛЕ**, а не по времени (так в уточнениях); дубли ищутся по времени. Это закреплено fuzz-тестом.
- **Пороги правил** (`anomalies.Rules`) по умолчанию строго как в уточнениях; менять их можно только в демо через «Пороги».
- **`app.html` — один самодостаточный файл** без сборки: данные приходят из `/api/*` или из вшитого снимка `window.TAZA_SNAPSHOT`. Строку-заглушку снимка, `id` элементов и `data-*` атрибуты трогать нельзя: на них завязан JS и тесты.

## Что осталось сделать

### До защиты (обязательно)

- [ ] **Пройти все экраны глазами после перекраски** (коммит `4096a5f`). Проверены главная, карточка Айгерим, тариф и «Для родителей». Не проверены: радар, ширина телефона (375 px), кыргызский язык, окно «Пороги», окно дня.
- [ ] **Отрепетировать демо 3 раза** по [docs/demo.md](demo.md) и записать видео-запаску.
- [ ] **Показать носителю кыргызского** тексты, написанные без проверки: короткий текст первого экрана, «секирик күн», пояснения и советы в `billcheck/rich.py` (`explanation_ky`, `advice_texts`, `reasons_ky`).

### Желательно

- [ ] **Render** (полная версия в интернете с загрузкой файлов): render.com → New → Blueprint → этот репозиторий → Apply. Всё описано в `render.yaml`. Бесплатный сервис засыпает через 15 минут — открыть за пару минут до показа.
- [ ] **Telegram-бот с настоящим токеном.** Проверен только тестами с подменой сети. Токен — у @BotFather, затем `$env:TELEGRAM_BOT_TOKEN = "…"; python analyze.py --bot`. Бот работает, пока запущен на компьютере; на Render он не развёрнут.
- [ ] **PDF:** `pip install pdfplumber`, если хотите показывать загрузку PDF. Проверено только на нашем демо-PDF (`data/billing_03_sample.pdf`), настоящей выгрузки оператора нет.
- [ ] **Ключ ИИ** для «Объяснить проще» и письма: `GEMINI_API_KEY` (бесплатный уровень) и запуск с `--llm`. Без ключа работают шаблоны — это нормально.

### Можно потом

- [ ] Обновить `docs/how-it-works.md`: он описывает старый интерфейс и не знает про приложение, радар, тариф и бота.
- [ ] Решить судьбу старого интерфейса (`/classic`, `report.html`, `family.html`, `upload.html`): либо удалить вместе с тестами, либо оставить как запасной.
- [ ] Обновить версии actions в workflow (предупреждение GitHub про Node.js 20).
- [ ] Из ТЗ команды не сделано (сознательно или не успели): FastAPI + Docker Compose (оставили стандартную библиотеку), хранение отчётов в SQLite и `/api/reports/{id}`, претензия в PDF/DOCX (есть .txt и печать в PDF из браузера), модуль `python -m akcham validate` (есть `python analyze.py --validate`), экран для малого бизнеса, QR-код на слайде.

## Ссылки

- Репозиторий: https://github.com/KUMA-ORIGINAL/inai-billing-check
- Сайт без сервера (GitHub Pages, обновляется на каждый push в `main`): https://kuma-original.github.io/inai-billing-check/
- ТЗ и данные организаторов: папка участников `INAI_2026_participants_v1.1` (README_RU.md, CLARIFICATIONS_RU.md, 04_billing, 02_tariffs, 05_support).
- Перед каждым push: `pytest` зелёный и `python analyze.py --validate data` даёт 5/5.
