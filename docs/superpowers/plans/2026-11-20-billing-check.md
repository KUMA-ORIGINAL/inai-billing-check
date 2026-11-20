# «Где мои деньги?» — ТЗ 4 «Расшифровщик детализации»: план на 1 место

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ядро ТЗ 4 с точным совпадением со всеми эталонами + продукт «Где мои деньги?», который за одну кнопку превращает детализацию в заявление на возврат денег и защищает всю семью от скрытых подписок.

**Architecture:** Чистый Python без зависимостей во время выполнения. `parse` (грязный CSV) → `report` (суммы) → `anomalies` (5 правил из уточнений) → `pipeline` (файлы для жюри). Поверх ядра — `explain`/`claim` (тексты для человека), `family` (взгляд на несколько номеров сразу), самодостаточные HTML-страницы и маленький локальный веб-сервер на `http.server` для загрузки файла в демо. Деньги — только `Decimal`, `ROUND_HALF_UP` до 0.01 на выходе.

**Tech Stack:** Python 3.10+, stdlib (`csv`, `decimal`, `datetime`, `statistics`, `json`, `http.server`), pytest; опционально `anthropic` для бонуса с ИИ.

**Spec:**
- `C:\Users\Slim 7 Pro\Downloads\Telegram Desktop\INAI_2026_participants_v1.1\participants\TASKS_ORIGINAL_RU.docx` — «ТЗ 4. Расшифровщик детализации» и «Критерии оценки»
- `...\participants\CLARIFICATIONS_RU.md` — раздел «4. Детализация» (приоритет над DOCX)
- `...\participants\04_billing\` — 5 пар `billing_0N.csv` + `billing_0N_expected.json`, `README_RU.md`
- `...\participants\05_support\faq.json` — тексты советов RU/KY (id 8, 14, 15)
- Объявление жюри: обязательные пункты остаются; 10 баллов за демо — за идею продукта, осмысленное применение и уверенное объяснение реализации.

**Репозиторий:** `C:\Users\Slim 7 Pro\PycharmProjects\inai-billing-check` (ТЗ 7 остаётся в `inai-coverage-map`). **До старта — подтвердить у менторов смену ТЗ.**

---

## Как мы забираем 100 баллов

| Критерий | Баллы | Чем берём |
|---|---|---|
| Автопроверка | 40 | Все 20 аномалий открытых данных совпадают с эталонами 1-в-1 (тест). `check.py` повторяет зачёт жюри: ≥ 80% найдено, ≤ 2 ложных. Никаких «лишних» находок в `anomalies.json`. |
| Качество кода | 20 | Маленькие модули с одной ответственностью, `Decimal` для денег, понятные ошибки и коды выхода, ~60 тестов, запуск одной командой. |
| Обязательные пункты | 20 | Таблица «пункт ТЗ → где увидеть → код → тест» в README и **чек-лист ТЗ прямо в интерфейсе**. |
| Бонусы | 10 | График трат по дням с отмеченными аномалиями + пояснения через ИИ (с откатом на шаблоны). PDF-чтение не делаем: нет образцов. |
| Демо | 10 | Одна история семьи → живая загрузка файла → кнопка «Подготовить возврат» → находка, которую не видит ни одно правило ТЗ (7575 у всей семьи) → честные цифры проверки. |

## Продукт

**«Где мои деньги?» — семейный щит от скрытых списаний**

- **Кто пользуется:** молодые люди, которые помогают родителям и бабушкам со связью. Пожилые не читают детализацию и случайно подписываются на платный контент через баннеры.
- **Проблема:** детализация — сотни строк в двух форматах дат. Ночная подписка за 15 сом, двойное списание или звонок по 40 сом/мин в ней не видны.
- **Как работает:**
  1. Загрузил детализацию (или выбрал профиль семьи) → за секунду отчёт-«чек»: сколько потрачено и **сколько возможно лишнего**.
  2. Каждая спорная строка — карточка с объяснением человеческим языком и советом из FAQ оператора (RU/KY).
  3. Кнопка **«Подготовить возврат N сом»** → готовое заявление на перерасчёт в INAI Mobile: дата, время, номер, сумма, строка детализации. Скопировать / скачать / распечатать в PDF.
  4. Окно телефона показывает, как абонент мог бы одним меню отключить подписки (**помеченная симуляция**, связь с ТЗ 3; реальный совет — из FAQ: личный кабинет → «Подписки»).
  5. **Семейный экран:** все номера семьи, флажки «новая подписка у бабушки», и **репутация коротких номеров** по всей семье: «7575 списывает деньги у 5 из 5 номеров — 85 сом».
- **Объединение ТЗ:** советы и языки из ТЗ 5, симуляция меню из ТЗ 3, (если останется время) подсказка по тарифу из ТЗ 2.
- **Честность (главное в ответах на вопросы):** оператор — учебный **INAI Mobile**; деньги мы не возвращаем, а готовим заявление; симуляции подписаны; каждое число на экране посчитано из данных.

### Три вау-момента (все — из настоящих открытых данных)

1. **«Нашли 65 сом у бабушки за 1 секунду».** billing_03: ночное SMS на 62626 в 01:37 (10 сом), звонок в ОАЭ +971 по 40 сом/мин (переплата 41 сом), двойное списание за 53 с (6 сом), подписка 53530 (8 сом). Итого к возврату **65,00 сом**.
2. **«То, чего не видит ни одно правило».** Короткий номер **7575** списывает за контент у **всех 5** членов семьи — 7 дневных списаний, **85 сом**. Ни под одно правило ТЗ они не попадают (днём, не подписка, не дубль), а семейный экран показывает схему.
3. **«Проверено на ваших эталонах».** Бейдж в интерфейсе: «Открытые данные организаторов: 20 из 20 аномалий, 0 ложных, 5 из 5 отчётов совпали» — считается вживую при наличии `*_expected.json`.

Цифры для зала: 5 абонентов, 8 285,42 сом расходов за сентябрь, 20 аномалий, **204,26 сом** спорных списаний (2,5% счёта).

---

## Global Constraints

- Python 3.10+; во время выполнения — только стандартная библиотека. `pytest` — тесты, `anthropic` — только флаг `--llm`.
- Запуск одной командой: `run.bat` / `./run.sh` (создают `.venv`, ставят `requirements.txt`, запускают `analyze.py "$@"`); `python analyze.py <файл>` работает без установки. `run.bat --serve` запускает веб-демо.
- Входной CSV: UTF-8 (допускается BOM, CRLF), заголовок `datetime,type,number,duration_sec,mb,cost_som` не считается в `dropped_rows`.
- Даты — только `YYYY-MM-DD HH:MM:SS` и `DD.MM.YYYY HH:MM:SS`; `2026/09/12 …` и несуществующие даты (`2026-09-31`) — битые.
- Суммы с точкой или запятой (`"1,20"` в кавычках).
- Строка отбрасывается целиком (порядок проверки = порядок причин): `empty_line` (пустая физическая строка) → `column_count` (≠ 6) → `unknown_type` (∉ call, sms, data, subscription, content) → `bad_datetime` → `bad_number` (`duration_sec`, `mb`, `cost_som` пустое, нечисловое, `NaN`, `Infinity`, отрицательное). `number` может быть пустым; это не причина отбрасывать.
- Полные дубли **не удалять** из отчёта.
- Деньги — `Decimal`; в JSON — `float` с 2 знаками, `ROUND_HALF_UP`.
- `report.json` — ровно ключи эталона: `valid_rows, dropped_rows, total_som, by_category, by_day, top5_numbers, anomalies`; `by_category` — все 5 типов, отсутствующие `0.0`.
- Аномалия в `report.json`: `{"datetime": "YYYY-MM-DD HH:MM:SS", "type", "anomaly_type", "amount_som", "reason"}`, сортировка по `datetime`. `anomalies.json` — те же 5 полей + `line`, `explanation_ru`, `advice_ru`, `advice_ky`.
- Тексты `reason` дословно:
  - `night_charge` — `Платное SMS/контент ночью с 00:00 до 06:00`
  - `new_subscription` — `Новая подписка на короткий номер`
  - `duplicate_charge` — `Одинаковое списание в пределах 60 секунд`
  - `international_rate` — `Международный звонок дороже 20 сом/мин`
  - `day_spike` — `Расходы дня выше среднего предыдущих 7 дней: z-score > 3`
- Правила аномалий (CLARIFICATIONS §4), на каждое правило — отдельная аномалия:
  - **night_charge:** `type ∈ {sms, content}`, `cost > 0`, время в `[00:00:00, 06:00:00)`; сумма = полная стоимость.
  - **new_subscription:** первая **по порядку строк файла** запись `subscription` на номер из 3–6 цифр без `+`; сумма = полная стоимость.
  - **duplicate_charge:** сортировка по времени; совпадают `type, number, duration_sec, mb, cost_som` (как числа); разница 0–60 с включительно; флаг только на более позднюю; сумма = её стоимость.
  - **international_rate:** номер начинается с `+`, но не с `+996`; `duration_sec > 0`; `cost*60/duration_sec > 20`; сумма = `max(0, cost − 20*duration_sec/60)`. `+996…` и `996…` — местные.
  - **day_spike:** суммы по дням непрерывно с 1-го числа месяца первой записи до дня последней записи (нулевые дни учитываются); окно — 7 предыдущих дней; `mean`, `pstdev` (ddof=0); первые 7 дней ряда не проверяются; `std = 0` и `x > mean` → `z = +inf`, `std = 0` иначе → `z = 0`; аномалия при `z > 3`; `datetime = D 00:00:00`, `type = "day_spike"`; сумма = `x − mean`.
- **«Возможно лишнее»** = сумма аномалий без `day_spike`; одна строка CSV учитывается один раз (если попала в два правила — большая сумма). `day_spike` показывается отдельно: «необычный день».
- **Репутация номеров и любые «наблюдения» никогда не попадают в `anomalies.json`** — жюри считает их ложными срабатываниями (допустимо ≤ 2).
- Оператор — учебный **INAI Mobile**. Никаких реальных брендов, «юридических» ссылок на законы, выдуманных номеров транзакций, USSD-кодов или сумм экономии. Симуляции подписаны «демо».
- HTML — самодостаточный: без `<script src=…>`, работает офлайн; данные встроены JSON (экранировать `</` как `<\/`).
- Кыргызский текст — только из `faq.json` и подписи, проверенные носителем языка в команде.

## Review Focus

1. **CRLF и BOM в скрытом файле** — результат как у LF без BOM → `test_crlf_and_bom` (Task 1).
2. **Одно списание в двух форматах** (`12.09.2026 16:55:01 … 6.00` и `2026-09-12 16:55:54 … 6,00`) — дубль; цепочка из трёх за 60 с — 2 аномалии → `test_duplicate_across_formats`, `test_duplicate_chain_of_three` (Task 3).
3. **Номер `996…` без плюса** — местный → `test_local_number_without_plus` (Task 3).
4. **Загрузка в веб-демо не того файла** (картинка, пустой файл, без заголовка) — понятное сообщение и код 400, а не падение сервера → `test_upload_bad_file` (Task 11).
5. **Двойной счёт переплаты** — `day_spike` и строка в двух правилах не складываются → `test_overpay_no_double_count` (Task 6).

---

## Ядро ТЗ (баллы за автопроверку и обязательные пункты)

### Task 1: Каркас и разбор грязного CSV

**Files:**
- Create: `billcheck/__init__.py`, `billcheck/money.py`, `billcheck/parse.py`, `tests/conftest.py`, `tests/test_parse.py`
- Create: `requirements.txt` (`pytest>=7.0`), `pyproject.toml` (pytest: `pythonpath = ["."]`, `testpaths = ["tests"]`), `.gitignore` (`.venv/`, `out/`, `__pycache__/`, `.pytest_cache/`), `.gitattributes` (`*.sh text eol=lf`, `*.bat text eol=crlf`)
- Copy: `04_billing/*` → `data/`; `05_support/faq.json` → `data/faq.json`
- Copy & adapt: `run.bat`, `run.sh` из `inai-coverage-map` (вызывают `analyze.py`)

**Interfaces:**
- Produces (`money.py`): `parse_amount(text: str) -> Decimal | None` (`"1,20"` → `Decimal("1.20")`; `None` для пустого, нечислового, `NaN`, `Infinity`, отрицательного); `money(x: Decimal) -> float` (`ROUND_HALF_UP`, 0.01).
- Produces (`parse.py`):
  - `TYPES = ("call", "sms", "data", "subscription", "content")`
  - `@dataclass(frozen=True) class Charge: line: int; dt: datetime; type: str; number: str; duration_sec: Decimal; mb: Decimal; cost: Decimal`
  - `@dataclass(frozen=True) class Dropped: line: int; reason: str; raw: str`
  - `read_billing(path: str | Path) -> tuple[list[Charge], list[Dropped]]` (`line` — номер физической строки, заголовок = 1)
  - `class BillingFileError(Exception)` — нет файла, пустой файл, нет нужных колонок в заголовке.

- [ ] **Step 1:** `git init -b main`, структура, копия данных, `.venv` с pytest.
- [ ] **Step 2: Падающие тесты**

```python
@pytest.mark.parametrize("name, valid, dropped", [
    ("billing_01", 338, 7), ("billing_02", 480, 9), ("billing_03", 596, 8),
    ("billing_04", 668, 13), ("billing_05", 775, 6)])
def test_open_files_counts(data_dir, name, valid, dropped):
    charges, bad = read_billing(data_dir / f"{name}.csv")
    assert (len(charges), len(bad)) == (valid, dropped)

def test_each_broken_kind(tmp_path):
    rows = ["", "2026-09-12 14:00:00,call", "2026-09-10 10:00:00,unknown,,0,0,1",
            "2026/09/12 14:00:00,call,+996700123456,60,0,1.2", "2026-09-31 10:00:00,call,+996555100000,60,0,1",
            "11.09.2026 12:00:00,sms,+996700123456,0,0,Infinity", "2026-09-10 10:00:00,data,,0,NaN,1",
            "2026-09-10 10:00:00,data,,0,20,broken", "2026-09-10 10:00:00,call,+996555100000,-1,0,1",
            '01.09.2026 13:03:21,call,+996700188574,43,0,"1,20"']
    charges, bad = read_billing(write_csv(tmp_path, rows))
    assert [b.reason for b in bad] == ["empty_line", "column_count", "unknown_type", "bad_datetime",
        "bad_datetime", "bad_number", "bad_number", "bad_number", "bad_number"]
    assert charges[0].cost == Decimal("1.20") and charges[0].dt == datetime(2026, 9, 1, 13, 3, 21)

def test_crlf_and_bom(tmp_path): ...       # тот же набор с \r\n и BOM → те же причины и списания
def test_missing_or_headerless(tmp_path): ...  # BillingFileError
```

`conftest.py`: фикстура `data_dir` и `write_csv(tmp_path, rows, newline="\n", bom=False)` (пишет заголовок).

- [ ] **Step 3:** `pytest tests/test_parse.py` → FAIL.
- [ ] **Step 4:** Реализовать. Файл открывать `encoding="utf-8-sig", newline=""`, `csv.reader`, номер строки — `reader.line_num`, `[]` → `empty_line`.
- [ ] **Step 5:** `pytest` → PASS.
- [ ] **Step 6: Commit** `feat: разбор грязной детализации со счётчиком отброшенных строк`

### Task 2: Суммы по категориям, дням и топ-5

**Files:** Create `billcheck/report.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: `Charge`, `money`, `TYPES`.
- Produces:
  - `daily_totals(charges) -> dict[date, Decimal]` — непрерывный ряд с 1-го числа месяца первой записи до дня последней записи (его же использует `day_spike`).
  - `normalize_number(number: str) -> str` — `996XXXXXXXXX` → `+996XXXXXXXXX`, остальное без изменений.
  - `summarize(charges, dropped_count: int) -> dict` — `valid_rows, dropped_rows, total_som, by_category, by_day ("YYYY-MM-DD"), top5_numbers ([{"number", "cost_som"}], непустые номера, сумма убыв., затем номер)`.

- [ ] **Step 1: Падающие тесты**

```python
@pytest.mark.parametrize("n", range(1, 6))
def test_summary_matches_expected(data_dir, n):
    charges, bad = read_billing(data_dir / f"billing_0{n}.csv")
    expected = json.loads((data_dir / f"billing_0{n}_expected.json").read_text(encoding="utf-8"))
    expected.pop("anomalies")
    assert summarize(charges, len(bad)) == expected

def test_zero_days_and_all_categories(): ...   # списания 1 и 3 сентября → "2026-09-02": 0.0; все 5 категорий
def test_duplicates_are_not_removed(): ...     # две одинаковые записи → total = 2 × cost
```

- [ ] **Step 2:** FAIL. **Step 3:** реализовать. **Step 4:** PASS (контроль: billing_01 `total_som` 1230.16; billing_05 топ-1 `+996220863991` 577.0).
- [ ] **Step 5: Commit** `feat: суммы по категориям, дням и топ-5 номеров`

### Task 3: Четыре правила по отдельным списаниям

**Files:** Create `billcheck/anomalies.py`, `tests/test_anomalies.py`

**Interfaces:**
- Consumes: `Charge`, `money`.
- Produces:
  - `@dataclass(frozen=True) class Anomaly: dt: datetime; type: str; anomaly_type: str; amount: Decimal; reason: str; line: int | None; charge: Charge | None` + `as_dict() -> dict` (5 полей эталона).
  - `REASONS: dict[str, str]` (тексты из Global Constraints).
  - `find_night_charges`, `find_new_subscription`, `find_duplicates`, `find_international` — все `(charges: list[Charge]) -> list[Anomaly]`.

- [ ] **Step 1: Падающие тесты** (хелпер `ch(dt, type, number, dur, mb, cost, line=0)`)

```python
def test_night_boundaries():
    found = find_night_charges([ch("2026-09-05 00:00:00", "content", "1414", 0, 0, "10"),
                                ch("2026-09-05 05:59:59", "sms", "8899", 0, 0, "15"),
                                ch("2026-09-05 06:00:00", "sms", "8899", 0, 0, "15"),
                                ch("2026-09-05 03:00:00", "call", "+996700000000", 60, 0, "2")])
    assert [a.amount for a in found] == [Decimal("10"), Decimal("15")]

def test_only_first_subscription_in_file(): ...   # 53530 на строках 263 (23.09) и 334 (30.09) → одна, 23.09, 8.0
def test_subscription_number_length(): ...       # "53530" да; "12", "1234567", "+53530" нет
def test_duplicate_across_formats(): ...         # 16:55:01 "6.00" и 16:55:54 "6,00" → флаг на 16:55:54, 6.0
def test_duplicate_chain_of_three(): ...         # t, t+30, t+60 → 2 аномалии; t, t+61 → 0
def test_international_rate(): ...               # +971007731297, 99 с, 66 → 33.00; +1914035016, 115 с, 47.92 → 9.59
def test_local_number_without_plus(): ...        # "996700000000", 60 с, 50 сом → нет
def test_international_zero_duration(): ...      # duration 0 → нет
```

- [ ] **Step 2:** FAIL. **Step 3:** реализовать (дубли: сортировка по `(dt, line)`, окно 60 с, ключ `(type, number, duration_sec, mb, cost)`). **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat: ночные списания, подписки, дубли, дорогие международные звонки`

### Task 4: Всплеск за день и полный список аномалий

**Files:** Modify `billcheck/anomalies.py`, `tests/test_anomalies.py`

**Interfaces:**
- Consumes: `daily_totals`.
- Produces: `find_day_spikes(charges) -> list[Anomaly]` (`line=None`, `charge=None`); `find_all(charges) -> list[Anomaly]` (5 правил, сортировка `(dt, anomaly_type)`).

- [ ] **Step 1: Падающие тесты**

```python
def test_first_seven_days_not_checked(): ...  # всплеск 1–7 сентября → нет; тот же 8-го → есть
def test_zero_days_count_in_window(): ...     # одна запись 08.09 на 5 сом → ряд 1–8 сент., std=0, рост → аномалия 5.00
def test_flat_days_no_spike(): ...            # 8 дней по 10 сом → нет
def test_population_std(): ...                # окно [10,12,10,12,10,12,10], x=20 → аномалия 9.14

@pytest.mark.parametrize("n", range(1, 6))
def test_all_anomalies_match_expected(data_dir, n):
    charges, _ = read_billing(data_dir / f"billing_0{n}.csv")
    expected = json.loads((data_dir / f"billing_0{n}_expected.json").read_text(encoding="utf-8"))["anomalies"]
    assert [a.as_dict() for a in find_all(charges)] == expected
```

- [ ] **Step 2:** FAIL. **Step 3:** реализовать (`statistics.mean`/`pstdev`, сумма — `Decimal`). **Step 4:** PASS (контроль: billing_01 → `2026-09-25 00:00:00`, 290.97; всего 20 аномалий).
- [ ] **Step 5: Commit** `feat: всплеск расходов за день, полный список аномалий`

### Task 5: `analyze()`, CLI, файлы для жюри, `check.py`

**Files:** Create `billcheck/pipeline.py`, `analyze.py`, `check.py`, `tests/test_pipeline.py`, `tests/test_check.py`

**Interfaces:**
- Produces:
  - `@dataclass class Result: source: Path; charges: list[Charge]; dropped: list[Dropped]; anomalies: list[Anomaly]; report: dict`
  - `analyze(path: str | Path) -> Result` — `report = summarize(...) | {"anomalies": [a.as_dict() …]}`.
  - `write_outputs(result: Result, out_dir: Path) -> dict[str, Path]` — `report.json`, `anomalies.json`, `dropped_rows.csv` (`line,reason,raw`, `utf-8-sig`).
  - CLI `python analyze.py [FILE …] [--out out] [--open] [--llm] [--serve] [--port 8000]`: один файл → всё в `--out`; несколько → `--out/<имя>/` + `index.html`; без файлов → все `data/billing_*.csv`. Коды: 0 успех, 2 нет файла/заголовка, 3 нет зависимостей. Сводка в консоль (UTF-8).
  - `check.py`: `compare(found: list[dict], expected: list[dict]) -> dict` → `{"found", "missed", "false_positives", "recall", "passed"}`, совпадение по `(datetime, anomaly_type)`, зачёт — `recall >= 0.8` и `len(false_positives) <= 2`. CLI `python check.py out/anomalies.json data/billing_01_expected.json` (принимает список или объект с `anomalies`), печатает ЗАЧЁТ/НЕЗАЧЁТ и сверку полей отчёта, если рядом `report.json`.

- [ ] **Step 1: Падающие тесты**

```python
@pytest.mark.parametrize("n", range(1, 6))
def test_report_equals_expected(data_dir, n):
    assert analyze(data_dir / f"billing_0{n}.csv").report == json.loads(
        (data_dir / f"billing_0{n}_expected.json").read_text(encoding="utf-8"))

def test_cli_single_file_outputs(data_dir, tmp_path): ...   # 0; report.json, anomalies.json, dropped_rows.csv (7 строк данных)
def test_cli_many_files(data_dir, tmp_path): ...            # 2 файла → out/billing_01/, out/billing_02/, out/index.html
def test_header_only_file(tmp_path): ...                    # 0; valid_rows 0, total 0.0, anomalies []
def test_missing_file_exit_code(tmp_path): ...              # 2
def test_check_rules(): ...                                  # 4/5 + 2 лишних → passed; 3/5 → нет; 3 лишних → нет
```

- [ ] **Step 2:** FAIL. **Step 3:** реализовать. **Step 4:** PASS; `python analyze.py data/billing_03.csv` → `python check.py out/anomalies.json data/billing_03_expected.json` → «ЗАЧЁТ, 5 из 5, ложных 0».
- [ ] **Step 5: Commit** `feat: analyze(), CLI, файлы для жюри, check.py`

> **Контрольная точка «обязательная часть готова»** — здесь же первый push (после согласия пользователя на создание репозитория).

---

## Продукт (баллы за демо и бонусы)

### Task 6: Пояснения, советы RU/KY, «возможно лишнее», заявление на возврат

**Files:** Create `billcheck/explain.py`, `billcheck/claim.py`, `tests/test_explain.py`, `tests/test_claim.py`; Modify `billcheck/pipeline.py` (поля `explanation_ru`, `advice_ru`, `advice_ky` в `anomalies.json`)

**Interfaces:**
- Produces:
  - `explain(a: Anomaly) -> str` — шаблоны:
    - night_charge: `«{дд.мм} в {чч:мм} списано {сумма} сом за платное {SMS|контент} с номера {номер}. Ночные платные списания часто приходят от подписок, на которые вы не соглашались.»`
    - new_subscription: `«{дд.мм} подключена подписка на короткий номер {номер}: {сумма} сом. Если вы её не оформляли — её можно отключить и попросить вернуть деньги.»`
    - duplicate_charge: `«{дд.мм} в {чч:мм:сс} одно и то же списание ({тип} на {номер}, {сумма} сом) прошло дважды с разницей {N} с.»`
    - international_rate: `«Звонок на {номер} ({мин} мин) стоил {цена} сом/мин — дороже 20 сом/мин. Переплата — {сумма} сом.»`
    - day_spike: `«{дд.мм} вы потратили {x} сом — в {k} раза больше обычного ({mean} сом в день за предыдущую неделю).»`
  - `advice(a: Anomaly, lang: str = "ru") -> str` — night/new_subscription → FAQ 8; duplicate/international → FAQ 14; day_spike → FAQ 15 (`answer_{lang}`).
  - `possible_overpay(anomalies) -> Decimal` (правило из Global Constraints).
  - `build_claim(result: Result, selected_lines: set[int] | None = None, msisdn: str | None = None, full_name: str | None = None) -> str` — заявление в INAI Mobile: шапка (пустые поля `________`), «Прошу провести проверку и перерасчёт по следующим списаниям:», нумерованный список (дата и время, тип, номер, сумма, строка детализации, причина), «Итого к проверке: {сумма} сом», дата составления. Без `day_spike`.

- [ ] **Step 1: Падающие тесты**

```python
def test_explain_has_numbers(): ...           # +971, 66 сом, 99 с → "40.00 сом/мин" и "33.00 сом"
def test_advice_from_faq_ru_ky(data_dir): ... # advice(night, "ky") == faq[id 8]["answer_ky"]
def test_overpay_no_double_count(): ...       # night 15 + day_spike 290.97 + строка в двух правилах (10 и 12) → 27.00
def test_claim_billing_03(data_dir): ...      # 4 позиции, "Итого к проверке: 65.00 сом", "INAI Mobile", нет "z-score"
def test_claim_selected_lines(data_dir): ...  # только строка с 62626 → "Итого к проверке: 10.00 сом"
```

- [ ] **Step 2:** FAIL. **Step 3:** реализовать. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat: пояснения, советы RU/KY, заявление на перерасчёт`

### Task 7: Семья: профили и репутация коротких номеров

**Files:** Create `billcheck/family.py`, `data/family.json`, `tests/test_family.py`

**Interfaces:**
- Consumes: `Result`, `possible_overpay`.
- Produces:
  - `data/family.json`: `{"billing_01.csv": "Я", "billing_02.csv": "Папа", "billing_03.csv": "Бабушка", "billing_04.csv": "Мама", "billing_05.csv": "Брат"}` — только подписи, без телефонных номеров.
  - `load_profiles(data_dir: Path) -> dict[str, str]` (файл → подпись; нет файла — имя файла).
  - `number_reputation(results: list[Result]) -> list[dict]` — по коротким номерам (без `+`, не `996…`): `{"number", "members": int, "members_total": int, "charges": int, "total_som": float, "types": list[str], "night": int}`, сортировка по `members` убыв., затем `total_som` убыв.
  - `family_summary(results, profiles) -> list[dict]` — на профиль: `{"name", "file", "total_som", "overpay_som", "anomalies", "new_subscription": bool}`.
  - `self_check(results, data_dir) -> dict | None` — если рядом `*_expected.json`: `{"files": 5, "reports_equal": 5, "anomalies_expected": 20, "found": 20, "false_positives": 0}`, иначе `None`.

- [ ] **Step 1: Падающие тесты**

```python
def test_7575_everywhere(data_dir):
    rep = number_reputation([analyze(p) for p in sorted(data_dir.glob("billing_0*.csv"))])
    top = rep[0]
    assert (top["number"], top["members"], top["charges"], top["total_som"]) == ("7575", 5, 7, 85.0)

def test_reputation_not_in_anomalies(data_dir): ...  # ни одна аномалия billing_0N не про 7575 днём
def test_self_check_open_data(data_dir): ...         # {"files": 5, "reports_equal": 5, "anomalies_expected": 20, "found": 20, "false_positives": 0}
def test_family_summary(data_dir): ...               # "Бабушка": overpay 65.0, anomalies 5, new_subscription True
```

- [ ] **Step 2:** FAIL. **Step 3:** реализовать. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat: семейный взгляд, репутация коротких номеров, самопроверка`

### Task 8: HTML-отчёт «чек» (главный экран демо)

**Files:** Create `billcheck/templates/report.html`, `billcheck/html.py`, `tests/test_html.py`; Modify `billcheck/pipeline.py` (`report.html` в `write_outputs`)

Перед вёрсткой загрузить skill `frontend-design`. Направление: **бумажный кассовый чек** на спокойном фоне — моноширинные суммы, зубчатый край, спорные строки помечены красным косым штампом «ПРОВЕРИТЬ». Один акцентный цвет для действия «вернуть». Не повторять палитру ТЗ 7.

**Interfaces:**
- Consumes: `Result`, `explain`, `advice`, `possible_overpay`, `build_claim`.
- Produces: `render_report(result: Result, profile: str | None = None) -> str` (JSON в `__BILL_DATA__`).

Блоки по порядку:
1. Шапка: профиль («Бабушка»), месяц, **потрачено**, **возможно лишнее**, число находок; кнопка **«Подготовить возврат N сом»**.
2. «Чек»: списания сгруппированы по дням, спорные — со штампом; клик по строке раскрывает исходную строку детализации и её номер.
3. **График трат по дням** (SVG из данных) с отмеченными аномалиями — бонус ТЗ; день `day_spike` выделен, подпись «в k раз больше обычного».
4. Категории (5 полос) и топ-5 номеров.
5. Карточки аномалий: заголовок, `explain`, сумма, совет с переключателем **RU / KY**, чекбокс «в заявление».
6. Панель заявления: поля «номер», «ФИО», живой текст `build_claim` по отмеченным чекбоксам (дублировать логику суммы в JS по тем же правилам; сумма в шапке и в тексте совпадают), кнопки «Скопировать», «Скачать .txt», «Печать / PDF».
7. **Чек-лист ТЗ 4** (свернуть/развернуть): 4 обязательных блока + 5 правил + бонусы, у каждого живая цифра.
8. «Качество данных»: отброшено N строк — номер строки, причина, исходный текст.
9. Переключатель **«Крупный шрифт»** (для пожилых), мобильная ширина, видимый фокус, `prefers-reduced-motion`.

- [ ] **Step 1: Падающие тесты**

```python
def test_report_html_self_contained(data_dir): ...  # нет "<script src", нет "__BILL_DATA__", есть все 5 datetime аномалий billing_03, есть "65.00"
def test_report_html_escapes_script(tmp_path): ...  # номер "</script>" в CSV не ломает страницу (в HTML нет сырого "</script>" внутри данных)
```

- [ ] **Step 2:** FAIL. **Step 3:** реализовать. **Step 4:** PASS; открыть `out/billing_03/report.html` в браузере (1440 и 375 px): чекбоксы меняют сумму, RU/KY переключается, «Скачать .txt» работает, консоль без ошибок.
- [ ] **Step 5: Commit** `feat: HTML-отчёт «чек», график, карточки, заявление`

### Task 9: Семейный экран

**Files:** Create `billcheck/templates/family.html`, `tests/test_family_html.py`; Modify `billcheck/html.py` (`render_family`), `analyze.py` (при нескольких файлах пишет `index.html` = семейный экран)

**Interfaces:**
- Consumes: `family_summary`, `number_reputation`, `self_check`, ссылки на отчёты.
- Produces: `render_family(results, profiles, links: list[str], data_dir: Path) -> str`.

Блоки:
1. Карточки профилей: имя, потрачено, возможно лишнее, флажок **«Новая подписка!»**; клик → отчёт профиля.
2. **«Номера, которые списывают у всей семьи»** — репутация: `7575 — у 5 из 5, 7 списаний, 85 сом, днём, контент`; подпись: «Ни одно из пяти правил ТЗ этого не видит: списания дневные и не повторяются в пределах минуты».
3. Итоги семьи: 8 285,42 сом, 20 находок, 204,26 сом спорных.
4. Бейдж самопроверки (если `self_check` не `None`): «Открытые данные организаторов: 5/5 отчётов совпали, 20/20 аномалий, 0 ложных».
5. Подпись про будущее (текстом, без имитации): «В продукте — еженедельная проверка и уведомление в Telegram».

- [ ] **Step 1: Тесты:** `test_family_page_has_profiles_and_reputation` (5 подписей из `family.json`, «7575», «5 из 5», «204.26»), `test_self_check_badge_hidden_without_expected` (без `*_expected.json` бейджа нет).
- [ ] **Step 2–4:** FAIL → реализовать → PASS; проверка в браузере.
- [ ] **Step 5: Commit** `feat: семейный экран с репутацией номеров и самопроверкой`

### Task 10: Окно телефона — симуляция отключения (связь с ТЗ 3)

**Files:** Modify `billcheck/templates/report.html`; Create `tests/test_phone.py`

Компонент на чистом JS/CSS внутри `report.html`. Открывается кнопкой **«Отключить подписки»** на карточках `new_subscription` / `night_charge`.

- Экран телефона «INAI Mobile» с плашкой **«Демо: так это могло бы выглядеть»**.
- Анимированный сценарий (пропускается при `prefers-reduced-motion`): меню «1 — Мои подписки» → список коротких номеров **этого абонента из данных** с суммами → «2 — Отключить все» → «3 — Запрет платного контента» → «Подтвердить: 1» → «Готово».
- Под телефоном честный совет из FAQ id 8: «Откройте раздел «Подписки» в личном кабинете…» (RU/KY).
- Не показывать никаких USSD-кодов: у учебного оператора кода отключения нет.

- [ ] **Step 1: Тест:** `test_phone_lists_this_subscriber_numbers` — в данных телефона billing_03 есть «53530» и «62626», нет «7799»; на странице есть «Демо».
- [ ] **Step 2–4:** FAIL → реализовать → PASS; проверка в браузере.
- [ ] **Step 5: Commit** `feat: симуляция отключения подписок в окне телефона`

### Task 11: Веб-демо: загрузка файла перетаскиванием

**Files:** Create `billcheck/server.py`, `billcheck/templates/upload.html`, `tests/test_server.py`; Modify `analyze.py` (`--serve`, `--port`)

**Interfaces:**
- Produces: `make_server(data_dir: Path, port: int = 8000) -> ThreadingHTTPServer` (только `127.0.0.1`). Маршруты:
  - `GET /` — страница: зона «перетащите детализацию», кнопки профилей семьи, ссылка «Семья».
  - `POST /api/analyze` — тело: текст CSV, заголовок `X-Filename`; ответ — HTML отчёта. Лимит 5 МБ. Ошибка разбора / без заголовка / не текст → **400** с понятным сообщением.
  - `GET /profile/<file>` — отчёт по файлу из `data/`; `GET /family` — семейный экран.
- Разбор загрузки — через временный файл и тот же `analyze()` (одна логика для CLI и сервера).

- [ ] **Step 1: Тесты** (сервер в потоке на свободном порту, запросы через `urllib`):

```python
def test_upload_billing_03(server, data_dir): ...  # 200, в HTML "65.00" и "62626"
def test_upload_bad_file(server): ...              # b"\x89PNG..." и пустое тело → 400, текст ошибки, сервер жив
def test_profile_and_family(server): ...           # /profile/billing_03.csv и /family → 200
def test_unknown_profile(server): ...              # /profile/../../etc → 404
```

- [ ] **Step 2–4:** FAIL → реализовать → PASS; `run.bat --serve` → открыть `http://127.0.0.1:8000`, перетащить `billing_03.csv`.
- [ ] **Step 5: Commit** `feat: веб-демо с загрузкой детализации`

### Task 12 (бонус): резюме через ИИ

**Files:** Create `billcheck/llm.py`, `tests/test_llm.py`, `requirements-llm.txt` (`anthropic`); Modify `analyze.py` (`--llm`), `billcheck/html.py`

Перед кодом загрузить skill `claude-api` (модель и вызов SDK — оттуда).

**Interfaces:** `llm_summary(result: Result, client=None) -> str | None` — короткое письмо абоненту по готовым числам (числа передаются в промпт; инструкция не придумывать суммы и номера). Нет `ANTHROPIC_API_KEY` / пакета / сети → `None`, отчёт с шаблонами; в отчёте подпись «Текст подготовлен ИИ по посчитанным числам».

- [ ] **Step 1: Тесты:** `test_no_key_returns_none`, `test_uses_given_client` (фейковый клиент → текст в `report.html`), `test_numbers_in_prompt` (фейковый клиент получает «65.00»).
- [ ] **Step 2–4:** FAIL → реализовать → PASS.
- [ ] **Step 5: Commit** `feat: опциональное резюме через ИИ с откатом на шаблоны`

### Task 13 (только если к 05:00 всё готово): подсказка по тарифу из ТЗ 2

**Files:** Create `billcheck/tariff_hint.py`, `data/tariffs.json` (копия из `02_tariffs`), `tests/test_tariff_hint.py`

**Interfaces:** `tariff_hint(charges, tariffs: list[dict]) -> dict | None` — минуты (каждый звонок `ceil(sec/60)`), SMS, ГБ (`mb/1024`) за месяц детализации → стоимость месяца на каждом тарифе (абонплата + перерасход сверх пакета), без ночного безлимита и роуминга. Показывать: «Этот месяц на тарифе {name} стоил бы {X} сом вместо {total}» — только если выгода > 50 сом, иначе `None`. Подпись: «Оценка по одному месяцу, без роуминга и ночного интернета».

- [ ] **Step 1: Тесты:** ручной расчёт на 3 синтетических списаниях для одного тарифа; `None`, когда выгоды нет.
- [ ] **Step 2–5:** FAIL → реализовать → PASS → Commit `feat: подсказка по тарифу (оценка)`

### Task 14: README, объяснение, сценарий демо, проверка с нуля

**Files:** Create `README.md`, `docs/how-it-works.md`, `docs/demo.md`

- [ ] **Step 1: README:** запуск для жюри (`run.bat data/billing_01.csv` → `out/anomalies.json`), `check.py`, таблица «пункт ТЗ → где увидеть → код → тест», правила из уточнений, продукт в 5 строк, `--serve`, инструкция для разработчика, «Что не успели».
- [ ] **Step 2: `docs/how-it-works.md`:** конвейер (mermaid), каждое правило с примером из открытых данных, ответы на вопросы жюри (раздел ниже).
- [ ] **Step 3: `docs/demo.md`:** сценарий и вопросы (разделы ниже) с итоговыми цифрами из `self_check` и `family_summary`.
- [ ] **Step 4: Проверка с нуля:** копия без `.venv` → `run.bat` (все 5 файлов + семья) → `check.py` по каждому → ЗАЧЁТ; `run.bat --serve` → загрузка; `pytest` → зелёный; карта открывается без интернета.
- [ ] **Step 5: Commit** `docs: README, объяснение, сценарий демо` → push (с согласия пользователя).

---

## Сценарий демо (3:00)

Экран заранее: `run.bat --serve`, вкладка `http://127.0.0.1:8000`, крупный масштаб браузера.

| Время | На экране | Говорим |
|---|---|---|
| 0:00–0:20 | Главная | «Наша бабушка звонит только детям, а счёт за сентябрь — 2 106 сом. Детализация — 600 строк в двух форматах. Кто из вас читал свою?» |
| 0:20–0:45 | Перетаскиваем `billing_03.csv` | «Секунда — и чек: потрачено 2 106, **возможно лишнее 65 сом**». Показываем штампы «ПРОВЕРИТЬ». |
| 0:45–1:15 | Карточки | «Ночью в 01:37 платное SMS на 62626. Звонок в ОАЭ по 40 сом/мин — переплата 41 сом. Одно списание прошло дважды за 53 секунды. И подписка на 53530, которую никто не оформлял». График: красный день 29 сентября. |
| 1:15–1:40 | «Подготовить возврат 65 сом» | Живой текст заявления, «Печать / PDF». «Готовое заявление — со строками детализации, без единой выдуманной цифры». |
| 1:40–2:00 | «Отключить подписки» → телефон | «Так это могло бы работать у оператора — пока это демо; сегодня совет из FAQ оператора, на русском и кыргызском» (переключить KY). |
| 2:00–2:35 | «Семья» | «А теперь главное. Номер **7575** списывает деньги у **всех пятерых** — 85 сом. Днём, по чуть-чуть. Ни одно правило из ТЗ этого не видит — видно только, когда смотришь на семью целиком». |
| 2:35–3:00 | Бейдж самопроверки | «Ядро — строго по ТЗ: на открытых данных организаторов 5 из 5 отчётов и 20 из 20 аномалий совпали, 0 ложных. 60 тестов, запуск одной командой. Мы — „Где мои деньги?“: проверяем счёт родителей раз в неделю». |

**Запасной план:** записанное заранее видео демо (экранная запись) и скриншоты в `docs/demo/`; всё работает без интернета.

## Вопросы жюри — готовые ответы

1. **Почему `Decimal`, а не `float`?** 0.1 + 0.2 ≠ 0.3 во `float`; в деньгах копейки складываются из сотен строк — ошибка в 0.01 сорвёт сверку.
2. **Почему z-score по 7 предыдущим дням?** Так в уточнениях; окно только назад — нельзя знать будущее в момент списания; нулевые дни считаются, иначе «тихая» неделя завышала бы среднее.
3. **Почему при `std = 0` бесконечность?** Неделя одинаковых трат и вдруг рост — это и есть всплеск; деление на ноль явно обработано.
4. **Почему дубли не удаляются из отчёта?** Это два реальных списания: деньги ушли дважды — поэтому мы и просим их вернуть.
5. **Почему `day_spike` не входит в «возможно лишнее»?** Всплеск часто состоит из тех же спорных списаний — сложение посчитало бы деньги дважды (правило из уточнений).
6. **Как вы находите 7575, если это не аномалия?** Отдельный семейный анализ коротких номеров; в `anomalies.json` он не попадает, чтобы не давать ложных срабатываний автопроверке.
7. **Деньги правда возвращаются?** Нет — мы готовим заявление с точными строками детализации; решение за оператором. Телефон — помеченная симуляция.
8. **Что если в файле неизвестный мусор?** Каждая строка проверяется по 5 причинам, неподходящая уходит в `dropped_rows.csv` с номером строки и причиной; программа не падает (тесты на CRLF, BOM, пустой файл, картинку).
9. **Как масштабировать на оператора?** Разбор потоковый и линейный; правила независимы; репутация номеров по всем абонентам — готовый сигнал для антифрода оператора.
10. **Что делал ИИ, а что вы?** Каждый в команде объясняет свой модуль: `parse` — …, `anomalies` — …, `family` — …, интерфейс — … (распределить заранее, прогнать ответы вслух).

## Время и роли (ночь 20 → 21 ноября)

| Время | Задачи | Контрольная точка |
|---|---|---|
| старт + 1,5 ч | 1–2 | отчёт = 5 эталонов |
| + 2 ч | 3–5 | **20/20 аномалий, `check.py` ЗАЧЁТ, первый push** |
| + 1 ч | 6–7 | заявление, семья, 7575 |
| + 2 ч | 8–9 | главный экран и семейный экран |
| + 1 ч | 10–11 | телефон и загрузка файла |
| + 0,5 ч | 12 | ИИ-бонус (если есть ключ) |
| 05:00 | 13 | только если всё выше готово |
| **06:00** | **заморозка функций** | дальше — только исправления |
| 06:00–07:00 | 14 | README, проверка с нуля, push |
| 07:00–08:30 | — | 3 прогона демо с таймером, ответы на вопросы вслух, запись видео-запаски |
| **08:45** | — | последний push |

Роли команды: код ведётся здесь; люди — (1) проверяют интерфейс глазами пожилого пользователя и кыргызские подписи, (2) готовят и репетируют речь, (3) каждый разбирает один модуль для ответов на вопросы.
