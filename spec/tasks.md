# discovery runtime v1 — canonical backlog

Канонический бэклог арки runtime-v1. Детальные шаги, тестовый код и сигнатуры —
в `docs/superpowers/plans/2026-08-18-discovery-runtime-v1.md` (далее «план»);
дизайн и его обоснование — в
`docs/superpowers/specs/2026-08-18-discovery-runtime-design.md` (далее «спека»).

Здесь — идентичность задач, зависимости и критерии приёмки. Maestro генерирует
свои `spec/maestro-*.md` на каждый воркстрим; статусы в этом файле сверяются
вручную после финального PR (та же практика, что в `kapelle/project.yaml`).

Воркстримы: **A1** (TASK-001…002), **B** (TASK-003…006), **C** (TASK-007…011),
**D1** (TASK-012…013), **A2** (TASK-014), **D2** (TASK-015…016).

## Milestone A1: вендоренный контракт

### TASK-001: Скелет пакета и вендоринг контракта
🔴 P0 | ⬜ TODO | Est: 2h

**Checklist:**
- [ ] Проверить базу (она **уже готова**, не пересоздавать): `uv run pytest` стартует, `ruff check`/`format --check` чисты, `discovery.contract.gate_check` импортируется и отдаёт оба фрейма — при расхождении остановиться с отчётом
- [ ] `tools/vendor_pull.py` копирует контракт и линтер и пишет `PINNED.txt` (upstream, commit, `path sha256`); назначение берётся из `VENDOR_DEST`, иначе `src/discovery/contract`
- [ ] Тест инструмента **герметичный**: поддельный upstream в `tmp_path`, никакого соседнего чекаута — внутри worktree его и нет
- [ ] Вендоренные `DISCOVERY-BRIEF-CONTRACT.md` и `gate_check.py` **уже лежат** в `src/discovery/contract/` (пред-вендоринг на базовой ветке); задача добавляет `__init__.py` и делает их импортируемыми как `discovery.contract.gate_check`
- [ ] `tests/test_vendored_copy.py` зелёный: пин называет 40-символьный коммит, файлы совпадают с digest'ами, `FRAMES` и `check()` доступны
- [ ] Вендоренные файлы не отредактированы ни на байт

**Traces to:** план Task 1, спека §4
**Примечание:** вендоринг — одноразовое действие разработчика, требующее доступа к
upstream-чекауту, которого внутри maestro-worktree нет (`../discovery-toolkit` резолвится
рядом с worktree). Поэтому копия кладётся на базовую ветку до прогона; задача её не тянет.
**Depends on:** —
**Blocks:** [TASK-002], [TASK-003], [TASK-007]

### TASK-002: Две гарантии копии и тест на сам прибор
🔴 P0 | ⬜ TODO | Est: 3h

**Checklist:**
- [ ] `tools/check_vendor.py` с режимами `consistency` / `provenance` / `drift`, коды выхода 0/1/3
- [ ] `provenance` сравнивает байты с upstream-деревом на пиненом коммите; недоступность → `unknown` (exit 3), никогда не `ok`
- [ ] Негативный тест: `consistency` не описывает себя как доказательство происхождения
- [ ] `drift` красит job красным при `unknown`; **свежесть самой вахты не проверяется изнутри job'а** — это вечная блокировка (первый прогон не имеет предыдущего успеха), её ловит внешний наблюдатель
- [ ] Манифест `PINNED.txt` сам предмет проверки: удаление строки не должно тихо выводить файл из-под обеих гарантий (`EXPECTED_SURFACE` + регресс-тест)
- [ ] Оба workflow заведены: `vendor-integrity` (PR) и `vendor-drift` (scheduled)

**Traces to:** план Task 2, спека §4
**Depends on:** [TASK-001]
**Blocks:** —

## Milestone B: состояние сессии

### TASK-003: Канонические байты ответа и `answer_id`
🔴 P0 | ⬜ TODO | Est: 1h

**Checklist:**
- [ ] `canonical_answer_bytes`: UTF-8, `CRLF`/`CR` → `LF`, без trimming и прочих преобразований
- [ ] `answer_id` = SHA-256 по (`session_id`, `question_id`, `participant_role`, канонические байты), поля разделены NUL
- [ ] Тест: тот же текст от другой роли даёт другой id
- [ ] Тест: конкатенацию полей нельзя прочитать двояко

**Traces to:** план Task 3, спека §5
**Depends on:** [TASK-001]
**Blocks:** [TASK-012]

### TASK-004: Журнал событий с обещанной durability
🔴 P0 | ⬜ TODO | Est: 2h

**Checklist:**
- [ ] `Journal.append`: блокировка, одна целая JSONL-строка `O_APPEND`, `flush` + `fsync`
- [ ] Событие с переводами строк внутри значения остаётся одной строкой файла
- [ ] Битая строка даёт `JournalUnreadable`, а не молчаливый пропуск
- [ ] `ts` проставляется, если не передан

**Traces to:** план Task 4, спека §5
**Depends on:** [TASK-001]
**Blocks:** [TASK-005], [TASK-008]

