# SMP_V8StorageKit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Упакувати конвеєр «сховище ↔ git» з SMP_BankExchange у плагін Claude Code `v8storagekit` (репозиторій `VSydorenko/SMP_V8StorageKit`) і перевести SMP_BankExchange на нього як першого споживача.

**Architecture:** Один публічний репозиторій = маркетплейс + плагін. Скрипти/модулі/тести **копіюються** з `R:\github\SMP_BankExchange\tools` з двома адаптаціями: параметр `-RepoRoot` (замість якоря `$PSScriptRoot\..`) і виявлення продуктів у `build.ps1` (замість вшитого списку BankExchange). Три скіли надають UX; шаблони — файли репо-споживача.

**Tech Stack:** PowerShell 7, Pester 5, Claude Code plugins (marketplace + skills), платформа 1С 8.3.27.x.

**Spec:** `R:\github\SMP_BankExchange\docs\superpowers\specs\2026-08-29-v8storagekit-design.md`

## Global Constraints

- Два робочі каталоги: Tasks 1–11 виконуються в `R:\github\SMP_V8StorageKit` (порожній клон, гілка `main`); Tasks 12–13 — у `R:\github\SMP_BankExchange` (гілка `restructure/2026-08`). Кожен коміт — у свій репозиторій.
- **Копіювання, не повторна розробка**: файли з `SMP_BankExchange/tools` переносяться байт-у-байт; зміни — лише ті, що явно вказані в задачах.
- Kit публічний: жодних логінів, паролів, рядків підключення, імен серверів у файлах kit. Локальні шляхи (`R:\...`) — лише в документації як приклади.
- Сховища 1С — тільки читання; мутуючі скрипти без `-Apply` нічого не змінюють. Ці межі переносяться в шаблони й скіли дослівно.
- Канонічна форма виклику скриптів у скілах і шаблонах: `pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/<скрипт>.ps1" -RepoRoot . ...`
- Контракт `storage.json` (`storagePath`, `extensionName`, `lastSyncedVersion`, `sourcePath`) не змінюється.
- Тести: `pwsh -NoProfile -File tools/tests/Run-Tests.ps1 -ExcludeTag Integration` має бути зеленим після кожної задачі, що чіпає `tools/`.
- Мова файлів kit — українська (як у BankExchange); імена скілів/файлів — англійська kebab-case.

---

### Task 1: Скаффолд плагіна й маркетплейсу

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.claude-plugin/marketplace.json`
- Create: `README.md`
- Create: `.gitignore`

**Interfaces:**
- Produces: імена `v8storagekit` (плагін) і `smp-v8storagekit` (маркетплейс) — їх використовують Tasks 11 і 13 у командах `claude plugin ...`.

- [ ] **Step 1: Створити `.claude-plugin/plugin.json`**

```json
{
  "name": "v8storagekit",
  "description": "Конвеєр «сховище конфігурацій 1С ↔ git»: синхронізація версій сховища в git з авторством, вивантаження конфігурацій, розкатка розширень у дев-бази, збірка .cfe/.epf, міграція старих gitsync-репозиторіїв.",
  "version": "0.1.0",
  "author": { "name": "Volodymyr Sydorenko" }
}
```

- [ ] **Step 2: Створити `.claude-plugin/marketplace.json`**

```json
{
  "name": "smp-v8storagekit",
  "owner": { "name": "VSydorenko" },
  "plugins": [
    {
      "name": "v8storagekit",
      "source": "./",
      "description": "Конвеєр «сховище конфігурацій 1С ↔ git» для репозиторіїв SMP_*"
    }
  ]
}
```

- [ ] **Step 3: Створити `.gitignore`**

```gitignore
# Робочі каталоги тестів і тимчасові артефакти
.build/
build/
```

- [ ] **Step 4: Створити `README.md`**

```markdown
# SMP_V8StorageKit

Плагін Claude Code: конвеєр «сховище конфігурацій 1С ↔ git» для репозиторіїв SMP_*.
Походження — SMP_BankExchange (перезапуск 2026-08); скрипти й тести перенесені звідти.

## Встановлення

    claude plugin marketplace add VSydorenko/SMP_V8StorageKit
    claude plugin install v8storagekit@smp-v8storagekit

## Що всередині

- `tools/` — скрипти конвеєра (storage-sync, dump-config, load-ext, build) + модулі + Pester-тести
- `skills/` — storage-pipeline (щоденний цикл), product-onboarding (новий продукт), repo-migration (міграція старого репо)
- `templates/` — шаблони файлів репо-споживача (CLAUDE.md, .gitattributes, .gitignore, settings.json, storage.json)
- `docs/` — архітектура контуру «сховище ↔ git»

## Розробка

Робоча копія — звичайний клон. Живе тестування на реальному проєкті:

    claude --plugin-dir R:\github\SMP_V8StorageKit

`/reload-plugins` підхоплює правки без перезапуску сесії. Тести:

    pwsh -NoProfile -File tools/tests/Run-Tests.ps1 -ExcludeTag Integration

Повний прогін (з тегом Integration) реально запускає 1cv8.exe і створює файлову ІБ.
```

- [ ] **Step 5: Перевірити валідність JSON**

Run: `pwsh -NoProfile -Command "Get-Content .claude-plugin/plugin.json -Raw | Test-Json; Get-Content .claude-plugin/marketplace.json -Raw | Test-Json"`
Expected: `True` двічі.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "Скаффолд плагіна v8storagekit: plugin.json, marketplace.json, README"
```

---

### Task 2: Копія tools/ з BankExchange, зелені тести

**Files:**
- Create: `tools/**` — копія з `R:\github\SMP_BankExchange\tools` (скрипти, `lib/`, `tests/` з фікстурами, `assets/empty-extension/`), **без** `tools/assets/.build/` (кеш Unica, не частина інструментів).

**Interfaces:**
- Produces: `tools/lib/{PathSafety,V8,StorageReport,Authors,SyncState}.psm1`, скрипти `storage-sync.ps1`, `dump-config.ps1`, `load-ext.ps1`, `build.ps1`, тести. Tasks 3–5 редагують саме ці файли.

- [ ] **Step 1: Скопіювати дерево**

```powershell
robocopy R:\github\SMP_BankExchange\tools R:\github\SMP_V8StorageKit\tools /E /XD .build
```

