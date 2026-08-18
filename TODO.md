# TODO — discovery (заведён 2026-07-26)

> Роль в экосистеме: **runtime стадии discovery/elicitation** (author ≠ execute) —
> ведёт интервью со стейкхолдером и авторит `discovery-brief`, но **не пишет**
> `tasks.md`/design: компиляция вниз делегируется governance-слою.
> Методология и канон контракта — в соседнем `discovery-toolkit` (skill
> `discovery-interview`, `DISCOVERY-BRIEF-CONTRACT.md` v1.1 frozen 2026-07-14,
> линтер `gate_check.py` GC-01…GC-16).
> Решение: `../_cowork_output/decisions/2026-07-13-adr-discovery-interview-agent.md`;
> план и тест-пирамида: `../_cowork_output/plans/2026-07-13-discovery-agent-flow-and-test-strategy.md`;
> обзор экосистемы: `../COWORK_CONTEXT.md`.
> Повод завести файл: замер 2026-07-26 показал, что discovery — одно из зеркал без
> план-файла в корне, то есть его состояние было невидимо дайджесту Robin
> (`../_cowork_output/2026-07-26-plan-fields-and-todo-coverage-handoff.md` §2).
> Для скелета это особенно вредно: пустой каркас без плана читается в обзоре как
> «репо без открытой работы», хотя правда обратная — тут не начато **ничего**.

## Правила ведения

- После выполненной задачи — `[x]` и номер PR / хеш коммита.
- Задача стала неактуальной — зачеркнуть `~~...~~` с пометкой **почему**, не удалять:
  дельта-счётчики Robin читают исчезновение строки как «закрыто».
- Здесь — **только пункты уровня команды и кросс-проектные**. Микрошаги реализации
  появятся в `docs/plans/` и описаниях PR; дайджест их намеренно не читает.
- Поля пункта — инлайн-теги `@owner:<principal>` /
  `@blocked_by:todo://<repo>/<id>` / `@trigger:"…"` / `@id:<node-id>`. Для
  `@owner:` каноничны `github:<login>`, `github-team:<org>/<team>`,
  `repo:<manifest-key>` и `TBD`; bare handle/role — legacy. Отсутствующий `@owner:`
  означает, что владелец неизвестен; `@owner:TBD` — что назначение явно отложено.
- **Теги и суть пункта — на одной строке с `- [ ]`**: парсер Robin (`plan_state`)
  разбирает пункт построчно, продолжения ниже он не видит. Отступленные строки под
  пунктом — контекст для человека.
- Правку в соседнем репо здесь не планируем как свою работу: кросс-репный пункт —
  это **handoff** (см. `CLAUDE.md`, scope & boundaries).

## Текущее состояние (замер 2026-07-26)

