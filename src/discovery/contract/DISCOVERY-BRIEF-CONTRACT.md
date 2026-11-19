# Discovery Brief — контракт выходного артефакта интервьюера (v1.4)

> Дата заморозки: 2026-07-14 (v1) · Правки v1.1: 2026-07-14 · Правки v1.2: 2026-11-14 · Правки v1.3: 2026-11-15 · Правки v1.4: 2026-11-19 · Статус: **Frozen (v1.4)** · Канон: этот файл
> (репо `discovery-toolkit`; черновик v0.1 остаётся в
> `_cowork_output/contracts/2026-07-13-discovery-brief-contract-v0.1.md` как история).
> Владелец: discovery-agent (авторит) · Потребитель: governance-слой (Gate BR/FRD/0b/0a)
> Совместим с: SpecMeta v1 (`spec-runner/src/spec_runner/spec.py`, `meta_from_dict`
> игнорирует unknown-keys) и C2-расширением (`owner_role`/`approver`, REQ-401/402 —
> до его лендинга эти два поля тоже едут unknown-keys, семантика не меняется).

## Решения, закрывшие v0.1 → v1

| Открытый пункт v0.1 | Решение v1 |
|---|---|
| Один brief vs два файла | **Один brief** на фрейм; секции Charter+Requirements внутри. Расщепление по владельцам — при открытии гейтов, не на discovery-стадии. (Решение Andrei, 2026-07-14.) |
| `spec_stage: discovery` | Зафиксировано как стадия **governance-профиля**. В spec-runner `SPEC_STAGES` НЕ добавляется. |
| Coverage-ключи engineer-фрейма | Определены (§4): `systems, interfaces, constraints, arch_preferences, risks, feasibility_review`. |
| `out_of_scope` в coverage | Добавлен required-ключом customer-фрейма (в v0.1 секция OUT была required, но ключа не было — рассинхрон закрыт). |
| Приватность `interview.sessions` | Нормативно: **роли, не имена** по умолчанию; имя — только с явного согласия участника. |
| Семантика счётчика `conflicts` | Уточнено: число `X-NN` со `status: open` (resolved остаются в теле для истории, счётчик — только открытые). |

## Изменения v1.1 (по итогам первых двух реальных прогонов и ревью Copilot)

- **GC-15**: `validation` обязан зеркалить фактический результат линтера (ловит
  протухшее `pending` при чистом брифе и лживое `pass` при ошибках).
- **GC-16**: путь-элементы `traces_to` обязаны разрешаться — относительно брифа или
  корня его git-репо (ловит ссылки, умершие при переносе брифа в целевой репо).
- **Формат §2**: жирный ID зарезервирован за определениями; ссылки на ID (включая
  upstream-требования в feasibility-секции engineer-брифа) — без болда, иначе линтер
  читает их как определения. Схема брифа не менялась — `schema_version` остаётся 1.

## Изменения v1.2 (перевод предпочтений в ограничения; issue #28 ← discovery#71)

Наблюдение — живой прогон DarkFactory (12–14.11): интервью требовало от стейкхолдера
язык ограничений (числа в Acceptance/NFR/M), а перевод с языка предпочтений никто не
делал. Позиция владельца: числа — это исследование, а не вопрос одному человеку.

- **Поле `**Preference**`** (опционально у `FR`/`NFR`/`M`): слова стейкхолдера дословно,
  без требования измеримости. `Acceptance`/`Target` — гипотеза-ограничение составителя,
  стейкхолдер подтверждает её смысл, а не формулирует.
- **Число как исследование:** значение, которого нет (порог, baseline, target), — открытый
  `Q-NN` (`owner_role: analyst|engineer`, `blocking: false`); требование ссылается на него
  («… не хуже значения из Q-NN»). GC-08 не меняется — гипотеза со ссылкой и есть Acceptance.
- **GC-17:** ссылка на `Q-NN` из `FR`/`NFR`/`M` обязана разрешаться в запись `Q` брифа
  (error); ссылка на закрытый `Q` — warning «подставьте значение».
- **Банк вопросов:** `- `-пункт темы — вопрос человеку; инструкция составителю — строка
  `> ` (SKILL.md, приложение). Схема брифа не менялась — `schema_version` остаётся 1.