Expected: код robocopy 1 (файли скопійовано); у `tools/assets/` немає теки `.build`.

- [ ] **Step 2: Прогнати тести**

Run: `pwsh -NoProfile -File tools/tests/Run-Tests.ps1 -ExcludeTag Integration`
Expected: PASS, 0 failed (тести відносні до `$PSScriptRoot`, розташування в kit їх не ламає).

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "tools/: копія конвеєра з SMP_BankExchange (стан restructure/2026-08)"
```

---

### Task 3: Модуль RepoRoot.psm1 (TDD)

**Files:**
- Create: `tools/lib/RepoRoot.psm1`
- Create: `tools/tests/RepoRoot.Tests.ps1`

**Interfaces:**
- Produces: `Resolve-V8RepoRoot -Path <string>` → повертає розв'язаний абсолютний шлях (string) або кидає виняток. Використовується Tasks 4–5 у всіх чотирьох скриптах.

- [ ] **Step 1: Написати падаючий тест `tools/tests/RepoRoot.Tests.ps1`**

```powershell
#Requires -Version 7
BeforeAll {
    Import-Module "$PSScriptRoot/../lib/RepoRoot.psm1" -Force
}

Describe 'Resolve-V8RepoRoot' {
    BeforeEach {
        $script:tmp = Join-Path ([IO.Path]::GetTempPath()) ("v8kit-" + [guid]::NewGuid())
        New-Item -ItemType Directory -Path $script:tmp | Out-Null
    }
    AfterEach {
        Remove-Item -LiteralPath $script:tmp -Recurse -Force -ErrorAction SilentlyContinue
    }

    It 'повертає абсолютний шлях для кореня з текою .git' {
        New-Item -ItemType Directory -Path (Join-Path $script:tmp '.git') | Out-Null
        Resolve-V8RepoRoot -Path $script:tmp | Should -Be (Resolve-Path $script:tmp).Path
    }

    It 'приймає .git-файл (git worktree)' {
        Set-Content -LiteralPath (Join-Path $script:tmp '.git') -Value 'gitdir: ../somewhere'
        Resolve-V8RepoRoot -Path $script:tmp | Should -Be (Resolve-Path $script:tmp).Path
    }

    It 'розвʼязує відносний шлях відносно поточної теки' {
        New-Item -ItemType Directory -Path (Join-Path $script:tmp '.git') | Out-Null
        Push-Location $script:tmp
        try { Resolve-V8RepoRoot -Path '.' | Should -Be (Resolve-Path $script:tmp).Path }
        finally { Pop-Location }
    }

    It 'кидає виняток на теці без .git' {
        { Resolve-V8RepoRoot -Path $script:tmp } | Should -Throw '*не є коренем git-репозиторію*'
    }

    It 'кидає виняток на неіснуючому шляху' {
        { Resolve-V8RepoRoot -Path (Join-Path $script:tmp 'нема') } | Should -Throw
    }
}
```

- [ ] **Step 2: Запустити — переконатися, що падає**

Run: `pwsh -NoProfile -Command "Import-Module Pester -MinimumVersion 5.0; Invoke-Pester tools/tests/RepoRoot.Tests.ps1 -Output Detailed"`
Expected: FAIL — модуль `RepoRoot.psm1` не існує.

- [ ] **Step 3: Написати `tools/lib/RepoRoot.psm1`**

```powershell
#Requires -Version 7
Set-StrictMode -Version Latest

function Resolve-V8RepoRoot {
    <#
    .SYNOPSIS
        Розв'язує -RepoRoot скриптів kit і перевіряє, що це корінь git-репозиторію.
    .DESCRIPTION
        Скрипти kit живуть у плагіні, а не всередині репо-споживача, тому корінь
        передається параметром (типово '.'). Fail-closed: не-git тека зупиняє роботу
        до будь-якого читання чи запису — у дусі guard-перевірок storage-sync.
        .git може бути і текою (звичайний клон), і файлом (git worktree).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)

    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if (-not (Test-Path -LiteralPath (Join-Path $resolved '.git'))) {
        throw "'$resolved' не є коренем git-репозиторію (немає .git). " +
              'Запустіть із кореня репо-споживача або передайте -RepoRoot явно.'
    }
    return $resolved
}

Export-ModuleMember -Function Resolve-V8RepoRoot
```

- [ ] **Step 4: Запустити тести — зелені**

Run: `pwsh -NoProfile -Command "Import-Module Pester -MinimumVersion 5.0; Invoke-Pester tools/tests/RepoRoot.Tests.ps1 -Output Detailed"`
Expected: PASS, 5 passed.

- [ ] **Step 5: Повний прогін і коміт**

Run: `pwsh -NoProfile -File tools/tests/Run-Tests.ps1 -ExcludeTag Integration`
Expected: PASS, 0 failed.

```bash
git add tools/lib/RepoRoot.psm1 tools/tests/RepoRoot.Tests.ps1
git commit -m "RepoRoot.psm1: Resolve-V8RepoRoot — корінь репо-споживача параметром, fail-closed"
```

---

### Task 4: Параметр -RepoRoot у чотирьох скриптах

**Files:**
- Modify: `tools/storage-sync.ps1:10-20`
- Modify: `tools/dump-config.ps1:9-18`
- Modify: `tools/load-ext.ps1:9-19`
- Modify: `tools/build.ps1:13-22`

**Interfaces:**
- Consumes: `Resolve-V8RepoRoot` з Task 3.
- Produces: усі 4 скрипти приймають `[string]$RepoRoot = '.'`; `$repoRoot` усередині — розв'язаний абсолютний шлях. Скіли (Tasks 8–10) і шаблони (Task 6) покладаються на це.

- [ ] **Step 1: storage-sync.ps1 — параметр і розв'язання кореня**

У `param(...)` (рядки 10–15) додати параметр останнім:

```powershell
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Product,
    [switch]$Apply,
    [int]$MaxVersions = 0,
    [string]$StorageUser = 'gitbot',
    [string]$RepoRoot = '.'
)
```

Рядок 20 `$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')` замінити на:

```powershell
Import-Module (Join-Path $PSScriptRoot 'lib/RepoRoot.psm1') -Force
$repoRoot = Resolve-V8RepoRoot -Path $RepoRoot
```