- ✅ Репо создан 2026-07-14 как каркас graduation'а из ADR 2026-07-13
- ✅ README/pyproject описывают реальный замысел, а не placeholder (PR #1, 07-18)
- ❌ **Кода нет**: `main.py` — `print("Hello from discovery!")`; зависимостей, тестов,
  CI и governance-гейта нет
- ✅ Вся рабочая функция стадии сейчас живёт в `../discovery-toolkit`: фазы 0–2 ADR
  закрыты там, оба реальных прогона (dispatcher, customer + engineer) прошли skill'ом
  и получили approve через PR `dispatcher#14–#17`

Отсюда главный факт этого файла был: **у репо нет открытой работы по коду — у него
есть неразрешённое решение, начинать ли работу вообще**. **Снято 2026-08-18**:
решение принято (раздел ниже), открытая работа по коду появилась — арка runtime-v1,
дизайн в `docs/superpowers/specs/2026-08-18-discovery-runtime-design.md`. Замер выше
описывает состояние на 2026-07-26 и не переписывается задним числом.

---

## Решение о старте (принято 2026-08-18 — больше ничего не блокирует)

- [x] Решить: наполнять runtime или явно припарковать репо до триггера @owner:github:andrei-shtanakov @id:start-decision
      **Решение 2026-08-18 (владелец): наполнять.** Триггер сработал не тот, что был
      записан: не состояние/мультиюзер/UI сами по себе, а **вызываемость стадии
      прогоном** — стадию Need должен уметь запускать конвейер, а состояние нужно ровно
      затем, чтобы стадия умела приостановиться в ожидании человека. Мультиюзер и
      веб-UI остаются вне скоупа; стейкхолдер-агент уезжает в L3-бенчмарк
      (`@id:l3-quality-benchmark`). Дизайн:
      `docs/superpowers/specs/2026-08-18-discovery-runtime-design.md`.
      ADR (раздел «Где живёт», вариант B) выделяет репо **только** когда контракт
      стабилен **и** нужны состояние/мультиюзер/UI. Первое условие выполнено с
      2026-07-14; второе выполнено в форме «состояние обязательно, потому что стадия
      ждёт человека» — оба реальных интервью прошли skill'ом, но ни одно не вызывалось
      прогоном, и вызвать их прогоном сегодня нечем.

## Наполнение runtime (решение принято; порядок — воркстримы A1/A2/B/C/D1/D2 в дизайне §10)

- [ ] Вендорить пиненую копию `DISCOVERY-BRIEF-CONTRACT.md` внутрь репо @owner:github:andrei-shtanakov @id:vendored-contract
      Shipped-код не резолвит ни `../_cowork_output/`, ни `../discovery-toolkit/`
      (правило `repo-boundaries`). Сейчас README перечисляет соседние пути как
      canonical upstream inputs — для доки это нормально, для рантайма нет.
      Вендоринг тут не «один из вариантов», а единственный: `discovery-toolkit`
      помечен `package = false`, то есть зависимостью его не подключить.
- [ ] Тест синхронизации вендоренной копии с каноном @owner:github:andrei-shtanakov @blocked_by:todo://discovery/vendored-contract @id:vendored-contract-sync
      Образец готов у соседа — `discovery-toolkit/tests/test_contract_sync.py`.
      Без него пиненая копия тихо разъедется с каноном, и это увидит только человек.
- [x] Решить судьбу `gate_check.py`: вендорить линтер или переопубликовать как общий пакет @owner:github:andrei-shtanakov @id:gate-check-strategy
      **Решено 2026-08-18: вендорить пиненой копией, третьей реализации не будет.**
      `discovery-toolkit` помечен `[tool.uv] package = false` — переопубликование
      означало бы изобрести ему release-поверхность, которой у него намеренно нет.
      Копия не даёт третьей реализации именно потому, что вендорится **код** `check()`
      и `FRAMES`, а не пересказ таблицы §4: правила остаются одни. Расхождение с
      каноном ловят две раздельные гарантии (copy-integrity в PR-гейте против
      upstream-дерева на коммите из `PINNED.txt`; scheduled upstream-drift), недоступный
      upstream ⇒ `unknown`, не `pass`. Дизайн §4.
- [ ] Вендорить банк вопросов (`frames/*.md`) + парс маркеров `coverage_key` + fail-closed инвариант полноты @owner:github:andrei-shtanakov @blocked_by:todo://discovery-toolkit/bank-coverage-key-markers @id:vendored-bank
      Нужен `QuestionSource.bank`. Ключ темы не выводится из ID-префикса заголовка **по
      построению**: `X-NN`/`Q-NN` сквозные (их порождают и feasibility-проход, и тема
      «Завершение»), а `feasibility_review` — required-ключ с `None` в `FRAMES`
      («процесс, не секция»). Поэтому запрошен машинный маркер у владельца банка:
      `discovery-toolkit#4`. Эвристику по заголовку и вторую таблицу «тема → ключ» на
      своей стороне не заводим. Инвариант — «каждый required-ключ фрейма заявлен ≥1
      темой», error, не warning.
- [ ] Границу author ≠ execute закрепить тестом, а не только доками @owner:github:andrei-shtanakov @blocked_by:todo://discovery/vendored-contract @id:author-execute-boundary
      ADR TL;DR 2 и README запрещают писать `tasks.md`/design/execution-планы. Пока
      это утверждение в прозе; у соседа-аналога (dispatcher) такие инварианты
      проверяются кодом.
- [ ] L2-тесты `transcript → brief` (ассерты на свойства брифа, не на текст) @owner:github:andrei-shtanakov @trigger:"накопились 2–3 замороженных транскрипта интервью" @id:l2-transcript-brief-tests
- [ ] L3-бенчмарк качества интервью на ATP: симулятор со скрытой спекой, метрики coverage-recall / anti-sycophancy / leading-question rate @owner:github:andrei-shtanakov @trigger:"появился работающий runtime" @id:l3-quality-benchmark
      План §3: прогон живёт в нетрекаемом стенде `discovery-test`, фикстуры L0/L1 — в
      тестах репо. Раньше runtime мерить нечего.
- [ ] Фаза 3 (grounding): чтение `../prograph-vault` перед интервью, чтобы не спрашивать уже известное; `traces_to` на KB @owner:github:andrei-shtanakov @id:phase-3-grounding
      Это же место пересечения с Robin — см. раздел ниже.
- [ ] Политика приватности `interview.sessions`: хранить роли, не имена @owner:github:andrei-shtanakov @trigger:"первое интервью с сотрудником, а не с заказчиком" @id:employee-interview-privacy-policy
      ADR «Последствия» §5: провенанс «кто что сказал» при опросе сотрудников
      чувствителен, и решать это надо до пилота, а не после.

## Инфраструктура репо

- [ ] Подключить governance-гейт ADR-ECO-004 (caller `governance / gate`) @owner:github:andrei-shtanakov @trigger:"в репо появился код или CI" @id:governance-gate-caller
      Замер 2026-07-26: тонкий caller зонтичного reusable-workflow есть у 14 репо
      набора, discovery среди них нет. На пустом каркасе гейт нечего защищать, но включать его надо тем же PR,
      что приносит первый код, — иначе первая же реализация въезжает без проверки
      границ и путей.
- [ ] Handoff: зарегистрировать discovery в `workspace-manifest.toml` (SSOT набора) @owner:github:andrei-shtanakov @id:workspace-manifest-registration
      В манифесте `ai-orchestrators-workspace` сейчас 3 ядра + 11 apps + 2 tools, и
      ни discovery, ни discovery-toolkit в них нет. Правка — в чужом репо, поэтому
      наша часть ровно одна: написать handoff, когда репо перестанет быть каркасом.

## Открытые вопросы (не работа этого репо, но форму работы задают)

Намеренно не чекбоксы: решение принимается за пределами discovery.

- **discovery ↔ robin.** Общий conversational+KB субстрат зафиксирован, слияние
  отложено: Robin читает и отвечает, интервьюер спрашивает и пишет — потоки
  противоположны. Пункт остаётся открытым в `COWORK_CONTEXT.md`; риск — повторить
  overlap-триаж уровня dispatcher ↔ prograph ↔ appgraph.
- **Соло-режим.** Без реальных стейкхолдеров интервью вырождается в самоопрос, и
  фрейм должен схлопываться в мини-профиль (ADR «Последствия» §4). Для runtime это
  не украшение, а вопрос о том, кто вообще его пользователь.