## Изменения v1.3 (enterprise-фрейм заказчика; issue #30 ← devtools#764)

Контекст: у `dfl` появился личный путь со своим облегчённым брифом; discovery остаётся
путём **enterprise** — интервью с заказчиком, у которого есть спонсор, процесс и
compliance. В основу фрейма customer лёг опросник владельца для AI-продукта.

- **Банк customer** — девять блоков опросника (цель и контекст; делать; не делать;
  стоить; доказывать; данные и интеграции; качество и приёмка; эксплуатация; передача).
  Coverage-ключи и секции **не менялись**: каждый блок промаркирован существующим ключом
  (таблица Coverage в `frames/customer.md`).
- **Секция `## Translation table`** (customer, required): итог discovery — строка на
  каждое высказывание заказчика: слова → категория → ID ограничения → допущение,
  подтверждающий, срок (§2). Колонки «архитектурное решение» нет: запрет фрейма
  сохраняется, архитектурный вывод — `Q-NN` с `owner_role: architect`.
- **Критерии «Discovery завершён»** стали проверкой брифа там, где они механические:
  GC-18 (формат таблицы, допущения с подтверждающим и сроком), GC-19 (четыре
  обязательные категории), GC-20 (`**Category**` у каждой NFR; есть perf- и cost-цели — число с единицей или `Q-NN`), GC-21
  (владельцы процесса, данных, качества, эксплуатации — `owns:` у `P` или открытого `Q`).
  Семантические пункты (подтверждение compliance, письменное согласие заказчика,
  эталонный набор) — чек-лист фрейма, не линтер.
- Правила GC-18…GC-21 — только для customer; engineer-фрейм не менялся. Схема
  frontmatter не менялась — `schema_version` остаётся 1; customer-брифы v1.2 без
  translation table и `owns:` линтер v1.3 не пропустит.

## Изменения v1.4 (профиль feature; issue #35 ← discovery#86 ← devtools#816)

Наблюдение — живой прогон 19.11: фича «экспорт словаря в CSV для Anki» в существующем
небольшом репо, фрейм customer v1.3 задал 59 вопросов, по существу ответов 16. Блоки
4–8 (стоить, доказывать, данные, приёмка, эксплуатация) маленькой фиче в основном не
применимы, а GC-19/20/21 требуются независимо от размера темы.

- **`interview.profile: full | feature`** (необязательное; нет поля — `full`; `feature`
  — только у customer, GC-03). Профиль задаёт набор вопросов банка, не схему брифа.
- **Короткий набор и вопросы-фильтры** — машинная разметка банка
  (`<!-- profile: feature; short: …; filter: … -->` под маркером темы, SKILL.md,
  приложение). Состав набора и тексты фильтров — канон этого репо, рантайм их не
  сочиняет.
- **«Не применимо» — запись, не пустота.** Ответ «нет» на фильтр — слова заказчика:
  строка translation table и запись брифа. У `NFR`/`CON` в профиле feature допустима
  строка `**N/A**: «слова заказчика» — почему`; у `NFR` она заменяет `Acceptance`/`Target` (GC-08) и
  число perf/cost (GC-20). NFR категорий `perf`/`cost` по-прежнему обязательны.
- **GC-19 и GC-21 не ослаблены:** ответы на фильтры блоков 4 и 5 дают строки «стоить»
  и «доказывать»; вопросы о владельцах данных, качества и эксплуатации входят в
  короткий набор и задаются и при ответе «нет».
- **Coverage в профиле feature (§4):** чек-лист нераскрытой темы (без фильтра или с
  ответом «нет») сужается до её заданных вопросов; недостающее для проверки
  требования — открытый `Q-NN` (`blocking: false`), а не дозадавание банка.
- **GC-22:** `**N/A**` — только в профиле feature, только у `NFR`/`CON`, причина
  цитирует слова заказчика в «…». Схема frontmatter расширена аддитивно — `schema_version` остаётся 1;
  брифы v1.3 без `profile` читаются как `full` без изменений.

## TL;DR

1. **Не изобретаем парсер.** Frontmatter = ядро SpecMeta v1 как есть; discovery-специфика
   (`schema:`, `interview:`, `coverage:` и пр.) — unknown-keys, которые `meta_from_dict`
   игнорирует. Ноль правок в spec-runner, ноль второго state-движка.