(Імпорт RepoRoot — до інших імпортів; він нічого вкладено не імпортує, порядок із
ModuleImportOrder.Tests.ps1 не порушується.)

- [ ] **Step 2: dump-config.ps1 — те саме**

У `param(...)` додати `[string]$RepoRoot = '.'` останнім. Рядок 18
`$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')` замінити на ті самі два рядки
(Import-Module RepoRoot + Resolve-V8RepoRoot).

- [ ] **Step 3: load-ext.ps1 — те саме**

У `param(...)` додати `[string]$RepoRoot = '.'` останнім. Рядок 19 — та сама заміна.

- [ ] **Step 4: build.ps1 — те саме**

У `param(...)` додати `[string]$RepoRoot = '.'` останнім. Рядок 22 — та сама заміна.

- [ ] **Step 5: Оновити .EXAMPLE у довідках чотирьох скриптів**

У кожному з чотирьох скриптів у блоці `<# ... #>` замінити приклади виду
`pwsh tools/storage-sync.ps1 -Product BankExchange_SMB` на канонічну форму:

```
pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/storage-sync.ps1" -RepoRoot . -Product <Продукт>
pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/storage-sync.ps1" -RepoRoot . -Product <Продукт> -Apply
```

- [ ] **Step 6: Скриптовий тест на відмову поза git-коренем**

Додати в кінець `tools/tests/RepoRoot.Tests.ps1`:

```powershell
Describe 'Скрипти відмовляють на не-git RepoRoot' {
    It '<name> зупиняється до будь-якої роботи' -ForEach @(
        @{ name = 'storage-sync.ps1'; extra = @('-Product', 'X') }
        @{ name = 'dump-config.ps1'; extra = @('-Product', 'X') }
        @{ name = 'load-ext.ps1';    extra = @('-Product', 'X') }
        @{ name = 'build.ps1';       extra = @() }
    ) {
        $tmp = Join-Path ([IO.Path]::GetTempPath()) ("v8kit-norepo-" + [guid]::NewGuid())
        New-Item -ItemType Directory -Path $tmp | Out-Null
        try {
            $script = Resolve-Path "$PSScriptRoot/../$name"
            $out = & pwsh -NoProfile -File $script @extra -RepoRoot $tmp 2>&1 | Out-String
            $LASTEXITCODE | Should -Not -Be 0
            $out | Should -Match 'не є коренем git-репозиторію'
        }
        finally { Remove-Item -LiteralPath $tmp -Recurse -Force }
    }
}
```

- [ ] **Step 7: Прогін і коміт**

Run: `pwsh -NoProfile -File tools/tests/Run-Tests.ps1 -ExcludeTag Integration`
Expected: PASS (нові 4 кейси зелені, решта не зачеплена — StorageSync.Tests.ps1 тестує функції lib-модулів, не запуск скриптів).

```bash
git add tools/*.ps1 tools/tests/RepoRoot.Tests.ps1
git commit -m "-RepoRoot у чотирьох скриптах: корінь репо-споживача параметром замість \$PSScriptRoot/.."
```

---

### Task 5: build.ps1 — виявлення продуктів замість вшитого списку

**Files:**
- Modify: `tools/build.ps1:30-32`
- Create: `tools/tests/Build.Tests.ps1`

**Interfaces:**
- Consumes: `-RepoRoot` з Task 4.
- Produces: `build.ps1` без аргументу `-Product` збирає всі теки з `storage.json` у корені репо + `epf` (якщо існує `epf/src`). Скіл storage-pipeline (Task 8) описує саме цю поведінку.

- [ ] **Step 1: Написати падаючий тест `tools/tests/Build.Tests.ps1`**

Прев'ю-режим (без `-Apply`) не звертається до платформи — тест суто файловий:

```powershell
#Requires -Version 7
Describe 'build.ps1 — виявлення продуктів' {
    BeforeEach {
        $script:tmp = Join-Path ([IO.Path]::GetTempPath()) ("v8kit-build-" + [guid]::NewGuid())
        New-Item -ItemType Directory -Path (Join-Path $script:tmp '.git') -Force | Out-Null
        $script:build = (Resolve-Path "$PSScriptRoot/../build.ps1").Path
    }
    AfterEach {
        Remove-Item -LiteralPath $script:tmp -Recurse -Force -ErrorAction SilentlyContinue
    }

    It 'знаходить теки зі storage.json і epf/src' {
        foreach ($p in 'Alpha_SMB', 'Beta_ACC') {
            New-Item -ItemType Directory -Path (Join-Path $script:tmp $p) | Out-Null
            Set-Content -LiteralPath (Join-Path $script:tmp $p 'storage.json') -Value '{}'
        }
        New-Item -ItemType Directory -Path (Join-Path $script:tmp 'epf/src') -Force | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $script:tmp 'NoStorage') | Out-Null

        $out = & pwsh -NoProfile -File $script:build -RepoRoot $script:tmp 2>&1 | Out-String
        $LASTEXITCODE | Should -Be 0
        $out | Should -Match 'Alpha_SMB'
        $out | Should -Match 'Beta_ACC'
        $out | Should -Match 'epf'
        $out | Should -Not -Match 'NoStorage'
    }

    It 'зупиняється, коли продуктів немає' {
        $out = & pwsh -NoProfile -File $script:build -RepoRoot $script:tmp 2>&1 | Out-String
        $LASTEXITCODE | Should -Not -Be 0
        $out | Should -Match 'жодного продукту'
    }

    It 'явний -Product передається як є' {
        $out = & pwsh -NoProfile -File $script:build -RepoRoot $script:tmp -Product 'Gamma_SMB' 2>&1 | Out-String
        $LASTEXITCODE | Should -Be 0
        $out | Should -Match 'Gamma_SMB'
    }
}
```

- [ ] **Step 2: Запустити — падає**

Run: `pwsh -NoProfile -Command "Import-Module Pester -MinimumVersion 5.0; Invoke-Pester tools/tests/Build.Tests.ps1 -Output Detailed"`
Expected: FAIL — вивід містить BankExchange_SMB (вшитий список), а не Alpha_SMB.

- [ ] **Step 3: Замінити вшитий список у build.ps1**

