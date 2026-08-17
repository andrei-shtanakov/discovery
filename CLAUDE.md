# CLAUDE.md

## Что это за репо

`discovery` — **runtime стадии discovery/elicitation** (паттерн author ≠ execute):
ведёт интервью со стейкхолдером и авторит `discovery-brief`, который входит в
governance-гейты (BR/FRD — фрейм customer; 0b/0a — фрейм engineer).

**Состояние на 2026-07-26 — каркас без реализации:** `main.py` — placeholder,
зависимостей, тестов и CI нет. Вся рабочая функция стадии живёт в соседнем
`../discovery-toolkit` (skill `discovery-interview`, канон `DISCOVERY-BRIEF-CONTRACT.md`
v1.1, линтер `gate_check.py`). Прежде чем что-то реализовывать здесь, прочитай
`TODO.md`: там записано, что **решение о старте runtime ещё не принято** — ADR выделяет
этот репо только когда понадобятся состояние, мультиюзер или UI, а оба реальных
интервью прошли skill'ом без runtime.

**Жёсткая граница:** discovery авторит бриф и на этом останавливается. Он **не пишет**
`tasks.md`, design и планы исполнения — компиляция вниз делегируется governance-слою
(Maestro decompose + spec-runner authoring). Нарушить это — значит воспроизвести
«второго автора спеки», с которым уже боролись.

Контекст решений: `../_cowork_output/decisions/2026-07-13-adr-discovery-interview-agent.md`,
план и тест-пирамида — `../_cowork_output/plans/2026-07-13-discovery-agent-flow-and-test-strategy.md`.

## Repo scope & boundaries

- **Этот репо:** `discovery` — git-корень `all_ai_orchestrators/discovery/`, remote `git@github.com:andrei-shtanakov/discovery.git`.
- **Соседи (READ-ONLY reference):** все остальные подпроекты воркспейса — их код не
  редактировать. Состав флота — `ai-orchestrators-workspace/workspace-manifest.toml`
  (SSOT); рукописные списки соседей в CLAUDE.md не ведём — они дрейфуют.
- **Канон имени репо = имя каталога после обычного `git clone`** (`maestro`, `libretto`).
- Нужна правка у соседа → **стоп**: запиши handoff в `../prograph-vault/authored/notes/`
  (кросс-проектное) или `../_cowork_output/` (черновик), не трогай его файлы.
- Кросс-репные контракты — **вендорить пиненой копией внутрь**, не ссылаться наружу.
- Для этого репо вендоринг — не абстракция: `discovery-toolkit` помечен `package = false`,
  зависимостью его не подключить — контракт и правила gate-check попадают сюда только
  копией с пином.
- Полное правило (SSOT): `../prograph-vault/authored/rules/repo-boundaries.md`.

## `../_cowork_output/` — dev-only

Координационный dev-scratch воркспейса; у пользователей и клонов проекта его НЕТ.
Shipped/runtime-код никогда не читает и не резолвит пути под ним; кросс-репные
контракты вендорятся пиненой копией внутрь, не ссылкой наружу. Ссылаться на него
могут только dev-тулинг самого воркспейса и документация. Канонические факты живут
в репо-владельце (пример: SSOT agents-catalog — `atp-platform/method/agents-catalog.toml`,
ADR-ECO-003). Полное правило (SSOT): `../prograph-vault/authored/rules/cowork-output.md`.

## Планы: где что лежит

- **`TODO.md` в корне** — план уровня команды и кросс-проектные точки. Это
  единственный машинно-читаемый план-файл: дайджест Robin строит прогноз работ по
  чекбоксам `- [ ]` / `- [x]` в корне зеркал, в подкаталоги он намеренно не заходит.
  Репо без `TODO.md` выглядит в обзоре экосистемы как репо без открытой работы.