2. **Один brief → несколько gated-артефактов.** customer-фрейм: Charter (Gate BR) +
   черновик Requirements (FRD). engineer-фрейм: System Assessment (0b) + вход в Tech
   Selection (0a). Расщепление по владельцам — при входе в governance.
3. **Тело — FRD-стиль spec-runner + ID-трассируемость** (`G/P/J/FR/NFR/CON/M/OUT/S/IF/AP/RK/Q/X`).
4. **Coverage-gate — машиночитаемый блок**, проверяется линтером `gate_check.py`
   (правила GC-01…GC-22, §5), не человеком на глаз.
5. **Конфликты и открытые вопросы — first-class**: `X-NN` и `Q-NN` обязательны; агент их
   поднимает, не усредняет.

---

## 1. Frontmatter

```yaml
---
# --- ядро SpecMeta v1 (as-is) + C2-расширение (owner_role/approver) ---
spec_stage: discovery            # стадия governance-профиля; в exec-профили spec-runner не входит
status: draft                    # draft | in_review | approved — ЗЕРКАЛО git (git primary)
version: 1
generated_by: discovery-agent@claude-fable-5    # agent-id автора (<harness>@<model>)
generated_at: 2026-07-14
source_prompt_version: sha256:<хеш frames/<frame>.md>   # версия банка вопросов фрейма
validation: pass                 # зеркало результата gate_check (GC-15): pass только при 0 ошибок
approved_by: null                # actor/agent-id, записавший аппрув
approved_at: null
owner_role: product              # CODEOWNERS-роль (customer → product, engineer → architect)
approver: null                   # git-handle ЧЕЛОВЕКА, подтвердившего PR-merge (C2 REQ-402)
# --- discovery-расширение (unknown-keys; читает discovery/gate-check) ---
schema: discovery-brief
schema_version: 1
feeds: [charter, requirements]   # customer → [charter, requirements]; engineer → [system-assessment, tech-selection]
interview:
  frame: customer                # customer | engineer
  profile: full                  # full | feature (v1.4; нет поля = full; feature — только customer)
  sessions:                      # provenance: РОЛИ, не имена (по умолчанию)
    - participant_role: product-owner
      date: 2026-07-14
      medium: sync               # sync | async | self (соло-режим)
coverage:                        # required-набор по фрейму, см. §4
  goals: covered                 # covered | partial | missing
  # ... остальные ключи фрейма
  gate_passed: false             # см. формулу §4; линтер сверяет с вычисленным
open_questions: 2                # число незакрытых Q-NN (без resolved)
blocking_open_questions: 1       # из них blocking: true; гейт не пройти, пока > 0
conflicts: 1                     # число X-NN со status: open
traces_to: []                    # upstream: KB prograph-vault, approved customer-brief (для engineer)
---
```

**Правило зеркала:** `status`/`approved_by`/`approver` — машинное отражение git-состояния
(git — источник истины). Линтер сверяет счётчики и `gate_passed` с телом (GC-10/GC-11).

---

## 2. Тело — секции, ID-конвенции и лintable-формат

| Префикс | Секция | Обяз. (customer) | Обяз. (engineer) | Трассировка |
|---|---|:---:|:---:|---|
| `G-NN` | Цели | ✅ | — | — |
| `P-NN` | Персоны / стейкхолдеры | ✅ | ○ | — |
| `J-NN` | Jobs-to-be-done | ✅ | — | → G |
| `FR-NN` | Функциональные требования (MoSCoW) | ✅ | — | → ≥1 G/J |
| `NFR-NN` | Нефункциональные (категория + измеримая цель: число или `Q-NN` исследования) | ✅ | ○ | → G/CON |
| `CON-NN` | Ограничения | ✅ | ✅ | — |
| `M-NN` | Success-метрики (измеримые: baseline → target, значение — число или `Q-NN` исследования) | ✅ | — | → ≥1 G |
| `OUT-NN` | Вне scope / non-goals | ✅ | ○ | — |
| `S-NN` | System Assessment (текущие системы/данные) | — | ✅ | — |
| `IF-NN` | Интерфейсы/контракты существующих систем | — | ✅ | → S |
| `AP-NN` | Архитектурные предпочтения/ограничения | — | ✅ | → S/CON |
| `RK-NN` | Риски (tacit-знание) | ○ | ✅ | — |
| `Q-NN` | Открытые вопросы | ✅ | ✅ | — |
| `X-NN` | Конфликты стейкхолдеров | ✅ | ✅ | — |