Рядки 30–32:

```powershell
$products = if ($Product) { @($Product) } else {
    @('BankExchange_SMB', 'BankExchange_SMBru', 'BankExchange_ACC', 'epf')
}
```

замінити на:

```powershell
# Продукт — тека з storage.json у корені репо; epf — за наявності epf/src.
# Вшитого списку немає: kit обслуговує будь-який репозиторій цієї схеми.
$products = if ($Product) { @($Product) } else {
    $found = @(Get-ChildItem -LiteralPath $repoRoot -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'storage.json') } |
        Sort-Object Name | Select-Object -ExpandProperty Name)
    if (Test-Path -LiteralPath (Join-Path $repoRoot 'epf/src')) { $found += 'epf' }
    if (-not $found) {
        throw "У $repoRoot не знайдено жодного продукту: ні теки зі storage.json, ні epf/src."
    }
    $found
}
```

- [ ] **Step 4: Прогін і коміт**

Run: `pwsh -NoProfile -File tools/tests/Run-Tests.ps1 -ExcludeTag Integration`
Expected: PASS.

```bash
git add tools/build.ps1 tools/tests/Build.Tests.ps1
git commit -m "build.ps1: виявлення продуктів за storage.json замість вшитого списку BankExchange"
```

---

### Task 6: templates/ — файли репо-споживача

**Files:**
- Create: `templates/CLAUDE.md`
- Create: `templates/gitattributes` (без крапки — щоб не діяв на сам kit; при міграції копіюється як `.gitattributes`)
- Create: `templates/gitignore` (так само)
- Create: `templates/settings.json`
- Create: `templates/storage.json.example`

**Interfaces:**
- Consumes: канонічну форму виклику з Task 4.
- Produces: шаблони, які скіли repo-migration і product-onboarding (Tasks 9–10) копіюють у репо-споживач.

- [ ] **Step 1: `templates/gitattributes` — копія з BankExchange**

Скопіювати `R:\github\SMP_BankExchange\.gitattributes` байт-у-байт (уся EOL-політика
критична для clean-tree guard — пояснення в самому файлі й у docs kit).

- [ ] **Step 2: `templates/gitignore`**

Копія `R:\github\SMP_BankExchange\.gitignore` без рядка `.superpowers/` (специфіка
BankExchange; додається окремо, якщо в репо-споживачі ведеться робота superpowers):

```gitignore
# Вендорські конфігурації — не наш код, у публічний репозиторій не потрапляють.
# Ігнорується вміст теки, а не сама тека, інакше README.md неможливо було б закомітити.
**/cf/**
!**/cf/README.md

# Робочі каталоги
build/
.build/

# Локальні перевизначення з підключеннями й логінами
v8project.local.yaml

# Побічні файли платформи
ConfigDumpInfo.xml
DumpFilesIndex.txt
```

- [ ] **Step 3: `templates/storage.json.example`**

```json
{
  "storagePath": "R:\\СховищаРозширень_1С\\<ІмʼяСховища>",
  "extensionName": "<ІмʼяРозширенняВ1С>",
  "lastSyncedVersion": 0,
  "sourcePath": "cfe/src"
}
```

- [ ] **Step 4: `templates/settings.json`**

За зразком `R:\github\SMP_BankExchange\.claude\settings.json`: скопіювати його повністю і
замінити рядок `"Bash(pwsh -NoProfile -File tools/tests/Run-Tests.ps1 -ExcludeTag Integration)"`
на нічого (тести живуть у kit, з репо-споживача їх не запускають). Блоки `ask`
(`git push`, `gh pr create`, `gh release`) і `deny` (`gitsync`, `oscript`) — без змін.
Прев'ю конвеєрних скриптів свідомо НЕ в allow: правила працюють за префіксом, і дозвіл
на прев'ю автоматично дозволив би той самий рядок із `-Apply` (політика BankExchange,
розділ «Дозволи» CLAUDE.md). Якщо Task 11 підтвердить гіпотезу про стабільний
літеральний префікс — цей файл НЕ розширюється: гіпотеза стосується зручності
майбутніх точкових дозволів, а не стартового набору.

- [ ] **Step 5: `templates/CLAUDE.md`**

Скелет за структурою CLAUDE.md BankExchange; плейсхолдери в кутових дужках заповнює
скіл міграції:

```markdown
# <ІмʼяРепозиторію> — інструкції проєкту

<Один абзац: що це за підсистема, для яких конфігурацій.>

Конвеєр «сховище ↔ git» — плагін Claude Code `v8storagekit`
(https://github.com/VSydorenko/SMP_V8StorageKit). Скіли плагіна знають щоденний цикл,
підключення продукту й міграцію; архітектура контуру — в docs плагіна.

## Структура

| Тека | Що це | Ім'я розширення в 1С |
|---|---|---|
| `<Продукт>/` | <базова конфігурація, мова> | `<ІмʼяРозширення>` |

Усередині продукту: `cfe/src` (вихідники, Designer XML — у git), `cf/` (базова
конфігурація — gitignored, крім README.md), `v8project.yaml` (воркспейс Unica),
`v8project.local.yaml` (gitignored: підключення й логіни), `storage.json` (сховище,
ім'я розширення, остання залита версія).

## Межі

- **Формат вихідників — тільки Designer platform XML.** EDT не використовується.
- **Платформа — тільки гілка 8.3.27.x.**
- **Репозиторій публічний.** Рядки підключення, імена серверів 1С, логіни й паролі не
  потрапляють у закомічені файли — тільки у `v8project.local.yaml` (gitignored).
  Єдиний свідомий виняток — `storagePath` у `storage.json` (шлях сам собою не дає
  доступу ні до чого).
- **`cf/` ніколи не комітиться** — код вендора, ліцензія цього не дозволяє.
- **Сховища конфігурацій — тільки читання.** Жодних `ConfigurationRepositoryCommit`,
  `ConfigurationRepositoryLock`, `ConfigurationRepositoryUnlockObjects`. Запис у
  сховище виконує людина в Конфігураторі.
- **Мутуючі скрипти без `-Apply` нічого не змінюють.** Ставити `-Apply` лише коли
  користувач явно попросив виконати.
- **Ліцензія 1С.** Якщо у виводі платформи є `лиценз`, `license`, `HASP`, `No license`
  — зупинись і скажи користувачу.

## Типові операції

```powershell
pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/storage-sync.ps1" -RepoRoot . -Product <Продукт>          # перегляд нових версій сховища
pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/storage-sync.ps1" -RepoRoot . -Product <Продукт> -Apply   # перенести їх у git
pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/dump-config.ps1"  -RepoRoot . -Product <Продукт> -Apply   # вивантажити базову конфігурацію
pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/load-ext.ps1"     -RepoRoot . -Product <Продукт> -Apply   # розкотити вихідники в дев-базу
pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/build.ps1"        -RepoRoot . -Apply                      # зібрати .cfe (та .epf, якщо є)
```

## Дозволи

`.claude/settings.json` дозволяє без запиту лише читання. Запуски конвеєрних скриптів
(і прев'ю, і `-Apply`) — з підтвердженням: правила дозволів працюють за префіксом, і
дозвіл на прев'ю автоматично дозволив би `-Apply`. `gitsync` і `oscript` заборонені.
`git push`, `gh pr create`, `gh release` — завжди з підтвердженням.

## Робота через Unica

**Воркспейс — тека продукту, не корінь репозиторію** (автоскан Unica падає на першому
не-UTF-8 файлі; вузький корінь тримає BSL-індекс малим). Обмеження маршруту: `dump` на
Windows fail-closed — вивантажує Конфігуратор через скрипти плагіна; `make` для
`.epf`/`.cfe` на Windows падає на публікації артефакту — збирає `build.ps1` плагіна;
`cfe.borrow` і `cfe.diff` потребують вивантаженої `cf/src`.
```

