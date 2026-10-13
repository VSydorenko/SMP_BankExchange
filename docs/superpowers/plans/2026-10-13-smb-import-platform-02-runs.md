# Журнал прогонів — план 02 (розпізнавання)

План: `docs/superpowers/plans/2026-10-13-smb-import-platform-02-recognition.md`, бриф із коміту
`a948d7a`. Гілка `feature/smb-import-platform`.

Усі виклики Unica — з `cwd = SMP_BankExchange_SMB`. Колір тесту належить коміту: червоний —
на хеші коміту тесту, зелений — на хеші коміту продуктового коду, дерево чисте.

## Базова лінія (задача 0, крок 1)

**Умова:** 2026-10-13, `HEAD` = `bd67162`, `git status --short` порожній, серверна база агента SMB,
обидва source-set зібрано з `fullRebuild=true`, прогони послідовні. Еталон — фінальний прогін
журналу плану 01 («Після хвилі виправлень фінального рев'ю»); будь-яка розбіжність з ним — СТОП.

| Перевірка | Параметри | Результат |
|---|---|---|
| `unica_cfe_validate` | `cfe/src` | 0 errors, 1 warning (`Cannot check DefaultLanguage (empty)`) |
| `unica_cfe_validate` | `tests/src` | 0 errors (14 checks) |
| `build` | `sourceSet=SMP_BankExchange_SMB`, `fullRebuild=true` | Build completed successfully |
| `build` | `sourceSet=SMP_BankExchange_SMB_Tests`, `fullRebuild=true` | Build completed successfully |
| `test` | `yaxunit`, `module=СМП_ТестыКонтрольХарнеса` | `total=3, passed=3, failed=0, skipped=0, errors=0` |
| `test` | `module=СМП_ТестыВендораЗаполнениеПоОснованию` | `total=62, passed=60, failed=0, skipped=2, errors=0` |
| `test` | `module=СМП_ТестыВендораСпособЗачета` | `total=30, passed=30, failed=0, skipped=0, errors=0` |
| `test` | `module=СМП_ТестыКонтрактаВыписки` | `total=99, passed=99, failed=0, skipped=0, errors=0` |
| `test` | `module=СМП_ТестыПозднееСвязывание` | `total=3, passed=3, failed=0, skipped=0, errors=0` |
| `test` | `module=СМП_ТестыФикстур` (сторож залишків, останнім) | `total=49, passed=49, failed=0, skipped=0, errors=0` |
| `syntax` | `designer-modules`, `server`, `extension=SMP_BankExchange_SMB` | errors 89, warnings 0 — усі `Переменная не определена` у запозичених `ОбменСБанками*` (норма `known-state.md`) |
| `syntax` | `designer-modules`, `server`, `extension=SMP_BankExchange_SMB_Tests` | errors 301, warnings 1; усі `ЮТ*` (286 `Переменная не определена (ЮТ…)` + 16 повторів рядків `<<?>>ЮТест…`), не-`ЮТ` — 0 |
| сторож переносимості (старий шаблон) | `rg -c` із `cfe/src/CommonModules` | `СМП_ВыпискаБанка/`: 0 збігів (код виходу 1); контроль `СМП_РаботаСБанкамиСервер/`: 15 |

Розбіжностей із фінальним прогоном плану 01 немає: 3/3, 62/60/0/2, 30/30, 99/99, 3/3, 49/49;
SMB 89; SMB_Tests 301, не-`ЮТ` 0.

**Критерій регресії синтаксису.** Продуктове розширення — число помилок не більше 89. Тестове —
перевірка бачить лише розширення, тож кожне звернення до рушія YaXUnit (`ЮТест`, `ЮТТесты`, `ЮТ*`)
дає `Переменная не определена`, і їх число росте з кожним тестом. Регресія тестового розширення —
будь-яка помилка **іншого** виду.

## Прогони

| Задача | Коміт | `git status --short` | Модуль | total/passed/failed/skipped | Примітка |
|---|---|---|---|---|---|
| 0 | `bd67162` | порожній | усі модулі плану 01 | див. базову лінію | базова лінія, збігається з фінальним прогоном плану 01 |