✅ required · ○ optional · — не для этого фрейма.

**Формат записи (нормативный — от него зависит линтер):**

- Запись = либо буллет `- **G-01** текст`, либо заголовок `#### FR-01: Название`.
  Метаданные записи — строки её блока (до следующей записи/заголовка).
- Жирный ID — **только для определений**. Ссылки на ID (в т.ч. на требования upstream-
  брифа в feasibility-секции engineer-фрейма) пишутся без болда: `FR-01`, не `**FR-01**`.
- Трассировка: `` `traces: [G-01, J-02]` `` — на строке заголовка записи или внутри блока.
- `FR`: строка `**Priority**: 🔴 Must | 🟠 Should | 🟡 Could | ⚪ Won't` и строка
  `**Acceptance**: …`. `NFR`: строка `**Acceptance**: …` или `**Target**: …`
  (Priority у NFR опционален); рекомендуется `**Category**: perf|safety|security|…`.
- `FR`/`NFR`/`M` (v1.2): опциональная строка `**Preference**: «…»` — слова стейкхолдера
  дословно; Acceptance/Target — перевод составителя. Значение, которого ещё нет,
  записывается ссылкой на открытый `Q-NN` исследования (без болда: «не хуже значения
  из Q-03»); такой `Q` — `owner_role: analyst|engineer`, `blocking: false`.
- `Q-NN`: `` `owner_role: <роль>` `` и `` `blocking: true|false` ``; закрытый вопрос
  помечается `` `resolved: true` `` (и не считается в счётчиках).
- `X-NN`: `` `status: open|resolved` ``; рекомендуется `` `target: FR-02` `` — на какое
  требование конфликт указывает (обязательно для feasibility-конфликтов engineer-фрейма).
- `NFR` (v1.3, customer — обязательно): `**Category**: perf|cost|safety|security|compliance|…`
  (несколько — через запятую). Цель категории
  `perf`/`cost` — число с единицей («p95 до 2 с», «500 запросов/день», «$300 в месяц»)
  либо ссылка на `Q-NN` исследования (GC-20). «Число с единицей» линтер проверяет
  эвристикой (число и следом слово или символ `₽ $ € £ % °`): «3 поставщиков» она
  пропустит, смысл единицы остаётся на ревью. В customer-брифе обязательна хотя бы одна
  `NFR` категории `perf` (латентность, объём) и одна категории `cost` (бюджет).
- `**N/A**: «слова заказчика» — почему` (v1.4, только профиль `feature`, только
  `NFR`/`CON`): блок отфильтрован ответом «нет» на вопрос-фильтр банка. Причина
  цитирует ответ заказчика в «…» (линтер проверяет непустую цитату; что она — ответ
  на фильтр, остаётся на ревью). У `NFR` строка заменяет `Acceptance`/`Target` и
  число perf/cost; запись при этом остаётся (категория обязательна, строка в
  translation table — тоже). Вне профиля `feature` — ошибка GC-22.
- Владельцы (v1.3, customer): `` `owns: process|data|quality|operations` `` (через
  запятую) у записи `P` — названный владелец; у открытого `Q` — владелец ещё не назван,
  вопрос открыт. Каждый из четырёх доменов закрыт хотя бы одной записью (GC-21).