- [ ] **Step 6: Commit**

```bash
git add templates/
git commit -m "templates/: файли репо-споживача — CLAUDE.md, gitattributes, gitignore, settings.json, storage.json.example"
```

---

### Task 7: docs/ kit — узагальнена архітектура контуру

**Files:**
- Create: `docs/storage-and-git.md`

**Interfaces:**
- Produces: документ, на який посилаються скіли (Tasks 8–10) замість дублювання пояснень.

- [ ] **Step 1: Створити `docs/storage-and-git.md` копіюванням-адаптацією**

Джерело: `R:\github\SMP_BankExchange\docs\architecture\storage-and-git.md`. Перенести
**без змін по суті** розділи (прибравши лише прив'язки до конкретних продуктів
BankExchange у прикладах — замінити на `<Продукт>`):

1. «Три напрямки і чому вони асиметричні» — цілком (таблиця напрямків, чому
   «база → сховище» ніколи не автоматичний).
2. «storage.json» — цілком (таблиця полів, відсутність пароля, `-StorageUser gitbot`).
3. «AUTHORS» — цілком (формат рядка, зупинка на невідомих іменах і чому).
4. «Захист від розбіжності» — цілком (три перевірки + Assert-SafeWorkPath + зв'язок
   clean-tree guard з `.gitattributes`).
5. «Три трейлери коміту» — базова частина (Storage-Version / Extension-Version /
   Storage-User і навіщо сирий рядок), без BankExchange-специфічних підрозділів про
   вісім replay-комітів і клієнтські бази.
6. «Перший прогін продукту — два коміти, не один» — цілком.
7. «Пряме обмеження на локальні шляхи розробників» — цілком (політика storagePath +
   перевизначення у v8project.local.yaml).
8. «Особливості платформи, на яких легко втратити час» — цілком, включно з розділом
   про обрізання коментарів на `//` (без BankExchange-специфічної статистики
   відновлених версій — лишити механізм і ключ `-IncludeCommentLinesWithDoubleSlash`).

НЕ переносити: «Хто володіє якою текою build» (специфіка дерева BankExchange — але
додати короткий абзац: скрипти kit працюють у `build/` репо-споживача, Unica тримає
`<продукт>/build/` і `<продукт>/.build/unica`), «Виняток: вісім найперших
replay-комітів», «Тимчасове зіставлення дев'яти версій».

- [ ] **Step 2: Перевірити відсутність секретів і згадок продуктів BankExchange**

Run: `pwsh -NoProfile -Command "Select-String -Path docs/storage-and-git.md -Pattern 'BankExchange_(SMB|ACC)' | Measure-Object | Select-Object -ExpandProperty Count"`
Expected: 0 (згадка репозиторію-походження в преамбулі допустима, конкретні продукти — ні).

- [ ] **Step 3: Commit**

```bash
git add docs/
git commit -m "docs/storage-and-git.md: узагальнена архітектура контуру (перенесено з BankExchange)"
```

---

### Task 8: Скіл storage-pipeline

**Files:**
- Create: `skills/storage-pipeline/SKILL.md`

**Interfaces:**
- Consumes: канонічну форму виклику (Task 4), поведінку build.ps1 (Task 5), docs (Task 7).
- Produces: скіл, який Task 11 перевіряє на «чужому» порожньому репо, а Task 13 — на BankExchange.

- [ ] **Step 1: Написати `skills/storage-pipeline/SKILL.md`**

Frontmatter:

```yaml
---
name: storage-pipeline
description: Щоденний цикл конвеєра «сховище 1С ↔ git» — перенести нові версії сховища в git, вивантажити базову конфігурацію, розкотити розширення в дев-базу, зібрати .cfe/.epf. Тригери — «сховище», «синхронізація», «перенеси версії», «вивантаж конфігурацію», «розкоти розширення», «збери cfe/epf», «storage sync».
---
```

Тіло скіла — обов'язкові розділи з конкретним змістом:

1. **Виявлення контексту.** Продукт = тека з `storage.json` у корені репо. Немає жодної
   → репо не підключене: запропонувати скіл repo-migration (старий формат упізнається за
   квартетом `AUTHORS`+`VERSION`+`DT-INF/`+`ConfigDumpInfo.xml`) або product-onboarding.
   Кілька product-тек і промпт не уточнює яка → спитати користувача (AskUserQuestion зі
   списком знайдених).
2. **Канонічні команди** — п'ять рядків із `templates/CLAUDE.md` (Task 6, розділ
   «Типові операції») дослівно.