### TASK-005: Раскладка сессии и атомарная запись артефакта
🔴 P0 | ⬜ TODO | Est: 2h

**Checklist:**
- [ ] `Session.create` / `Session.load`, заголовок с `frame`, `target`, `traces_to`, `source_pin`, `created_at`
- [ ] Отсутствующая сессия → `SessionUnreadable`
- [ ] `write_artifact`: temp-файл рядом, `os.replace`, **fsync каталога** после переименования
- [ ] После записи не остаётся временных файлов

**Traces to:** план Task 5, спека §5
**Depends on:** [TASK-004]
**Blocks:** [TASK-009], [TASK-012]

### TASK-006: Структурированный payload ответа
🔴 P0 | ⬜ TODO | Est: 2h

**Checklist:**
- [ ] `parse_payload`: YAML с `text` (дословно) и `entries` (типизированные записи контракта)
- [ ] Запись без `id` и запись с некорректным `id` отвергаются (`PayloadInvalid`)
- [ ] Поля записи (`traces`, `Priority`, `Acceptance`, …) сохраняются дословно
- [ ] Payload только с `text` валиден

**Traces to:** план Task 6, спека §5 (поправка о структурированном ответе)
**Depends on:** [TASK-001]
**Blocks:** [TASK-009], [TASK-012]

## Milestone C: контракт статуса

### TASK-007: Порт `QuestionSource` и статическая реализация
🔴 P0 | ⬜ TODO | Est: 1h

**Checklist:**
- [ ] `Question(question_id, coverage_key, text)`, Protocol `QuestionSource` с `pin` и `questions(frame)`
- [ ] `StaticQuestionSource` возвращает каталог в порядке объявления
- [ ] Реализации `llm` в v1 нет — только интерфейс

**Traces to:** план Task 7, спека §3
**Depends on:** [TASK-001]
**Blocks:** [TASK-008]

### TASK-008: Lifecycle и `next_action` из журнала
🔴 P0 | ⬜ TODO | Est: 3h

**Checklist:**
- [ ] `awaiting_input` пока есть невыданный обязательный вопрос или выданный без ответа; иначе `complete`
- [ ] Выданный, но неотвеченный вопрос возвращается **из журнала**, а не резолвом id по текущему банку
- [ ] Тест: сессия переживает ре-пин банка (id исчез из источника, вопрос восстановлен из журнала)
- [ ] Ответ не по порядку допустим: следующим остаётся ранее выданный неотвеченный

**Traces to:** план Task 8, спека §5
**Depends on:** [TASK-004], [TASK-007]
**Blocks:** [TASK-011], [TASK-012]

### TASK-009: Рендер брифа из журнала
🔴 P0 | ⬜ TODO | Est: 4h

**Checklist:**
- [ ] Frontmatter несёт ядро контракта: `schema`, `schema_version`, `spec_stage`, `interview.frame`, `sessions[].participant_role`
- [ ] `coverage` вычисляется по присутствующим записям; `validation` пишется как передан, не предсказывается
- [ ] Записи попадают в тело с полями (`Priority`, `Acceptance`, `traces`)
- [ ] Перекрытый (superseded) ответ в тело не попадает
- [ ] Рендер — чистая функция входов

**Traces to:** план Task 9, спека §5
**Depends on:** [TASK-005], [TASK-006]
**Blocks:** [TASK-010]

### TASK-010: Двухпроходный render → gate
🔴 P0 | ⬜ TODO | Est: 2h

**Checklist:**
- [ ] Порядок `render(pending) → check → render(pass|fail + findings) → check`, принимается только второй проход
- [ ] Отдельный ассерт: второй проход чист по GC-15
- [ ] Тонкий бриф валит гейт и объясняет чем (findings непусты)
- [ ] `validation` в возвращённом тексте совпадает с вердиктом

**Traces to:** план Task 10, спека §6
**Depends on:** [TASK-009]
**Blocks:** [TASK-012]

### TASK-011: Конверт статуса и приоритет кодов
🔴 P0 | ⬜ TODO | Est: 2h

**Checklist:**
- [ ] Конверт из пяти ключей: `lifecycle`, `gate`, `next_action`, `findings`, `operation`
- [ ] Приоритет `1 > 2 > 20 > 10 > 0`; `awaiting_input` перебивает падающий гейт
- [ ] `findings` возвращаются и при 20
- [ ] Отказ (exit 2) сохраняет оси вычисленными; `unknown` в осях только при exit 1

**Traces to:** план Task 11, спека §7
**Depends on:** [TASK-008]
**Blocks:** [TASK-012]

## Milestone D1: CLI и граница

### TASK-012: CLI — четыре команды над ядром
🔴 P0 | ⬜ TODO | Est: 4h

**Checklist:**
- [ ] `start` / `status` / `answer` / `brief`, все печатают один конверт
- [ ] `question_asked` персистится ДО возврата команды
- [ ] Повтор того же `answer_id` — no-op; конфликтующий ответ отвергается (exit 2), с `--supersede` принимается
- [ ] Неизвестная сессия → exit 1 и `lifecycle: unknown`
- [ ] Сессии под `$DISCOVERY_HOME/sessions`, дефолт `~/.discovery`
- [ ] `uv run pytest && ruff check && ruff format --check && pyrefly check` зелёные