- **Translation table** (v1.3, customer): секция `## Translation table` — markdown-таблица
  из шести колонок в этом порядке (заголовок — ровно эти названия, регистр не важен;
  линтер читает колонки по позиции):

  ```
  | Слова заказчика | Категория | Ограничение | Допущение | Подтверждает | Срок |
  |---|---|---|---|---|---|
  | «Должно работать мгновенно» | стоить | NFR-01 | «мгновенно» = p95 до 2 с | product-owner | 2026-12-01 |
  | «Он ничего не должен трогать» | не делать | NFR-02 | — | — | — |
  ```

  Слова — дословно, непусты. Категория ∈ {`делать`, `не делать`, `стоить`,
  `доказывать`, `данные`, `приёмка`, `эксплуатация`, `передача`}; первые четыре
  обязательны (≥1 строка каждой). Ограничение — ≥1 ID существующей записи
  `FR`/`NFR`/`CON`/`OUT` (без болда). Допущение — `—`, если ограничение следует из слов
  напрямую; иначе у него обязателен подтверждающий (роль) и срок `YYYY-MM-DD`.

---

## 3. Профили фреймов (данные, не код)

| | **customer** | **engineer** |
|---|---|---|
| Кого | заказчик / пользователь / product-owner | инженер / сотрудник, знающий текущие системы |
| Пространство | problem-space | solution-space |
| Банк вопросов | `frames/customer.md` | `frames/engineer.md` |
| Порождает | Charter (BR) + Requirements draft (FRD) | System Assessment (0b) + вход в Tech Selection (0a) |
| `feeds` | `[charter, requirements]` | `[system-assessment, tech-selection]` |
| Аппрувит (`owner_role`) | product | architect |
| Precondition | — | customer-brief со `status: approved` в `traces_to` |
| Анти-паттерн (запрет) | не спрашивать про архитектуру | не пересобирать цели — читать customer-brief |
| Итог discovery (v1.3) | `## Translation table` + владельцы `owns:` (GC-18…GC-21) | — |
| Профили интервью (v1.4) | `full` (по умолчанию) · `feature` — фича в существующем репо: короткий набор + вопросы-фильтры блоков 4–8, `**N/A**` (GC-22) | только `full` |

---

## 4. Coverage-gate

Required-набор ключей блока `coverage:` по фреймам:

| customer (required) | customer (optional) | engineer (required) |
|---|---|---|
| `goals` (G), `personas` (P), `jobs` (J), `functions` (FR), `nfr` (NFR), `constraints` (CON), `success_metrics` (M), `out_of_scope` (OUT) | `risks` (RK) | `systems` (S), `interfaces` (IF), `constraints` (CON), `arch_preferences` (AP), `risks` (RK), `feasibility_review` (проход по FR upstream-брифа) |

Формула (вычисляет линтер; значение в frontmatter обязано совпасть):

```
gate_passed = ( все required-ключи фрейма = covered, и их секции непусты )
            И ( каждое FR трассируется в существующий G/J )
            И ( blocking_open_questions == 0 )
```

- `covered` = секция есть, непуста и закрывает чек-лист темы; `partial` = есть, но чек-лист
  не закрыт; `missing` = нет.
- Профиль `feature` (v1.4): чек-лист нераскрытой темы — её заданные вопросы
  (`short:` и ответ на фильтр); недостающее — открытый `Q-NN` с `blocking: false`.
  Тема, раскрытая ответом «да», закрывается по полному чек-листу.
- Optional-ключи (`risks` у customer) со значением `partial`/`missing` гейт **не** валят.
- `Q` c `blocking: false` гейт не валят — это легитимный перенос в governance.
- `X` со `status: open` гейт сами по себе не валят, но feasibility-конфликт engineer-фрейма
  с `target:` на customer-brief инкрементирует `blocking_open_questions` **у customer-брифа**
  (петля reconciliation) — и валит уже его гейт.

Смысл: агент физически не может «сдать» дырявый или наводяще-собранный brief — линтер
режет до человеческого ревью.

---

## 5. Правила линтера `gate_check.py` (нормативный реестр)