3. **Правило -Apply**: без `-Apply` — завжди можна (прев'ю нічого не змінює); `-Apply`
   — лише коли користувач явно попросив виконати. Перед `-Apply` показати користувачу
   прев'ю.
4. **Штатні зупинки** (не помилки скіла, розбір за людиною): брудна робоча копія
   продукту перед `-Apply`; `lastSyncedVersion` більший за максимум сховища; невідомі
   автори — вивід містить готові рядки для `AUTHORS`, додати їх має людина (пояснити
   чому: мовчазна підстановка зіпсувала б авторство десятків комітів).
5. **Перший прогін продукту** — два коміти: спершу `storage.json` окремим комітом, лише
   потім `-Apply` (посилання на docs/storage-and-git.md, розділ «Перший прогін»).
6. **Ліцензія 1С**: `лиценз`/`license`/`HASP`/`No license` у виводі платформи →
   зупинитись і сказати користувачу.
7. **Посилання**: `$env:CLAUDE_PLUGIN_ROOT/docs/storage-and-git.md` — архітектура й
   особливості платформи.

- [ ] **Step 2: Самоперевірка скіла**

Прочитати SKILL.md очима агента без контексту: чи відповідає він на «перенеси нові
версії сховища в git» однозначною командою? Чи каже, що робити, коли продуктів кілька /
жодного? Чи заборонено самовільний `-Apply`? Якщо ні — виправити.

- [ ] **Step 3: Commit**

```bash
git add skills/storage-pipeline/
git commit -m "storage-pipeline: скіл щоденного циклу конвеєра"
```

---

### Task 9: Скіл product-onboarding

**Files:**
- Create: `skills/product-onboarding/SKILL.md`

**Interfaces:**
- Consumes: templates (Task 6), docs (Task 7).
- Produces: скіл підключення нового продукту в уже мігрованому репо.

- [ ] **Step 1: Написати `skills/product-onboarding/SKILL.md`**

Frontmatter:

```yaml
---
name: product-onboarding
description: Підключити новий продукт (розширення 1С) до конвеєра «сховище ↔ git» в уже налаштованому репозиторії — створити теку продукту, storage.json, v8project.yaml, перший коміт. Тригери — «підключи продукт», «додай розширення до синхронізації», «новий продукт у репо».
---
```

Обов'язковий зміст:

1. **Передумова**: репо вже мігроване (є `.gitattributes` kit і хоча б структура; якщо
   в корені квартет старого формату — це repo-migration, не сюди).
2. **Що спитати** (одним AskUserQuestion, не серією): шлях до сховища (перед питанням
   проскануати `R:\СховищаРозширень_1С` — якщо тека існує, запропонувати підтеки як
   варіанти); ім'я розширення в 1С; назву теки продукту за конвенцією
   `<Продукт>_<КодКонфігурації>` (приклади: `BankExchange_SMB`, `SimplyConnect_SMBru`).
3. **Що створити**: теку продукту; `storage.json` з `templates/storage.json.example`
   (заповнити відповіді, `lastSyncedVersion: 0` для replay з першої версії або
   значення, яке назвав користувач); `cf/README.md` (один рядок: «Базова конфігурація
   вивантажується локально, у git не потрапляє»); `v8project.yaml` за зразком сусіднього
   продукту цього ж репо, а якщо продукт перший — за прикладом з docs плагіна.
   Нагадати користувачу про gitignored `v8project.local.yaml` (підключення дев-бази —
   руками, логіни в git не потрапляють).
4. **Перший коміт**: `storage.json` + `cf/README.md` + `v8project.yaml` одним комітом
   ДО будь-якого `-Apply` (clean-tree guard інакше зупинить прогін — пояснити).
5. **Далі** — передати у storage-pipeline: прев'ю, за явним запитом `-Apply`.

- [ ] **Step 2: Самоперевірка скіла** — ті самі критерії, що в Task 8 Step 2.

- [ ] **Step 3: Commit**

```bash
git add skills/product-onboarding/
git commit -m "product-onboarding: скіл підключення нового продукту"
```

---

### Task 10: Скіл repo-migration

**Files:**
- Create: `skills/repo-migration/SKILL.md`

**Interfaces:**
- Consumes: templates (Task 6), docs (Task 7), скіли Tasks 8–9.
- Produces: плейбук міграції старого gitsync-репо; перевіряється на пілоті (окремий план, етап 3 спеки).

- [ ] **Step 1: Написати `skills/repo-migration/SKILL.md`**

Frontmatter:

```yaml
---
name: repo-migration
description: Мігрувати старий gitsync-репозиторій 1С (EDT-вихідники, AUTHORS+VERSION+DT-INF+ConfigDumpInfo.xml) на схему «продукт/cfe/src + storage.json + плагін v8storagekit» з чистою replay-гілкою історії сховища. Тригери — «мігруй репо», «підключи репозиторій до конвеєра», «переведи на нову схему», «перезапуск репо».
---
```

Обов'язковий зміст — плейбук по слідах `restructure/2026-08` BankExchange, кожен крок
з командою або точною дією:

1. **Розвідка** (read-only): знайти всі продукти за квартетом
   `AUTHORS`+`VERSION`+`DT-INF/`+`ConfigDumpInfo.xml` (він може бути в корені або у
   вкладених теках); прочитати `VERSION` (остання синхронізована версія сховища) і
   `AUTHORS`; показати користувачу знайдене.
2. **Що спитати** (одним AskUserQuestion): шлях до сховища кожного продукту
   (запропонувати кандидатів з `R:\СховищаРозширень_1С`); ім'я розширення; replay з
   версії 1 чи продовжити з `VERSION` (пояснити: replay з 1 дає повну історію в новій
   структурі, продовження — коротшу гілку, стара історія лишається в старій гілці);
   назви продуктових тек; що з продуктами-плейсхолдерами (порожні теки — підключати чи
   позначити «пізніше» в CLAUDE.md).
3. **Страхувальний bundle** (перед будь-якими змінами):
   `git bundle create <репо>-pre-migration-<дата>.bundle --all` у `build/` або поруч із
   репо; `git bundle verify` — перевірити.
4. **Локальний git-конфіг**: `git config core.longpaths true`,
   `git config core.quotepath false` (кириличні шляхи, > 260 символів; ці налаштування
   не переносяться клоном — виставляти в кожному клоні).
5. **Чиста гілка**: `git checkout --orphan restructure/<YYYY-MM>`; очистити індекс і
   робочу копію від старого дерева (старі гілки не переписуються й не видаляються).
6. **Каркас репо**: скопіювати з `$env:CLAUDE_PLUGIN_ROOT/templates/`: `gitattributes`
   → `.gitattributes`, `gitignore` → `.gitignore`, `settings.json` →
   `.claude/settings.json`, `CLAUDE.md` → `CLAUDE.md` (заповнити плейсхолдери
   відповідями користувача); перенести `AUTHORS` зі старого дерева в корінь. Закомітити
   каркас.
7. **Кожен продукт** — за скілом product-onboarding (тека, `storage.json` з
   `lastSyncedVersion` = 0 або `VERSION`, окремий перший коміт), потім
   `storage-sync.ps1 -Apply` — replay історії. Нагадування: невідомі автори зупинять
   прогін — це очікувано, рішення по кожному імені за людиною; прогін можна повторювати,
   він продовжить з місця зупинки.
8. **Перевірка**: `git log --format='%h %ad %an %s' --date=short` на гілці — коміти
   несуть трейлери `Storage-Version`/`Extension-Version`/`Storage-User`
   (`git log --grep='Storage-Version'`); `storage-sync` прев'ю каже «Нових версій немає».
9. **Що НЕ робить скіл**: не пушить (git push — завжди рішення людини), не видаляє
   старі гілки, не чіпає сховище (тільки читання), не переписує стару історію.
10. **Особливі випадки**: репо, вкладене в само-іменовану теку (як
    `SMP_OnlineExchange/SMP_OnlineExchange`) — нова структура будується від кореня
    репо, стара тека лишається тільки в старих гілках; C++/не-1С теки (як аддін у
    SimplyConnect) — не чіпати, згадати в CLAUDE.md; репо з повними конфігураціями
    (`cf` як продукт, не розширення) — поза можливостями поточної версії kit,
    зупинитись і сказати користувачу (відкрите питання спеки §10).

- [ ] **Step 2: Самоперевірка скіла** — прочитати як агент у чужому старому репо: чи
кожен крок має точну команду або точне питання? Чи явно заборонені push і запис у
сховище?

- [ ] **Step 3: Commit**

```bash
git add skills/repo-migration/
git commit -m "repo-migration: плейбук міграції старого gitsync-репо"
```

---

### Task 11: Смоук плагіна, перевірка гіпотез, пуш

**Files:**
- Modify (за результатами): `skills/*/SKILL.md`, `templates/settings.json`, `README.md`

**Interfaces:**
- Consumes: усе з Tasks 1–10.
- Produces: встановлений на машині плагін `v8storagekit@smp-v8storagekit`; підтверджені або спростовані гіпотези §7 спеки — від цього залежить фінальний текст шаблонів.

- [ ] **Step 1: Додати локальний маркетплейс і встановити плагін**

Run: `claude plugin marketplace add R:\github\SMP_V8StorageKit`
Run: `claude plugin install v8storagekit@smp-v8storagekit`
Expected: обидві команди успішні; `claude plugin list` (або `/plugin` у сесії) показує
`v8storagekit`. Якщо схема marketplace.json невалідна — команда скаже, що саме;
виправити і повторити.

- [ ] **Step 2: Гіпотеза 1 — `$env:CLAUDE_PLUGIN_ROOT` у Bash-викликах**

У новій сесії Claude Code в будь-якій теці попросити виконати скіл-команду (наприклад,
«покажи нові версії сховища» у BankExchange). Спостерігати фактичний Bash-виклик:
чи `$env:CLAUDE_PLUGIN_ROOT` розв'язався в шлях кешу плагіна.
Expected: скрипт знайдено і запущено. Якщо змінна НЕ визначена в Bash-контексті —
змінити канонічну форму в скілах на підстановку `${CLAUDE_PLUGIN_ROOT}` у самому тексті
SKILL.md (Claude Code підставляє її при завантаженні скіла; модель тоді пише в команду
вже готовий абсолютний шлях) і оновити Task 6/8/9/10-файли відповідно, окремим комітом
`"Канонічна форма виклику: \${CLAUDE_PLUGIN_ROOT} підставляється при завантаженні скіла"`.

- [ ] **Step 3: Гіпотеза 2 — стабільність префіксного правила дозволів**

У тестовому репо додати в `.claude/settings.local.json` правило з літеральним префіксом
канонічної форми (точний текст — як фактично виглядав Bash-виклик у Step 2) і повторити
прев'ю-виклик.
Expected: виконується без запиту дозволу. Зафіксувати результат обох гіпотез у
`README.md` kit (розділ «Дозволи в репо-споживачах»: що працює, що ні, який fallback).

- [ ] **Step 4: Приймальний тест спеки — «чуже» порожнє репо**

У порожньому git-репо (створити тимчасове) спитати агента «перенеси нові версії
сховища в git».
Expected: агент через скіл storage-pipeline виявляє відсутність `storage.json` і
квартету, пояснює, що репо не підключене, і пропонує repo-migration/product-onboarding
— не вигадує команд і не запускає нічого.

- [ ] **Step 5: Закомітити правки за результатами, пуш**

```bash
git add -A && git commit -m "Смоук: результати перевірки гіпотез CLAUDE_PLUGIN_ROOT і префіксних дозволів"
git push -u origin main
```

(`git push` — з підтвердженням користувача. Після пушу перемкнути маркетплейс з
локальної теки на GitHub: `claude plugin marketplace remove smp-v8storagekit`,
`claude plugin marketplace add VSydorenko/SMP_V8StorageKit`, перевстановити плагін —
щоб надалі оновлення йшли через `/plugin update` з GitHub.)

---

### Task 12: BankExchange — бейзлайн перед переходом

Робочий каталог: `R:\github\SMP_BankExchange`.

**Files:**
- Create (scratchpad, поза репо): `baseline-sync-SMB.txt`, `baseline-sync-SMBru.txt`, `baseline-sync-ACC.txt`

**Interfaces:**
- Produces: еталонні виводи прев'ю для порівняння в Task 13.

- [ ] **Step 1: Тести локального tools/ зелені**

Run: `pwsh -NoProfile -File tools/tests/Run-Tests.ps1 -ExcludeTag Integration`
Expected: PASS.

- [ ] **Step 2: Зафіксувати прев'ю трьох продуктів (локальний tools/)**

```powershell
$bl = New-Item -ItemType Directory -Path "$env:TEMP\v8storagekit-baseline" -Force
pwsh tools/storage-sync.ps1 -Product BankExchange_SMB   *> "$bl\baseline-sync-SMB.txt"
pwsh tools/storage-sync.ps1 -Product BankExchange_SMBru *> "$bl\baseline-sync-SMBru.txt"
pwsh tools/storage-sync.ps1 -Product BankExchange_ACC   *> "$bl\baseline-sync-ACC.txt"
```

(Стабільна тека поза репо: Task 13 може виконуватись іншою сесією і читає ці ж файли.)
Expected: кожен вивід закінчується або «Нових версій немає», або списком версій і
«Це попередній перегляд» — без винятків.

---

### Task 13: BankExchange — перший споживач: видалити tools/, перейти на плагін

Робочий каталог: `R:\github\SMP_BankExchange`, гілка `restructure/2026-08`.

**Files:**
- Delete: `tools/` (цілком)
- Modify: `CLAUDE.md` (розділи «Типові операції», «Дозволи»)
- Modify: `.claude/settings.json:14`

**Interfaces:**
- Consumes: встановлений плагін (Task 11), бейзлайни (Task 12).

- [ ] **Step 1: Видалити tools/**

```bash
git rm -r tools
```

- [ ] **Step 2: CLAUDE.md — «Типові операції» на канонічну форму**

Замінити блок команд у розділі «Типові операції» на:

```powershell
pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/storage-sync.ps1" -RepoRoot . -Product BankExchange_SMB          # перегляд нових версій сховища
pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/storage-sync.ps1" -RepoRoot . -Product BankExchange_SMB -Apply   # перенести їх у git
pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/dump-config.ps1"  -RepoRoot . -Product BankExchange_SMB -Apply   # вивантажити базову конфігурацію
pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/load-ext.ps1"     -RepoRoot . -Product BankExchange_SMB -Apply   # розкотити вихідники в дев-базу
pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/build.ps1"        -RepoRoot . -Apply                             # зібрати .cfe та .epf
```

(канонічна форма — та, яку підтвердив Task 11 Step 2; якщо гіпотеза 1 спростована —
форма зі скілів після правки). Додати рядок перед блоком: «Конвеєр — плагін
`v8storagekit` (VSydorenko/SMP_V8StorageKit); тести конвеєра живуть і ганяються в
репозиторії плагіна.»

- [ ] **Step 3: CLAUDE.md — «Дозволи» без рядка тестів**

У розділі «Дозволи» прибрати речення про дозволений рядок прогону тестів з
`-ExcludeTag Integration` (M8) — тестів у репо більше немає; додати: «Тести конвеєра —
в репозиторії плагіна SMP_V8StorageKit». Згадку «Свідомо не в дозволених — запуски
storage-sync, dump-config, load-ext, build» лишити, прибравши слово `tools/` де воно
вжите як шлях.

- [ ] **Step 4: settings.json — прибрати правило тестів**

Видалити рядок 14: `"Bash(pwsh -NoProfile -File tools/tests/Run-Tests.ps1 -ExcludeTag Integration)",`
Решта без змін.

- [ ] **Step 5: Прев'ю через плагін — порівняти з бейзлайном**

```powershell
$bl = "$env:TEMP\v8storagekit-baseline"
pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/storage-sync.ps1" -RepoRoot . -Product BankExchange_SMB   *> "$bl\plugin-sync-SMB.txt"
pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/storage-sync.ps1" -RepoRoot . -Product BankExchange_SMBru *> "$bl\plugin-sync-SMBru.txt"
pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/storage-sync.ps1" -RepoRoot . -Product BankExchange_ACC   *> "$bl\plugin-sync-ACC.txt"
```

Порівняти кожен `plugin-sync-*.txt` з відповідним `baseline-sync-*.txt` (Task 12).
Expected: побайтово ідентичні (той самий продукт, сховище, версії, той самий вердикт).
Розбіжність = блокер: розібратися до коміту, не «прийняти як нову норму».

- [ ] **Step 6: Прев'ю build через плагін**

Run: `pwsh "$env:CLAUDE_PLUGIN_ROOT/tools/build.ps1" -RepoRoot .`
Expected: `Збирати: BankExchange_ACC, BankExchange_SMB, BankExchange_SMBru, epf` —
виявлення продуктів (Task 5) знайшло всі чотири цілі (порядок — за Sort-Object Name,
epf останній).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Перехід на плагін v8storagekit: tools/ видалено, CLAUDE.md і дозволи оновлено

Конвеєр живе в VSydorenko/SMP_V8StorageKit; прев'ю всіх трьох продуктів
звірено з бейзлайном до видалення — побайтово ідентичне."
```

---

## Поза цим планом

Етапи 3–4 спеки (пілотна міграція `SMP_OnlineExchange`, решта репозиторіїв, підтримка
повних конфігурацій для `SMP_SMB_*_DEV`) — окремі плани після приймання цього.
`docs/architecture/storage-and-git.md` у BankExchange лишається без змін (документ
рішень цього репо; узагальнений зміст уже перенесено в kit Task 7).

## Self-Review (виконано при написанні)

- Покриття спеки: §3 структура kit — Tasks 1–10; §3.1 копіювання + `-RepoRoot` — Tasks
  2–4 (+ виявлена при плануванні необхідна генералізація build.ps1 — Task 5, у дусі
  «адаптація за потреби» §3.1); §3.2 канонічна форма — Tasks 4/6/8, перевірка — Task 11;
  §5 три скіли — Tasks 8–10; §7 дозволи й гіпотеза — Tasks 6/11; §8.1 — Tasks 1–11;
  §8.2 — Tasks 12–13; §9 критерії — вбудовані у відповідні задачі.
- Плейсхолдерів «TBD/додати пізніше» немає; шаблони або наведені повністю, або задані
  джерелом копіювання з точним переліком розділів.
- Узгодженість імен: `Resolve-V8RepoRoot`, `-RepoRoot`, `v8storagekit`,
  `smp-v8storagekit` — однакові в усіх задачах.