**Traces to:** план Task 12, спека §7
**Depends on:** [TASK-003], [TASK-005], [TASK-006], [TASK-010], [TASK-011]
**Blocks:** [TASK-013]

### TASK-013: Граница author ≠ execute как capability
🔴 P0 | ⬜ TODO | Est: 2h

**Checklist:**
- [ ] В графе импортов ядра нет сети и запуска процессов (`socket`, `urllib`, `httpx`, `subprocess`, …)
- [ ] Полный прогон пишет только под корень сессии и в переданный `brief_path`; в рабочем каталоге не появляется ничего
- [ ] Проверка сделана capability-тестом, а не поиском строк `tasks.md` / `design`

**Traces to:** план Task 13, спека §8
**Depends on:** [TASK-012]
**Blocks:** —

## Milestone A2: банк вопросов

### TASK-014: Вендоренные фреймы, маркеры, fail-closed инвариант
🟡 P1 | ⬜ TODO | Est: 3h

**Checklist:**
- [x] Фреймы **пред-вендорены** на базовую ветку с обновлением `PINNED.txt` (та же причина, что у TASK-001: upstream вне worktree) — сделано до прогона, коммит `4664604`; копию не трогать и `vendor_pull.py` против upstream не запускать
- [ ] `vendor_pull` создаёт подкаталог назначения перед копированием: `frames/` не существует, и `--include-frames` иначе падает на первом же файле
- [ ] Пути банка читаются по реальной раскладке toolkit (`.claude/skills/discovery-interview/frames/`), а пишутся плоско в `contract/frames/` — отображение source→dest, а не общий префикс
- [ ] `EXPECTED_SURFACE` расширен обоими файлами банка
- [ ] `parse_frame` читает маркер `coverage_key` / `produces`, ключ не угадывается по заголовку
- [ ] Буллет с переносом строки склеивается в один вопрос: в вендоренных фреймах таких 3 и 7, и построчный парсер обрывает текст вопроса на полуслове
- [ ] Тема кончается заголовком **любого** уровня, не только `###`: после последней темы идут `## Coverage` и `## Правила извлечения`, чьи буллеты иначе дописываются в неё
- [ ] Инвариант: каждый required-ключ фрейма заявлен ≥1 темой; нарушение — error
- [ ] `produces` сверяется с префиксом из `FRAMES`; `coverage_key: none` легитимен
- [ ] id вопросов вида `<frame>.<coverage_key>.<NN>`

**Traces to:** план Task 14, спека §4
**Depends on:** [TASK-001] · внешний блокер `discovery-toolkit#4` (машинные маркеры) снят: закрыт выполненным, маркеры в банке с коммита `ee93092`
**Blocks:** [TASK-015]

## Milestone D2: полный флоу и живая приёмка

### TASK-015: Банк в CLI и сквозной прогон
🟡 P1 | ⬜ TODO | Est: 2h

**Checklist:**
- [ ] `build_source()` возвращает `BankQuestionSource`, пиненый коммитом из `PINNED.txt`
- [ ] Пустой источник вопросов даёт `lifecycle: unknown`, а не `complete` (правка §5): `complete` требует, чтобы источник объявил ≥1 вопрос для фрейма; `gate` при этом считается как обычно, `operation.status` остаётся `ok`, код выхода — 1
- [ ] Выданный неотвеченный вопрос перебивает пустой источник: `awaiting_input`, а не `unknown` — журнал уже свидетельствует, что разговор идёт
- [ ] Вендоренный банк отвечает для обоих фреймов
- [ ] Сквозной тест: suspend → resume → `lifecycle: complete` → бриф записан и прогнан через гейт
- [ ] Полная верификация зелёная, включая `check_vendor.py provenance`

**Traces to:** план Task 15, спека §10
**Depends on:** [TASK-013], [TASK-014]
**Blocks:** [TASK-016]

### TASK-016: Живая приёмка с реальным стейкхолдером
🟡 P1 | ⬜ TODO | Est: 1d

**Checklist:**
- [ ] Расширение `write_scope` на целевой репо объявлено ДО прогона и только для него
- [ ] `start` → exit 20, процесс завершён, `status`/`answer` из нового процесса
- [ ] Достигнуты `lifecycle: complete`, `gate: pass`, exit 0
- [ ] Бриф записан в разрешённый путь целевого репо; независимый прогон вендоренного гейта чист
- [ ] Файл доказательств связывает session id, `transcript_sha256`, `brief_sha256` и commit/PR целевого репо — эти два артефакта единственные, что арка хеширует, и хеши снимаются на этом шаге: журнал лежит под `$DISCOVERY_HOME`, бриф ещё не закоммичен, и связать бриф в PR с этой сессией больше нечем. Всё, что уже в git, пинится commit SHA запуска (спека §11)
- [ ] Нет стейкхолдера → статус `implementation complete, live acceptance pending`, не `accepted`

**Traces to:** план Task 16, спека §12
**Depends on:** [TASK-015]
**Blocks:** —