| ID | Уровень | Правило |
|---|---|---|
| GC-01 | error | frontmatter парсится; `schema: discovery-brief`; `schema_version: 1` |
| GC-02 | error | SpecMeta-ядро: `spec_stage: discovery`, `status`, `generated_by`, `generated_at` непусты |
| GC-03 | error | `interview.frame ∈ {customer, engineer}`; `sessions` непуст; у каждой сессии `participant_role`; `interview.profile` (если есть) `∈ {full, feature}`, `feature` — только у customer |
| GC-04 | error | `coverage` содержит все required-ключи фрейма; значения ∈ {covered, partial, missing} |
| GC-05 | error | ключ `covered` ⇒ секция непуста (≥1 ID); пустая секция при `covered` — ложь в данных |
| GC-06 | error | каждое `FR-NN` имеет `traces` → ≥1 **существующего** `G/J` |
| GC-07 | error | каждая `M-NN` → ≥1 существующего `G` |
| GC-08 | error | каждое `FR` несёт `Priority` + `Acceptance`; каждое `NFR` — `Acceptance`/`Target` (в профиле `feature` — либо `**N/A**` с причиной) |
| GC-09 | error | каждый `Q-NN`: `owner_role` + `blocking`; каждый `X-NN`: `status ∈ {open, resolved}` |
| GC-10 | error | счётчики frontmatter = фактам тела (`open_questions`, `blocking_open_questions`, `conflicts`) |
| GC-11 | error | `gate_passed` в frontmatter = вычисленному по формуле §4 |
| GC-12 | error/warning | engineer: `traces_to` непуст (error); найденный upstream-brief читается (UTF-8) и парсится, `status: approved` (error); upstream не найден ⇒ warning (нерезолвящиеся пути ловит GC-16) |
| GC-13 | error | engineer: каждое `IF` → существующий `S`; каждое `AP` → `S`/`CON` |
| GC-14 | warning | customer: записи `S/IF/AP` в customer-брифе — solution-space протёк в problem-space |
| GC-15 | error | `validation` зеркалит линтер: `pass` допустим только при 0 ошибок; 0 ошибок при `pending`/пустом — протухшее зеркало |
| GC-16 | error | каждый путь-элемент `traces_to` (`*.md`) разрешается относительно брифа или корня его git-репо |
| GC-17 | error/warning | каждая ссылка на `Q-NN` в записи `FR`/`NFR`/`M` разрешается в запись `Q` брифа (error); ссылка на `Q` с `resolved: true` — warning: подставьте найденное значение |
| GC-18 | error | customer: секция `## Translation table` есть и непуста; заголовок совпадает с колонками §2 по порядку (без учёта регистра); в каждой строке шесть колонок, слова заказчика непусты, категория из словаря, ограничение ссылается на существующие `FR`/`NFR`/`CON`/`OUT`; у допущения есть подтверждающий и срок `YYYY-MM-DD` |
| GC-19 | error | customer: в translation table есть ≥1 строка каждой обязательной категории (`делать`, `не делать`, `стоить`, `доказывать`) |
| GC-20 | error | customer: у каждой `NFR` есть `**Category**`; есть ≥1 `NFR` категории `perf` и ≥1 категории `cost`; их цель — число с единицей до или после него (цифры ID записей не в счёт) или ссылка на `Q-NN`; в профиле `feature` — либо `**N/A**` с причиной |
| GC-21 | error | customer: каждый домен `process`, `data`, `quality`, `operations` закрыт `owns:` у записи `P` или открытого (не `resolved`) `Q` |
| GC-22 | error | `**N/A**` — только в профиле `feature`, только у `NFR`/`CON`, причина цитирует слова заказчика в непустых «…» |

---

## 6. Golden-фикстуры

Эталоны живут в `tests/fixtures/` этого репо (образец подхода — C2
`spec_meta_contract_v1.md`): `customer_good.md`, `customer_approved.md`,
`customer_feature_good.md` (профиль `feature`), `engineer_good.md` — проходят линтер; `bad_*.md` — каждая ломает ровно одно правило
GC-NN и поименована по нему. CI гоняет `gate_check.py` против всех.

Round-trip через SpecMeta (unknown-keys не теряются/не ломают `meta_from_dict`) —
ответственность spec-runner-стороны C2-контракта; здесь фиксируется только требование
совместимости (§1).

---

*Источники:* `_cowork_output/decisions/2026-07-13-adr-discovery-interview-agent.md`,
`_cowork_output/contracts/2026-07-13-discovery-brief-contract-v0.1.md` (черновик),
`spec-runner/src/spec_runner/spec.py` (SpecMeta v1, `meta_from_dict`),
`_cowork_output/spec-runner-c2-specmeta-contract/spec/` (REQ-401/402),
`spec-runner/spec/FORMAT.md` (FRD-стиль), [[project-spec-governance-layer]].
