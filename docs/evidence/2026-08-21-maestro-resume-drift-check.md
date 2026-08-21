# Проверка resume maestro после `maestro#198` (2026-08-21)

Закрывает `TODO.md` `@id:watch-maestro-198`. Это **не** оркестрованный прогон:
ни одного агента не запущено, репо и боевая база не тронуты — проверялось
поведение `--resume` на копии состояния прошлой арки.

Повод: `maestro#198` («resume молча продолжает со старым scope из `state.db`»)
закрыт апстримом 2026-08-19 без единого комментария. Прошлый раз этот дефект
стоил двух прогонов, причём правка `project.yaml` выглядела применённой и не
была, — поэтому проверяем до следующего прогона, а не после.

## Что оказалось починено — не то, что мы ждали

Формулировка пункта плана («resume применяет правку `project.yaml`») описывала
не то решение, которое принял апстрим. Чинил PR `maestro#199` (`73427f4` +
`3a3966c`, оба в `master`), и он делает обратное:

| | |
|---|---|
| Персистед-конфиг | **остаётся в силе** — прогон не меняет правила под собой на ходу |
| Что убрано | не подмена конфига, а **молчание** вокруг неё |
| Поведение при дрейфе | fail-closed halt на resume, **без флага обхода** |
| Что сравнивается | все поля `Workstream.from_config`, производная ветка (`branch_prefix`), множество id; `scope`/`depends_on` — без учёта порядка |
| Когда поднимается | в `run` **после** recovery: дрейф запрещает диспатч и декомпозицию, но не сверку уже существующих handle'ов |
| Как принять правку | `maestro workstream-rework <id> --refresh-from <config>` — и только `description`/`scope`; топология не принимается в живой прогон никак |

## Своя половина: установленный тулинг был из коммита до фикса

| | |
|---|---|
| Было установлено | `maestro` из `ffb5fa5` (merge PR #197) — **до** `f95918f` (merge #199) |
| Признак | в `site-packages/maestro/` нет `config_drift.py` |
| Стало | переустановлен с `master` — `6d93ca3` (включает #199, #200, #201) |

То есть на момент проверки закрытый апстрим-issue и установленный фикс были
разными фактами: сегодняшний прогон молчал бы ровно так же, как позавчерашний.

## Прогон проверки

```
cp ~/.maestro/discovery.db <scratch>/resume-check.db
maestro orchestrate project.yaml --resume --db <scratch>/resume-check.db
```

Дрейф в этой базе — ровно тот, что описан в апстрим-коммите: `project.yaml`
правился 2026-08-20, уже после старта прогона.

| воркстрим | scope в базе | scope в конфиге | разница |
|---|---|---|---|
| `a1-contract` | 7 | 11 | `test_vendor_pull.py`, `test_task_001_red.py`, `test_task_002_red.py`, `conftest.py` |
| `b-state` | 8 | 12 | четыре `test_task_00N_red.py` |
| `c-protocol` | 10 | 15 | пять `test_task_0NN_red.py` |
| `d1-cli` | 3 | 5 | `test_task_012_red.py`, `test_task_013_red.py` |

Результат — `exit 1`, ни одного диспатча:

```
WARNING:maestro.orchestrator:config drift detected on resume: 8 field(s), 0 added, 0 removed workstream(s)

╭────────────────────── Config drift — run not advanced ───────────────────────╮
│ config drift: …/discovery/project.yaml no longer matches this run's          │
│ persisted configuration.                                                     │
│ The run continues to use the PERSISTED version — a run does not change its   │
│ own rules mid-flight. Nothing was dispatched.                                │
│   workstream 'd1-cli':                                                       │
│     scope:                                                                   │
│       run:    ['src/discovery/cli.py', 'tests/test_boundary.py',             │
│                'tests/test_cli.py']                                          │
│       config: [… , 'tests/test_task_012_red.py',                             │
│                'tests/test_task_013_red.py']                                 │
│ description, scope — adopt with: maestro workstream-rework <id>              │
│ --refresh-from <config> …                                                    │
╰──────────────────────────────────────────────────────────────────────────────╯
```

Восемь полей — это `description` + `scope` у каждого из четырёх воркстримов:
описания правились тем же PR, что и scope (снятие обхода `spec-runner#301`).

**Побочных эффектов нет**, проверено после прогона: `git status` чист,
`git worktree list` — только сам репо, `discovery-maestro-ws/` пуст, боевая
`~/.maestro/discovery.db` осталась на миграции 22 (копия доехала до 28).

## Остаточное состояние прогонов

- `~/.maestro/discovery.db` — легаси-раскладка, схема 22, прогон первой арки
  (`a1-contract: ready`, остальные `pending`). Арка давно смержена, так что это
  мёртвое состояние; теперь оно ещё и защищено — `--resume` на него упирается в
  halt выше, а не продолжает старым scope.
- `~/.maestro/projects/github.com/andrei-shtanakov/discovery/runs/` — новая
  раскладка, 10 per-run каталогов от 2026-08-19. Свежайший
  (`01M0CYQ4VPBFBBQQ2S13WXD4Z6`, схема 27) — прогон A2/D2, в `run.outcome`
  стоит `superseded` («ended by the operator»), а его scope совпадает с
  `project.a2d2.yaml` пословно. Ждущего дрейфа там нет.

## Что из этого следует держать в руках

1. Перед оркестрованным прогоном сверять **ревизию установленного тулинга**, а
   не только читать апстрим-issue. `uv tool` пинует git-коммит: закрытие issue
   не двигает его само.
2. Правка `project.yaml` в живом прогоне больше не «применяется молча» и не
   «применяется» вообще: либо `workstream-rework --refresh-from` (это rework —
   пере-декомпозиция и новый автор), либо новый прогон.
3. Схема 28 (`run.workstreams_declared`) отличает удалённую секцию
   `workstreams:` от авто-декомпозиции. Для баз, заведённых раньше, этот случай
   fail-open — то есть у обеих наших старых баз он не проверяется.