- Микрошаги реализации, когда появятся, — в `docs/plans/` и описаниях PR, не в `TODO.md`.
- Поля пунктов — инлайн-теги `@owner:<principal>` /
  `@blocked_by:todo://<repo>/<id>` / `@trigger:"…"` / `@id:<node-id>`. Для
  `@owner:` каноничны `github:<login>`, `github-team:<org>/<team>`,
  `repo:<manifest-key>` и `TBD`; bare handle/role и `<repo>#<slug>` blocker — legacy.
  Отсутствующий `@owner:` означает «неизвестно», `@owner:TBD` — отложенное назначение.
  Теги держать **на одной строке** с `- [ ]` — парсер читает пункт построчно.
- Закрытый пункт — `[x]` + номер PR; неактуальный — `~~зачеркнуть~~` с причиной.
  **Строку не удалять**: дельта-счётчики читают исчезновение как «закрыто».
- Правя план-доки, держи их сверенными с кодом: устаревшая сводка хуже отсутствующей —
  по ней принимают решения.

## Python-тулинг

- Только `uv` (`uv add`, `uv run`), **никогда** `pip` / `uv pip install`.
- Python ≥ 3.12 (`pyproject.toml`). Типы обязательны, публичные API — с docstring.
- Формат и линт: `uv run ruff format .`, `uv run ruff check . --fix`, строка ≤ 88.
- Тесты: `uv run pytest`; async — через anyio, не asyncio.
- Первый же PR с кодом должен привезти и CI, и caller governance-гейта
  (ADR-ECO-004) — см. `TODO.md`, раздел «Инфраструктура репо».

## Git workflow (у репо есть remote)

- Ветка `<type>/<slug>` → push → `gh pr create`. **Прямые коммиты в `master`
  запрещены**, как и локальный мерж ветки в `master` в обход PR.
- После открытия PR — прочитать ревью **GitHub Copilot**: валидные замечания исправлять
  новыми коммитами в ту же ветку; невалидные — ответить с обоснованием, **не применять
  вслепую**; итерировать, пока не останется открытых замечаний. Ревью не всегда
  запрашивается само — если его нет, запросить явно:
  `gh api -X POST repos/<owner>/<repo>/pulls/<n>/requested_reviewers -f 'reviewers[]=copilot-pull-request-reviewer[bot]'`.
- **Не мержить.** Мерж делает пользователь.
- После мержа пользователем: `git switch master && git pull --ff-only`, затем удалить
  влитую ветку в **обеих половинах**: локально `git branch -d` (после squash-мержа `-d`
  откажется — сверить, что `git diff master <ветка>` пуст, и удалить `-D`) и на origin
  `git push origin --delete <ветка>`, если GitHub не удалил сам; затем `git fetch --prune`.
- Никогда не делать force-push в общие ветки; не трогать другие репо (см. scope выше).
- Полное правило (SSOT): `../prograph-vault/authored/rules/git-workflow.md`.

## Входящие запросы (inbox)

В начале работы проверь входящие: `gh issue list --label inbox --state open`.
Issue с лейблом `inbox` — запрос от соседнего репо, ещё **не** пункт плана.
Принять = завести пункт в `TODO.md` с указанным `slug:`; принял под другим
именем — поправь `slug:` в теле issue.
Отказать = `gh issue close --reason "not planned"`.
Нужна работа в соседнем репо — не редактируй его: заведи там issue
(`slug:` + `from:` + проза). Правило: ADR-ECO-006 — канон в `ecosystem-kb`
(каталог `prograph-vault/` в корне воркспейса),
`authored/decisions/2026-07-28-adr-eco-006-cross-repo-issue-inbox.md`.

Исходящее ожидание — вторая половина того же ритуала: «ждём соседа» существует
**только** как чекбокс `TODO.md` с `@blocked_by:todo://<repo>/<id>` (переходно —
`<repo>#<номер>`); память сессий, заметки и handoff-доки — лишь зеркало. Находка
PF-BLOCKER-STALE по этому репо = «ожидание доставлено — действуй или переставь тег».
Правило (SSOT): `../prograph-vault/authored/rules/cross-repo-waits.md`.
