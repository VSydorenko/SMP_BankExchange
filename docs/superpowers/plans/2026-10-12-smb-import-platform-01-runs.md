# Журнал прогонів — план 01 (фундамент)

План: `docs/superpowers/plans/2026-10-12-smb-import-platform-01-foundation.md`, бриф із коміту
`fd748f6`. Гілка `feature/smb-import-platform` від `0dc8aa0`.

Усі виклики Unica — з `cwd = SMP_BankExchange_SMB`. Колір тесту належить коміту: червоний —
на хеші коміту тесту, зелений — на хеші коміту продуктового коду, дерево чисте.

## Базова лінія (задача 1)

**Умова:** 2026-10-12, `HEAD` = `0dc8aa0`, `git status --short` порожній, серверна база агента SMB.

| Перевірка | Параметри | Результат |
|---|---|---|
| `unica_cfe_validate` | `cfe/src` | 0 errors, 1 warning (`Cannot check DefaultLanguage (empty)`) |
| `unica_cfe_validate` | `tests/src` | 0 errors (14 checks) |
| `build` | `sourceSet=SMP_BankExchange_SMB`, `fullRebuild=true` | Build completed successfully |
| `build` | `sourceSet=SMP_BankExchange_SMB_Tests`, `fullRebuild=true` | Build completed successfully |
| `syntax` | `designer-modules`, `server`, `extension=SMP_BankExchange_SMB` | errors 89, warnings 0 — усі `Переменная не определена` у запозичених `ОбменСБанками*` (норма `known-state.md`) |
| `syntax` | `designer-modules`, `server`, `extension=SMP_BankExchange_SMB_Tests` | errors 2, warnings 0 — обидві `Переменная не определена (ЮТест)` у `СМП_ТестыКонтрольХарнеса` |
| `test` | `yaxunit`, `module=СМП_ТестыКонтрольХарнеса` | `total=3, passed=3, failed=0, skipped=0, errors=0` |

**Критерій регресії синтаксису.** Продуктове розширення — число помилок не більше 89.
Тестове — перевірка бачить лише розширення, тож кожне звернення до рушія YaXUnit (`ЮТест`,
`ЮТест*`, `ЮТ*`) дає `Переменная не определена`, і їх число росте з кожним тестом. Регресія
тестового розширення — будь-яка помилка **іншого** виду.

## Прогони

| Задача | Коміт | `git status --short` | Модуль | total/passed/failed/skipped | Примітка |
|---|---|---|---|---|---|
| 1 | `0dc8aa0` | порожній | `СМП_ТестыКонтрольХарнеса` | 3/3/0/0 | базова лінія |
| 2 | `0575e5a` | зонд у `tests/src`, не закомічений (вимір бази, не колір тесту) | `СМП_ТестыЗондБазы` (тимчасовий, навмисно червоний) | 4/0/4/0 | вимір вмісту бази; результат — `known-state.md`, «Вміст бази агента SMB» |
