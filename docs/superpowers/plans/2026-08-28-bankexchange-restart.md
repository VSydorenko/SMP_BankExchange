# Перезапуск SMP_BankExchange — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести три розширення й обробки читання форматів у Designer platform XML, забрати зі сховищ ~30 незалитих версій із авторами й датами, і зібрати робочий контур Unica, у якому агент може розробляти далі.

**Architecture:** Власні PowerShell-скрипти в `tools/` викликають платформу 1С 8.3.27.1644 через `Start-Process`, читають історію сховищ зі звіту `/ConfigurationRepositoryReport` (формат MXL), вивантажують кожну версію в Designer XML і роблять git-коміт з автором, датою й коментарем зі сховища. Чисті функції (парсер MXL, мапінг авторів, обчислення відсутніх версій) винесені в модулі й покриті Pester-тестами; усе, що торкається платформи, ізольовано в одній обгортці.

**Tech Stack:** PowerShell 7.5.4, Pester 6.x, git 2.53, платформа 1С 8.3.27.1644, плагін Unica 0.12.3 (MCP).

**Spec:** `docs/superpowers/specs/2026-08-28-bankexchange-restart-design.md`

## Global Constraints

- **Платформа 1С — тільки гілка 8.3.27.x.** Виконуваний файл: `C:\Program Files\1cv8\8.3.27.1644\bin\1cv8.exe`. Unica інші гілки не підтримує; сховища створені саме цією версією.
- **Формат вихідників — Designer platform XML.** EDT у цьому репозиторії більше не використовується.
- **Репозиторій публічний.** Рядки підключення до баз, імена серверів 1С, логіни та локальні шляхи розробників не потрапляють у закомічені файли — лише у `v8project.local.yaml` (gitignored) і в пам'ять проєкту.
- **Сховища — тільки читання протягом усього плану.** Жодних `ConfigurationRepositoryCommit`, `Lock`, `UnlockObjects`. Запис у сховище виконує людина.
- **Гілка `restructure/2026-08`.** `main` не змінюється; злиття через Pull Request на GitHub.
- **Мова комітів і документації — українська.**
- **Запуск платформи — тільки через `Start-Process` з повністю зібраним рядком аргументів.** Нативний виклик PowerShell псує лапки; `/IBConnectionString` вимагає подвоєних лапок усередині, тому використовується `/F "<шлях>"` для файлових ІБ і `/S "<сервер>\<база>"` для серверних.
- **`-Extension <Ім'я>` належить команді-дії** (`/ConfigurationRepositoryReport`, `/ConfigurationRepositoryUpdateCfg`, `/DumpConfigToFiles`, `/LoadConfigFromFiles`), а не `/ConfigurationRepositoryF`.
- **Розширення має існувати в ІБ до звернення до сховища.** У порожню базу спершу вантажиться стаб із `tools/assets/empty-extension`.
- **Ліцензія 1С.** Якщо у виводі платформи трапиться `лиценз`, `license`, `HASP` або `No license` — зупинитись і повідомити користувача. Не чіпати служби, реєстр, файли ліцензій.
- **Мутуючі операції за замовчуванням у режимі попереднього перегляду.** Скрипти виконують зміни лише з явним `-Apply`.

---

## Мапа файлів

| Файл | Відповідальність |
|---|---|
| `tools/lib/V8.psm1` | єдина точка запуску `1cv8.exe`: пошук платформи, перетворення рядка підключення в ключ `/F`/`/S`, виклик Конфігуратора, створення файлової ІБ |
| `tools/lib/StorageReport.psm1` | читання MXL-звіту сховища й перетворення його на об'єкти версій |
| `tools/lib/Authors.psm1` | мапінг «ім'я користувача у сховищі → git-автор» з файла `AUTHORS` |
| `tools/lib/SyncState.psm1` | читання й запис `storage.json`, обчислення переліку незалитих версій |
| `tools/assets/empty-extension/` | мінімальний scaffold розширення, який вантажиться в порожню ІБ під потрібним іменем |
| `tools/storage-sync.ps1` | оркестрація «сховище → git»: звіт → версії → вивантаження → коміти |
| `tools/dump-config.ps1` | вивантаження базової конфігурації з дев-бази в `<продукт>/cf/src` |
| `tools/load-ext.ps1` | завантаження вихідників розширення з git у дев-базу |
| `tools/build.ps1` | збірка `.cfe` розширень і `.epf` обробок у `build/` |
| `tools/tests/*.Tests.ps1` | Pester-тести чистих функцій |
| `tools/tests/fixtures/storage-report-sample.txt` | синтетичний MXL-звіт для тестів парсера |
| `tools/tests/Run-Tests.ps1` | єдина точка запуску всіх тестів |

Розділення проведено так, щоб усе, що звертається до платформи, лежало в `V8.psm1` і не заважало тестувати решту. `storage-sync.ps1` не містить власної логіки розбору — тільки послідовність кроків і перевірки безпеки.

---

## Task 1: Каркас інструментів і обгортка платформи

**Files:**
- Create: `tools/lib/V8.psm1`
- Create: `tools/tests/V8.Tests.ps1`
- Create: `tools/tests/Run-Tests.ps1`

**Interfaces:**
- Consumes: нічого
- Produces:
  - `Get-V8Path([string]$Version = '8.3.27.1644') -> [string]` — повний шлях до `1cv8.exe`, кидає виняток, якщо не знайдено
  - `ConvertTo-V8IbSwitch([string]$Connection) -> [string]` — `'File="C:\x";'` → `/F "C:\x"`; `'Srvr="A";Ref="B";'` → `/S "A\B"`
  - `Invoke-V8Designer([string]$IbSwitch, [string[]]$Arguments, [string]$User, [string]$Password, [string]$V8Path) -> [pscustomobject]@{ ExitCode = [int]; Output = [string] }`
  - `New-V8FileInfobase([string]$Path, [string]$V8Path) -> [string]` — створює порожню файлову ІБ, повертає її шлях

- [ ] **Step 1: Встановити Pester 6**

```powershell
Install-Module Pester -MinimumVersion 5.0 -Scope CurrentUser -Force -SkipPublisherCheck
Get-Module -ListAvailable Pester | Select-Object Name, Version
```

Очікується рядок з версією 6.x. Модуль ставиться в профіль користувача; система не змінюється.

- [ ] **Step 2: Написати падаючий тест на `ConvertTo-V8IbSwitch`**

Створити `tools/tests/V8.Tests.ps1`:

```powershell
BeforeAll {
    Import-Module "$PSScriptRoot/../lib/V8.psm1" -Force
}

Describe 'ConvertTo-V8IbSwitch' {
    It 'перетворює файловий рядок підключення на /F' {
        ConvertTo-V8IbSwitch -Connection 'File="C:\bases\demo";' |
            Should -Be '/F "C:\bases\demo"'
    }

    It 'перетворює серверний рядок підключення на /S' {
        ConvertTo-V8IbSwitch -Connection 'Srvr="SRV01";Ref="DEMO_BASE";' |
            Should -Be '/S "SRV01\DEMO_BASE"'
    }

    It 'не залежить від регістру ключів і зайвих пробілів' {
        ConvertTo-V8IbSwitch -Connection '  srvr = "SRV01" ; ref = "DEMO_BASE" ; ' |
            Should -Be '/S "SRV01\DEMO_BASE"'
    }

    It 'приймає голий шлях як файлову базу' {
        ConvertTo-V8IbSwitch -Connection 'C:\bases\demo' |
            Should -Be '/F "C:\bases\demo"'
    }

    It 'кидає виняток на порожньому значенні' {
        { ConvertTo-V8IbSwitch -Connection '' } | Should -Throw
    }
}
```

- [ ] **Step 3: Написати `Run-Tests.ps1` і переконатись, що тест падає**

Створити `tools/tests/Run-Tests.ps1`:

```powershell
#Requires -Version 7
Import-Module Pester -MinimumVersion 5.0
$config = New-PesterConfiguration
$config.Run.Path = $PSScriptRoot
$config.Output.Verbosity = 'Detailed'
$config.Run.Exit = $true
Invoke-Pester -Configuration $config
```

Run: `pwsh -NoProfile -File tools/tests/Run-Tests.ps1`
Expected: FAIL — `Import-Module` не знаходить `V8.psm1`.

- [ ] **Step 4: Реалізувати `V8.psm1`**

Створити `tools/lib/V8.psm1`:

```powershell
#Requires -Version 7
Set-StrictMode -Version Latest

function Get-V8Path {
    [CmdletBinding()]
    param([string]$Version = '8.3.27.1644')

    $candidate = "C:\Program Files\1cv8\$Version\bin\1cv8.exe"
    if (Test-Path -LiteralPath $candidate) { return $candidate }

    $root = 'C:\Program Files\1cv8'
    if (Test-Path -LiteralPath $root) {
        $found = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like '8.3.27.*' } |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName 'bin\1cv8.exe' } |
            Where-Object { Test-Path -LiteralPath $_ } |
            Select-Object -First 1
        if ($found) { return $found }
    }

    throw "Платформу 1С гілки 8.3.27.x не знайдено. Очікувався $candidate"
}

function ConvertTo-V8IbSwitch {
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Connection)

    if ([string]::IsNullOrWhiteSpace($Connection)) {
        throw 'Рядок підключення до інформаційної бази порожній'
    }

    $value = $Connection.Trim()

    if ($value -match '(?i)\bsrvr\s*=\s*"([^"]+)"') {
        $server = $Matches[1]
        if ($value -match '(?i)\bref\s*=\s*"([^"]+)"') {
            return '/S "{0}\{1}"' -f $server, $Matches[1]
        }
        throw "У серверному рядку підключення відсутній Ref: $Connection"
    }

    if ($value -match '(?i)\bfile\s*=\s*"([^"]+)"') {
        return '/F "{0}"' -f $Matches[1]
    }

    if ($value -notmatch '[=;"]') {
        return '/F "{0}"' -f $value
    }

    throw "Не вдалося розпізнати рядок підключення: $Connection"
}

function Invoke-V8Designer {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$IbSwitch,
        [Parameter(Mandatory)][string[]]$Arguments,
        [string]$User,
        [string]$Password,
        [string]$V8Path
    )

    if (-not $V8Path) { $V8Path = Get-V8Path }

    $log = [System.IO.Path]::Combine(
        [System.IO.Path]::GetTempPath(),
        "v8-$([guid]::NewGuid().ToString('N')).log")

    $parts = @('DESIGNER', $IbSwitch)
    if ($User)     { $parts += '/N "{0}"' -f $User }
    if ($Password) { $parts += '/P "{0}"' -f $Password }
    $parts += '/DisableStartupDialogs'
    $parts += $Arguments
    $parts += '/Out "{0}"' -f $log

    $argLine = $parts -join ' '
    Write-Verbose "1cv8 $argLine"

    $proc = Start-Process -FilePath $V8Path -ArgumentList $argLine `
        -Wait -NoNewWindow -PassThru

    $output = ''
    if (Test-Path -LiteralPath $log) {
        $raw = Get-Content -LiteralPath $log -Raw -Encoding UTF8
        if ($raw) { $output = $raw.Trim() }
        Remove-Item -LiteralPath $log -Force -ErrorAction SilentlyContinue
    }

    if ($output -match '(?i)лиценз|license|HASP') {
        throw "Платформа повідомила про проблему з ліцензією, робота зупинена:`n$output"
    }

    [pscustomobject]@{ ExitCode = $proc.ExitCode; Output = $output }
}

function New-V8FileInfobase {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [string]$V8Path
    )

    if (-not $V8Path) { $V8Path = Get-V8Path }

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path -Force | Out-Null

    $log = Join-Path $Path 'create.log'
    $argLine = 'CREATEINFOBASE File="{0}"; /DisableStartupDialogs /Out "{1}"' -f $Path, $log
    $proc = Start-Process -FilePath $V8Path -ArgumentList $argLine -Wait -NoNewWindow -PassThru

    if ($proc.ExitCode -ne 0) {
        $msg = if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Raw -Encoding UTF8 } else { '' }
        throw "Не вдалося створити файлову ІБ у $Path : $msg"
    }

    Remove-Item -LiteralPath $log -Force -ErrorAction SilentlyContinue
    $Path
}

Export-ModuleMember -Function Get-V8Path, ConvertTo-V8IbSwitch, Invoke-V8Designer, New-V8FileInfobase
```

- [ ] **Step 5: Прогнати тести**

Run: `pwsh -NoProfile -File tools/tests/Run-Tests.ps1`
Expected: PASS, 5 тестів.

- [ ] **Step 6: Перевірити `Get-V8Path` на цій машині**

Run: `pwsh -NoProfile -Command "Import-Module ./tools/lib/V8.psm1; Get-V8Path"`
Expected: `C:\Program Files\1cv8\8.3.27.1644\bin\1cv8.exe`

- [ ] **Step 7: Коміт**

```bash
git add tools/lib/V8.psm1 tools/tests/V8.Tests.ps1 tools/tests/Run-Tests.ps1
git commit -m "Обгортка платформи 1С і каркас тестів"
```

---

## Task 2: Парсер MXL-звіту сховища

Звіт `/ConfigurationRepositoryReport` — це табличний документ у текстовому представленні: бінарна сигнатура `MOXCEL`, далі BOM і рядки виду `{"#","значення"}`. Значення йдуть парами «мітка → величина»: `Версия:`, `Пользователь:`, `Дата создания:`, `Время создания:`, `Версия конфигурации:`, `Комментарий:`. Коментар буває багаторядковим, лапки всередині подвоєні.

**Files:**
- Create: `tools/lib/StorageReport.psm1`
- Create: `tools/tests/StorageReport.Tests.ps1`
- Create: `tools/tests/fixtures/storage-report-sample.txt`

**Interfaces:**
- Consumes: `Invoke-V8Designer`, `ConvertTo-V8IbSwitch` з `V8.psm1`
- Produces:
  - `ConvertFrom-MxlText([string]$Path) -> [string[]]` — рядки тексту звіту без бінарного заголовка
  - `Get-MxlStringCells([string[]]$Lines) -> [string[]]` — значення текстових комірок, багаторядкові склеєні, подвоєні лапки розгорнуті
  - `Read-StorageReport([string]$Path) -> [pscustomobject[]]` з полями `Version` (int), `User`, `Date`, `Time`, `ConfigVersion`, `Comment`, `Timestamp` ([datetime])
  - `Get-StorageVersions([string]$IbSwitch, [string]$StoragePath, [string]$ExtensionName, [string]$StorageUser, [string]$WorkDir) -> [pscustomobject[]]` — будує звіт платформою й одразу його розбирає

- [ ] **Step 1: Створити фікстуру**

Створити `tools/tests/fixtures/storage-report-sample.txt` — синтетичний звіт із двома версіями: одна з багаторядковим коментарем, друга з подвоєними лапками. Дані вигадані навмисно, щоб тест не залежав від вмісту реальних сховищ.

```
{8,1,12,
{16,2,
{1,1,
{"#","Версия:"}
},0},1,
{16,5,
{1,1,
{"#","7"}
},0},5,0,2,0,
{16,2,
{1,1,
{"#","Пользователь:"}
},0},1,
{16,3,
{1,1,
{"#","Тестовий Автор"}
},0},6,0,2,0,
{16,2,
{1,1,
{"#","Дата создания:"}
},0},1,
{16,3,
{1,1,
{"#","16.03.2024"}
},0},7,0,2,0,
{16,2,
{1,1,
{"#","Время создания:"}
},0},1,
{16,3,
{1,1,
{"#","15:52:43"}
},0},8,0,2,0,
{16,2,
{1,1,
{"#","Версия конфигурации:"}
},0},1,
{16,3,
{1,1,
{"#","2.0.1.1"}
},0},9,0,2,0,
{16,6,
{1,1,
{"#","Комментарий:"}
},0},1,
{16,7,
{1,1,
{"#","Перший рядок

Третій рядок"}
},0},10,0,2,0,
{16,2,
{1,1,
{"#","Версия:"}
},0},1,
{16,5,
{1,1,
{"#","9"}
},0},5,0,2,0,
{16,2,
{1,1,
{"#","Пользователь:"}
},0},1,
{16,3,
{1,1,
{"#","Інший Автор"}
},0},6,0,2,0,
{16,2,
{1,1,
{"#","Дата создания:"}
},0},1,
{16,3,
{1,1,
{"#","02.04.2024"}
},0},7,0,2,0,
{16,2,
{1,1,
{"#","Время создания:"}
},0},1,
{16,3,
{1,1,
{"#","20:02:38"}
},0},8,0,2,0,
{16,2,
{1,1,
{"#","Версия конфигурации:"}
},0},1,
{16,3,
{1,1,
{"#","2.0.1.2"}
},0},9,0,2,0,
{16,6,
{1,1,
{"#","Комментарий:"}
},0},1,
{16,7,
{1,1,
{"#","Правка ""лапок"" усередині"}
},0},10,0,2,0,
```

Файл зберегти у UTF-8 **з BOM** — саме так його віддає платформа:

```powershell
$content = Get-Content -LiteralPath tools/tests/fixtures/storage-report-sample.txt -Raw
[System.IO.File]::WriteAllText(
    (Resolve-Path tools/tests/fixtures/storage-report-sample.txt),
    $content,
    (New-Object System.Text.UTF8Encoding($true)))
```

- [ ] **Step 2: Написати падаючі тести**

Створити `tools/tests/StorageReport.Tests.ps1`:

```powershell
BeforeAll {
    Import-Module "$PSScriptRoot/../lib/StorageReport.psm1" -Force
    $script:Fixture = Join-Path $PSScriptRoot 'fixtures/storage-report-sample.txt'
}

Describe 'Read-StorageReport' {
    BeforeAll { $script:Versions = Read-StorageReport -Path $script:Fixture }

    It 'знаходить обидві версії' {
        $script:Versions.Count | Should -Be 2
    }

    It 'читає номери версій як числа' {
        $script:Versions[0].Version | Should -Be 7
        $script:Versions[1].Version | Should -Be 9
        $script:Versions[0].Version | Should -BeOfType [int]
    }

    It 'читає автора, дату й версію конфігурації' {
        $script:Versions[0].User          | Should -Be 'Тестовий Автор'
        $script:Versions[0].Date          | Should -Be '16.03.2024'
        $script:Versions[0].Time          | Should -Be '15:52:43'
        $script:Versions[0].ConfigVersion | Should -Be '2.0.1.1'
    }

    It 'зберігає багаторядковий коментар цілим' {
        $script:Versions[0].Comment | Should -Be "Перший рядок`n`nТретій рядок"
    }

    It 'розгортає подвоєні лапки' {
        $script:Versions[1].Comment | Should -Be 'Правка "лапок" усередині'
    }

    It 'складає дату й час у Timestamp' {
        $script:Versions[0].Timestamp | Should -Be ([datetime]'2024-03-16T15:52:43')
    }

    It 'повертає версії за зростанням номера' {
        $script:Versions[0].Version | Should -BeLessThan $script:Versions[1].Version
    }
}

Describe 'ConvertFrom-MxlText' {
    It 'відкидає бінарний заголовок і повертає рядки' {
        $lines = ConvertFrom-MxlText -Path $script:Fixture
        $lines[0] | Should -Be '{8,1,12,'
    }
}
```

- [ ] **Step 3: Переконатись, що тести падають**

Run: `pwsh -NoProfile -File tools/tests/Run-Tests.ps1`
Expected: FAIL — модуль `StorageReport.psm1` не знайдено.

- [ ] **Step 4: Реалізувати `StorageReport.psm1`**

Створити `tools/lib/StorageReport.psm1`:

```powershell
#Requires -Version 7
Set-StrictMode -Version Latest

Import-Module "$PSScriptRoot/V8.psm1" -Force

$script:LabelMap = @{
    'Версия:'              = 'Version'
    'Пользователь:'        = 'User'
    'Дата создания:'       = 'Date'
    'Время создания:'      = 'Time'
    'Версия конфигурации:' = 'ConfigVersion'
    'Комментарий:'         = 'Comment'
}

function ConvertFrom-MxlText {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)

    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $start = 0
    $limit = [Math]::Min($bytes.Length - 2, 64)
    for ($i = 0; $i -lt $limit; $i++) {
        if ($bytes[$i] -eq 0xEF -and $bytes[$i + 1] -eq 0xBB -and $bytes[$i + 2] -eq 0xBF) {
            $start = $i + 3
            break
        }
    }
    [System.Text.Encoding]::UTF8.GetString($bytes, $start, $bytes.Length - $start) -split "`r?`n"
}

function Get-MxlStringCells {
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyCollection()][string[]]$Lines)

    $cells = [System.Collections.Generic.List[string]]::new()
    $buffer = $null

    foreach ($line in $Lines) {
        if ($null -ne $buffer) {
            $buffer += "`n" + $line
        }
        elseif ($line.StartsWith('{"#","')) {
            $buffer = $line.Substring(6)
        }
        else {
            continue
        }

        # Комірка закрита, коли рядок завершується лапкою й фігурною дужкою.
        if ($buffer -match '"\}[,\d]*$') {
            $value = $buffer -replace '\}[,\d]*$', ''
            $value = $value.TrimEnd()
            if ($value.EndsWith('"')) { $value = $value.Substring(0, $value.Length - 1) }
            $cells.Add($value.Replace('""', '"'))
            $buffer = $null
        }
    }

    , $cells.ToArray()
}

function Read-StorageReport {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)

    $cells = Get-MxlStringCells -Lines (ConvertFrom-MxlText -Path $Path)
    $result = [System.Collections.Generic.List[object]]::new()
    $current = $null
    $pending = $null

    foreach ($cell in $cells) {
        if ($script:LabelMap.ContainsKey($cell)) {
            if ($cell -eq 'Версия:') {
                if ($current) { $result.Add($current) }
                $current = [ordered]@{
                    Version = 0; User = ''; Date = ''; Time = ''
                    ConfigVersion = ''; Comment = ''
                }
            }
            $pending = $script:LabelMap[$cell]
            continue
        }

        if ($pending -and $current) {
            if ($pending -eq 'Version') {
                $current['Version'] = [int]$cell
            } else {
                $current[$pending] = $cell
            }
            $pending = $null
        }
    }
    if ($current) { $result.Add($current) }

    $result |
        ForEach-Object {
            $stamp = [datetime]::MinValue
            if ($_.Date -and $_.Time) {
                $stamp = [datetime]::ParseExact(
                    "$($_.Date) $($_.Time)", 'dd.MM.yyyy HH:mm:ss',
                    [cultureinfo]::InvariantCulture)
            }
            [pscustomobject]@{
                Version       = $_.Version
                User          = $_.User
                Date          = $_.Date
                Time          = $_.Time
                ConfigVersion = $_.ConfigVersion
                Comment       = $_.Comment
                Timestamp     = $stamp
            }
        } |
        Sort-Object Version
}

function Get-StorageVersions {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$IbSwitch,
        [Parameter(Mandatory)][string]$StoragePath,
        [Parameter(Mandatory)][string]$ExtensionName,
        [Parameter(Mandatory)][string]$StorageUser,
        [Parameter(Mandatory)][string]$WorkDir
    )

    New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null
    $reportPath = Join-Path $WorkDir 'storage-report.mxl'
    if (Test-Path -LiteralPath $reportPath) { Remove-Item -LiteralPath $reportPath -Force }

    $result = Invoke-V8Designer -IbSwitch $IbSwitch -Arguments @(
        '/ConfigurationRepositoryF "{0}"' -f $StoragePath
        '/ConfigurationRepositoryN "{0}"' -f $StorageUser
        '/ConfigurationRepositoryP ""'
        '/ConfigurationRepositoryReport "{0}" -NBegin 1 -Extension {1}' -f $reportPath, $ExtensionName
    )

    if ($result.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $reportPath)) {
        throw "Не вдалося побудувати звіт сховища $StoragePath : $($result.Output)"
    }

    Read-StorageReport -Path $reportPath
}

Export-ModuleMember -Function ConvertFrom-MxlText, Get-MxlStringCells, Read-StorageReport, Get-StorageVersions
```

- [ ] **Step 5: Прогнати тести**

Run: `pwsh -NoProfile -File tools/tests/Run-Tests.ps1`
Expected: PASS, 13 тестів (5 з Task 1 + 8 нових).

- [ ] **Step 6: Коміт**

```bash
git add tools/lib/StorageReport.psm1 tools/tests/StorageReport.Tests.ps1 tools/tests/fixtures/storage-report-sample.txt
git commit -m "Парсер звіту сховища конфігурацій"
```

---

## Task 3: Мапінг авторів і стан синхронізації

**Files:**
- Create: `tools/lib/Authors.psm1`
- Create: `tools/lib/SyncState.psm1`
- Create: `tools/tests/Authors.Tests.ps1`
- Create: `tools/tests/SyncState.Tests.ps1`

**Interfaces:**
- Consumes: `Read-StorageReport` (для типу об'єкта версії)
- Produces:
  - `Read-AuthorMap([string]$Path) -> [hashtable]` — ключ: ім'я у сховищі, значення: `[pscustomobject]@{ Name; Email }`
  - `Resolve-Author([hashtable]$Map, [string]$StorageUser) -> [pscustomobject]@{ Name; Email }` — кидає виняток, якщо автора немає в мапі
  - `Get-UnknownAuthors([hashtable]$Map, [string[]]$StorageUsers) -> [string[]]`
  - `Read-SyncState([string]$ProductPath) -> [pscustomobject]@{ StoragePath; ExtensionName; LastSyncedVersion; SourcePath }`
  - `Write-SyncState([string]$ProductPath, [int]$LastSyncedVersion) -> [void]`
  - `Get-PendingVersions([object[]]$AllVersions, [int]$LastSynced) -> [object[]]`

Автор, якого немає в `AUTHORS`, — це зупинка, а не припущення: мовчазна підстановка зіпсувала б авторство одразу в десятках комітів.

- [ ] **Step 1: Написати падаючі тести на `Authors.psm1`**

Створити `tools/tests/Authors.Tests.ps1`:

```powershell
BeforeAll {
    Import-Module "$PSScriptRoot/../lib/Authors.psm1" -Force
    $script:MapFile = Join-Path $TestDrive 'AUTHORS'
    @(
        "Володимир Сидоренко=Volodymyr Sydorenko <v.m.sydorenko@gmail.com>"
        "Олександр (alexsvlight)=alexsvlight <alexsv2012@gmail.com>"
        "# коментар, який треба пропустити"
        ""
    ) | Set-Content -LiteralPath $script:MapFile -Encoding UTF8
}

Describe 'Read-AuthorMap' {
    It 'читає записи у форматі Ім\u0027я=Name <email>' {
        $map = Read-AuthorMap -Path $script:MapFile
        $map['Володимир Сидоренко'].Name  | Should -Be 'Volodymyr Sydorenko'
        $map['Володимир Сидоренко'].Email | Should -Be 'v.m.sydorenko@gmail.com'
    }

    It 'витримує дужки в імені користувача сховища' {
        $map = Read-AuthorMap -Path $script:MapFile
        $map['Олександр (alexsvlight)'].Name | Should -Be 'alexsvlight'
    }

    It 'ігнорує коментарі й порожні рядки' {
        (Read-AuthorMap -Path $script:MapFile).Count | Should -Be 2
    }
}

Describe 'Resolve-Author' {
    It 'повертає git-автора для відомого користувача' {
        $map = Read-AuthorMap -Path $script:MapFile
        (Resolve-Author -Map $map -StorageUser 'Володимир Сидоренко').Email |
            Should -Be 'v.m.sydorenko@gmail.com'
    }

    It 'кидає виняток на невідомому користувачі' {
        $map = Read-AuthorMap -Path $script:MapFile
        { Resolve-Author -Map $map -StorageUser 'Хтось Новий' } | Should -Throw '*AUTHORS*'
    }
}

Describe 'Get-UnknownAuthors' {
    It 'повертає лише тих, кого немає в мапі, без повторів' {
        $map = Read-AuthorMap -Path $script:MapFile
        Get-UnknownAuthors -Map $map -StorageUsers @(
            'Володимир Сидоренко', 'Хтось Новий', 'Хтось Новий') |
            Should -Be @('Хтось Новий')
    }
}
```

- [ ] **Step 2: Написати падаючі тести на `SyncState.psm1`**

Створити `tools/tests/SyncState.Tests.ps1`:

```powershell
BeforeAll {
    Import-Module "$PSScriptRoot/../lib/SyncState.psm1" -Force
}

Describe 'Read-SyncState / Write-SyncState' {
    BeforeEach {
        $script:Product = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $script:Product -Force | Out-Null
        @{
            storagePath       = 'R:\Сховища\Тест'
            extensionName     = 'Test_Extension'
            lastSyncedVersion = 23
            sourcePath        = 'cfe/src'
        } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $script:Product 'storage.json') -Encoding UTF8
    }

    It 'читає storage.json' {
        $state = Read-SyncState -ProductPath $script:Product
        $state.ExtensionName     | Should -Be 'Test_Extension'
        $state.LastSyncedVersion | Should -Be 23
        $state.SourcePath        | Should -Be 'cfe/src'
    }

    It 'оновлює тільки номер версії, решту лишає незмінною' {
        Write-SyncState -ProductPath $script:Product -LastSyncedVersion 47
        $state = Read-SyncState -ProductPath $script:Product
        $state.LastSyncedVersion | Should -Be 47
        $state.StoragePath       | Should -Be 'R:\Сховища\Тест'
    }

    It 'кидає виняток, якщо storage.json відсутній' {
        $empty = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $empty -Force | Out-Null
        { Read-SyncState -ProductPath $empty } | Should -Throw '*storage.json*'
    }
}

Describe 'Get-PendingVersions' {
    BeforeAll {
        $script:All = @(
            [pscustomobject]@{ Version = 2 }
            [pscustomobject]@{ Version = 23 }
            [pscustomobject]@{ Version = 24 }
            [pscustomobject]@{ Version = 47 }
        )
    }

    It 'повертає версії, більші за залиту, за зростанням' {
        (Get-PendingVersions -AllVersions $script:All -LastSynced 23).Version |
            Should -Be @(24, 47)
    }

    It 'повертає порожній набір, коли все залито' {
        Get-PendingVersions -AllVersions $script:All -LastSynced 47 |
            Should -BeNullOrEmpty
    }

    It 'кидає виняток, коли git попереду сховища' {
        { Get-PendingVersions -AllVersions $script:All -LastSynced 99 } |
            Should -Throw '*попереду*'
    }
}
```

- [ ] **Step 3: Переконатись, що тести падають**

Run: `pwsh -NoProfile -File tools/tests/Run-Tests.ps1`
Expected: FAIL — модулі `Authors.psm1` і `SyncState.psm1` не знайдено.

- [ ] **Step 4: Реалізувати `Authors.psm1`**

```powershell
#Requires -Version 7
Set-StrictMode -Version Latest

function Read-AuthorMap {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Файл мапінгу авторів не знайдено: $Path"
    }

    $map = @{}
    foreach ($line in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        if ($trimmed -match '^(?<key>.+?)=(?<name>.+?)\s*<(?<mail>[^>]+)>\s*$') {
            $map[$Matches['key'].Trim()] = [pscustomobject]@{
                Name  = $Matches['name'].Trim()
                Email = $Matches['mail'].Trim()
            }
        }
    }
    $map
}

function Resolve-Author {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][hashtable]$Map,
        [Parameter(Mandatory)][string]$StorageUser
    )

    if ($Map.ContainsKey($StorageUser)) { return $Map[$StorageUser] }

    throw "Користувача сховища '$StorageUser' немає у файлі AUTHORS. " +
          "Додайте рядок «$StorageUser=Ім'я <пошта>» і повторіть запуск."
}

function Get-UnknownAuthors {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][hashtable]$Map,
        [Parameter(Mandatory)][AllowEmptyCollection()][string[]]$StorageUsers
    )

    , @($StorageUsers | Sort-Object -Unique | Where-Object { -not $Map.ContainsKey($_) })
}

Export-ModuleMember -Function Read-AuthorMap, Resolve-Author, Get-UnknownAuthors
```

- [ ] **Step 5: Реалізувати `SyncState.psm1`**

```powershell
#Requires -Version 7
Set-StrictMode -Version Latest

function Read-SyncState {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$ProductPath)

    $file = Join-Path $ProductPath 'storage.json'
    if (-not (Test-Path -LiteralPath $file)) {
        throw "Файл storage.json не знайдено в $ProductPath"
    }

    $json = Get-Content -LiteralPath $file -Raw -Encoding UTF8 | ConvertFrom-Json
    [pscustomobject]@{
        StoragePath       = $json.storagePath
        ExtensionName     = $json.extensionName
        LastSyncedVersion = [int]$json.lastSyncedVersion
        SourcePath        = $json.sourcePath
        Path              = $file
    }
}

function Write-SyncState {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$ProductPath,
        [Parameter(Mandatory)][int]$LastSyncedVersion
    )

    $file = Join-Path $ProductPath 'storage.json'
    $json = Get-Content -LiteralPath $file -Raw -Encoding UTF8 | ConvertFrom-Json
    $json.lastSyncedVersion = $LastSyncedVersion
    ($json | ConvertTo-Json -Depth 5) + "`n" |
        Set-Content -LiteralPath $file -Encoding UTF8 -NoNewline
}

function Get-PendingVersions {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$AllVersions,
        [Parameter(Mandatory)][int]$LastSynced
    )

    $max = ($AllVersions | Measure-Object -Property Version -Maximum).Maximum
    if ($null -ne $max -and $LastSynced -gt $max) {
        throw "git попереду сховища: залито версію $LastSynced, а у сховищі максимум $max. " +
              "Синхронізацію зупинено, розберіться з розбіжністю вручну."
    }

    , @($AllVersions | Where-Object { $_.Version -gt $LastSynced } | Sort-Object Version)
}

Export-ModuleMember -Function Read-SyncState, Write-SyncState, Get-PendingVersions
```

- [ ] **Step 6: Прогнати тести**

Run: `pwsh -NoProfile -File tools/tests/Run-Tests.ps1`
Expected: PASS, 25 тестів (13 попередніх + 6 у `Authors` + 6 у `SyncState`).

- [ ] **Step 7: Коміт**

```bash
git add tools/lib/Authors.psm1 tools/lib/SyncState.psm1 tools/tests/Authors.Tests.ps1 tools/tests/SyncState.Tests.ps1
git commit -m "Мапінг авторів і стан синхронізації сховищ"
```

---

## Task 4: Стаб розширення й підготовка тимчасової ІБ

Порожня ІБ не приймає звернення до сховища розширень: платформа відповідає «расширение конфигурации с указанным именем не найдено». Тому в базу спершу вантажиться мінімальний scaffold, а ключ `-Extension` задає потрібне ім'я — внутрішнє ім'я в самому scaffold значення не має (перевірено: `UNICA_STUB` завантажився як `SMP_BankExchange_SMBru`).

**Files:**
- Create: `tools/assets/empty-extension/Configuration.xml`
- Create: `tools/assets/empty-extension/Languages/Русский.xml`
- Modify: `tools/lib/V8.psm1` (додати `New-ExtensionInfobase`)
- Modify: `tools/tests/V8.Tests.ps1` (додати інтеграційний тест)

**Interfaces:**
- Consumes: `New-V8FileInfobase`, `Invoke-V8Designer`
- Produces:
  - `New-ExtensionInfobase([string]$Path, [string]$ExtensionName, [string]$StubPath, [string]$V8Path) -> [string]` — створює файлову ІБ і вантажить у неї порожнє розширення з указаним іменем; повертає ключ `/F "<шлях>"`

- [ ] **Step 1: Покласти scaffold**

Створити `tools/assets/empty-extension/Configuration.xml` і `tools/assets/empty-extension/Languages/Русский.xml`. Згенерувати їх інструментом Unica, щоб не переписувати XML руками:

```
MCP unica.cfe.init
{
  "cwd": "<абсолютний шлях до tools/assets>",
  "Name": "UNICA_STUB",
  "OutputDir": "empty-extension",
  "NoRole": true,
  "dryRun": false
}
```

Інструмент попередить, що `ExtendedConfigurationObject` мови заповнений нулями — для стаба це нормально, він ніколи не потрапляє у вихідники продукту.

- [ ] **Step 2: Написати падаючий інтеграційний тест**

Додати в кінець `tools/tests/V8.Tests.ps1`:

```powershell
Describe 'New-ExtensionInfobase' -Tag 'Integration' {
    It 'створює базу з розширенням під заданим іменем' {
        $ib = Join-Path $TestDrive 'ext-ib'
        $stub = Join-Path $PSScriptRoot '../assets/empty-extension'

        $ibSwitch = New-ExtensionInfobase -Path $ib -ExtensionName 'PROBE_EXT' -StubPath $stub
        $ibSwitch | Should -Be ('/F "{0}"' -f $ib)

        $dump = Join-Path $TestDrive 'ext-dump'
        New-Item -ItemType Directory -Path $dump -Force | Out-Null
        $res = Invoke-V8Designer -IbSwitch $ibSwitch -Arguments @(
            '/DumpConfigToFiles "{0}" -Extension PROBE_EXT' -f $dump)
        $res.ExitCode | Should -Be 0

        (Get-Content (Join-Path $dump 'Configuration.xml') -Raw -Encoding UTF8) |
            Should -Match '<Name>PROBE_EXT</Name>'
    }
}
```

- [ ] **Step 3: Переконатись, що тест падає**

Run: `pwsh -NoProfile -File tools/tests/Run-Tests.ps1`
Expected: FAIL — `New-ExtensionInfobase` не визначено.

- [ ] **Step 4: Додати функцію в `V8.psm1`**

Вставити перед рядком `Export-ModuleMember`:

```powershell
function New-ExtensionInfobase {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$ExtensionName,
        [Parameter(Mandatory)][string]$StubPath,
        [string]$V8Path
    )

    if (-not $V8Path) { $V8Path = Get-V8Path }

    New-V8FileInfobase -Path $Path -V8Path $V8Path | Out-Null
    $ibSwitch = '/F "{0}"' -f $Path

    $result = Invoke-V8Designer -IbSwitch $ibSwitch -V8Path $V8Path -Arguments @(
        '/LoadConfigFromFiles "{0}" -Extension {1}' -f (Resolve-Path -LiteralPath $StubPath), $ExtensionName)

    if ($result.ExitCode -ne 0) {
        throw "Не вдалося створити розширення $ExtensionName у тимчасовій ІБ: $($result.Output)"
    }

    $ibSwitch
}
```

Замінити рядок експорту на:

```powershell
Export-ModuleMember -Function Get-V8Path, ConvertTo-V8IbSwitch, Invoke-V8Designer, New-V8FileInfobase, New-ExtensionInfobase
```

- [ ] **Step 5: Прогнати тести**

Run: `pwsh -NoProfile -File tools/tests/Run-Tests.ps1`
Expected: PASS, 26 тестів. Інтеграційний триває близько хвилини — це нормально.

- [ ] **Step 6: Коміт**

```bash
git add tools/assets/empty-extension tools/lib/V8.psm1 tools/tests/V8.Tests.ps1
git commit -m "Стаб розширення для тимчасової ІБ синхронізації"
```

---

## Task 5: Скрипт синхронізації `storage-sync.ps1`

**Files:**
- Create: `tools/storage-sync.ps1`

**Interfaces:**
- Consumes: усі чотири модулі з `tools/lib`
- Produces: CLI `pwsh tools/storage-sync.ps1 -Product <тека> [-Apply] [-MaxVersions <n>]`

За замовчуванням скрипт **нічого не змінює**: друкує перелік майбутніх комітів (версія, автор, дата, повідомлення) і перелік невідомих авторів. Це і є гейт перед реальним прогоном — заразом видно, які коментарі зі сховища стануть публічними повідомленнями комітів.

- [ ] **Step 1: Написати скрипт**

Створити `tools/storage-sync.ps1`:

```powershell
#Requires -Version 7
<#
.SYNOPSIS
    Переносить нові версії сховища конфігурацій 1С у git — по коміту на версію.
.EXAMPLE
    pwsh tools/storage-sync.ps1 -Product BankExchange_SMB
    pwsh tools/storage-sync.ps1 -Product BankExchange_SMB -Apply
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Product,
    [switch]$Apply,
    [int]$MaxVersions = 0,
    [string]$StorageUser = 'gitbot'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Import-Module (Join-Path $PSScriptRoot 'lib/V8.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'lib/StorageReport.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'lib/Authors.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'lib/SyncState.psm1') -Force

$productPath = Join-Path $repoRoot $Product
if (-not (Test-Path -LiteralPath $productPath)) {
    throw "Продукт '$Product' не знайдено в $repoRoot"
}

$state     = Read-SyncState -ProductPath $productPath
$authors   = Read-AuthorMap -Path (Join-Path $repoRoot 'AUTHORS')
$sourceDir = Join-Path $productPath $state.SourcePath
$workDir   = Join-Path $productPath 'build/sync'
$ibPath    = Join-Path $workDir 'ib'
$stubPath  = Join-Path $PSScriptRoot 'assets/empty-extension'

Write-Host "Продукт:    $Product"
Write-Host "Розширення: $($state.ExtensionName)"
Write-Host "Сховище:    $($state.StoragePath)"
Write-Host "Залито:     версія $($state.LastSyncedVersion)"

if (-not (Test-Path -LiteralPath $state.StoragePath)) {
    throw "Каталог сховища не знайдено: $($state.StoragePath)"
}

# Робоча тека створюється з нуля на кожен запуск — щоб не тягнути стан попереднього.
if (Test-Path -LiteralPath $workDir) { Remove-Item -LiteralPath $workDir -Recurse -Force }
New-Item -ItemType Directory -Path $workDir -Force | Out-Null

Write-Host 'Створюю тимчасову ІБ і читаю історію сховища...'
$ibSwitch = New-ExtensionInfobase -Path $ibPath -ExtensionName $state.ExtensionName -StubPath $stubPath
$all      = Get-StorageVersions -IbSwitch $ibSwitch -StoragePath $state.StoragePath `
                -ExtensionName $state.ExtensionName -StorageUser $StorageUser -WorkDir $workDir

Write-Host "У сховищі версій: $($all.Count), максимальна: $(($all | Select-Object -Last 1).Version)"

$pending = Get-PendingVersions -AllVersions $all -LastSynced $state.LastSyncedVersion
if ($MaxVersions -gt 0) { $pending = $pending | Select-Object -First $MaxVersions }

if (-not $pending) {
    Write-Host 'Нових версій немає — git синхронний зі сховищем.'
    return
}

$unknown = Get-UnknownAuthors -Map $authors -StorageUsers ($pending.User)
if ($unknown) {
    Write-Host ''
    Write-Host 'Невідомі автори — додайте їх у AUTHORS перед прогоном:' -ForegroundColor Yellow
    $unknown | ForEach-Object { Write-Host "  $_=Ім'я <пошта>" }
    throw 'Синхронізацію зупинено через невідомих авторів.'
}

Write-Host ''
Write-Host "До перенесення версій: $($pending.Count)"
foreach ($v in $pending) {
    $author = Resolve-Author -Map $authors -StorageUser $v.User
    $first  = ($v.Comment -split "`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
    if (-not $first) { $first = "Версія сховища $($v.Version)" }
    Write-Host ("  v{0,-4} {1:yyyy-MM-dd HH:mm}  {2,-22} {3}" -f `
        $v.Version, $v.Timestamp, $author.Name, $first)
}

if (-not $Apply) {
    Write-Host ''
    Write-Host 'Це попередній перегляд. Для виконання додайте -Apply.' -ForegroundColor Cyan
    return
}

foreach ($v in $pending) {
    $author = Resolve-Author -Map $authors -StorageUser $v.User
    Write-Host "→ версія $($v.Version) ($($author.Name), $($v.Date))"

    $upd = Invoke-V8Designer -IbSwitch $ibSwitch -Arguments @(
        '/ConfigurationRepositoryF "{0}"' -f $state.StoragePath
        '/ConfigurationRepositoryN "{0}"' -f $StorageUser
        '/ConfigurationRepositoryP ""'
        '/ConfigurationRepositoryUpdateCfg -v {0} -Extension {1} -force' -f $v.Version, $state.ExtensionName
    )
    if ($upd.ExitCode -ne 0) {
        throw "Оновлення до версії $($v.Version) не вдалося: $($upd.Output)"
    }

    # Вивантаження не видаляє зниклі об'єкти, тому тека очищається перед кожним прогоном.
    if (Test-Path -LiteralPath $sourceDir) { Remove-Item -LiteralPath $sourceDir -Recurse -Force }
    New-Item -ItemType Directory -Path $sourceDir -Force | Out-Null

    $dump = Invoke-V8Designer -IbSwitch $ibSwitch -Arguments @(
        '/DumpConfigToFiles "{0}" -Extension {1}' -f $sourceDir, $state.ExtensionName)
    if ($dump.ExitCode -ne 0) {
        throw "Вивантаження версії $($v.Version) не вдалося: $($dump.Output)"
    }

    Write-SyncState -ProductPath $productPath -LastSyncedVersion $v.Version

    $lines = @($v.Comment -split "`n" | ForEach-Object { $_.TrimEnd() })
    $subject = ($lines | Where-Object { $_.Trim() } | Select-Object -First 1)
    if (-not $subject) { $subject = "Версія сховища $($v.Version)" }
    $body = @($lines | Select-Object -Skip ([array]::IndexOf($lines, $subject) + 1))

    $message = [System.Collections.Generic.List[string]]::new()
    $message.Add($subject)
    if ($body -and ($body -join '').Trim()) {
        $message.Add('')
        $body | ForEach-Object { $message.Add($_) }
    }
    $message.Add('')
    $message.Add("Storage-Version: $($v.Version)")
    if ($v.ConfigVersion) { $message.Add("Extension-Version: $($v.ConfigVersion)") }

    $msgFile = Join-Path $workDir 'commit-message.txt'
    ($message -join "`n") | Set-Content -LiteralPath $msgFile -Encoding UTF8

    $stamp = $v.Timestamp.ToString('yyyy-MM-ddTHH:mm:ss')
    $env:GIT_AUTHOR_DATE    = $stamp
    $env:GIT_COMMITTER_DATE = $stamp
    try {
        git -C $repoRoot add -A -- $Product
        git -C $repoRoot commit --author="$($author.Name) <$($author.Email)>" -F $msgFile --quiet
        if ($LASTEXITCODE -ne 0) { throw "git commit завершився з кодом $LASTEXITCODE" }
    }
    finally {
        Remove-Item Env:GIT_AUTHOR_DATE, Env:GIT_COMMITTER_DATE -ErrorAction SilentlyContinue
    }
}

Write-Host ''
Write-Host "Готово. Перенесено версій: $($pending.Count)." -ForegroundColor Green
```

- [ ] **Step 2: Перевірити, що скрипт коректно падає без `storage.json`**

Run: `pwsh -NoProfile -File tools/storage-sync.ps1 -Product BankExchange_SMB`
Expected: помилка `Продукт 'BankExchange_SMB' не знайдено` — продукти з'являться в Task 6. Це підтверджує, що перевірки спрацьовують до звернення до платформи.

- [ ] **Step 3: Коміт**

```bash
git add tools/storage-sync.ps1
git commit -m "Скрипт синхронізації «сховище → git»"
```

---

## Task 6: Реструктуризація репозиторію

**Files:**
- Create: `.gitignore` (замінити наявний)
- Create: `BankExchange_SMB/cf/README.md`, `BankExchange_SMBru/cf/README.md`, `BankExchange_ACC/cf/README.md`
- Modify: `AUTHORS` (перенести в корінь, доповнити)
- Move: усі теки продуктів
- Delete: EDT-специфічні файли

**Interfaces:**
- Consumes: нічого
- Produces: структуру тек, на яку спирається Task 5 і далі

- [ ] **Step 1: Зафіксувати офлайн-бекап**

```bash
mkdir -p build
git bundle create build/pre-restructure-$(date +%Y%m%d).bundle --all
git bundle verify build/pre-restructure-$(date +%Y%m%d).bundle
```

Expected: `The bundle records a complete history` і перелік гілок.

- [ ] **Step 2: Записати поточні номери версій**

```bash
for f in "BAS for accounting" "BAS small business" "SMB"; do
  echo -n "$f: "; grep -o '[0-9]\+' "$f/VERSION" | head -1
done
```

Expected: `BAS for accounting: 35`, `BAS small business: 23`, `SMB: 15`. Ці числа підуть у `storage.json` у Task 8.

- [ ] **Step 3: Перенести розширення**

```bash
mkdir -p BankExchange_SMB/cfe BankExchange_SMBru/cfe BankExchange_ACC/cfe
git mv "BAS small business/src"  BankExchange_SMB/cfe/src
git mv "SMB/src"                 BankExchange_SMBru/cfe/src
git mv "BAS for accounting/src"  BankExchange_ACC/cfe/src
```

- [ ] **Step 4: Перенести обробки**

```bash
mkdir -p epf/src epf/dist
for d in ExtDataProcessors/*/; do
  git mv "${d}src/"* epf/src/
  find "$d" -maxdepth 1 -name '*.epf' -exec git mv {} epf/dist/ \;
done
git status --short | head -20
```

- [ ] **Step 5: Прибрати EDT-специфічні залишки й консолідувати AUTHORS**

```bash
git mv "BAS small business/AUTHORS" AUTHORS
git rm -r --quiet "BAS for accounting" "BAS small business" "SMB" ExtDataProcessors
git status --short | grep -c '^D' || true
```

`.project`, `.settings`, `DT-INF` і `VERSION` — артефакти EDT-контуру, якого більше не буде; їхні номери версій уже виписані на кроці 2.

- [ ] **Step 6: Доповнити AUTHORS**

У сховищах трапляються користувачі, яких у файлі немає, і один запис не збігається за іменем (`Василь` проти `Василь Прокоф'єв`). Привести файл до такого вигляду, замінивши плейсхолдери на реальні дані — імена клієнтських баз (`Clarity_UNF_work`, `Decoratorskyi_UNF_work`, `TakeHot_UNF_work`) з'явились як користувачі сховища, тож потребують рішення власника, на кого їх зіставити:

```
Володимир Сидоренко=Volodymyr Sydorenko <v.m.sydorenko@gmail.com>
Ярослав Головатий=Yaroslav Holovatyi <yaroslav.holovatiy@gmail.com>
Володимир Прудніков=PrudnikovV <Prudnikovv@ukr.net>
Василь Прокоф'єв=evil beaver <va.prokophev@gmail.com>
Олександр (alexsvlight)=alexsvlight <alexsv2012@gmail.com>
```

Три невідомі імена свідомо не додаються наосліп: `storage-sync.ps1` у режимі перегляду сам їх перелічить у Task 7, і власник вирішить, кого вписати.

- [ ] **Step 7: Написати `.gitignore`**

Замінити вміст `.gitignore` на:

```gitignore
# Вендорські конфігурації — не наш код, у публічний репозиторій не потрапляють.
# Ігнорується вміст теки, а не сама тека, інакше README.md неможливо було б закомітити.
**/cf/**
!**/cf/README.md

# Робочі каталоги
build/
.build/
.superpowers/

# Локальні перевизначення з підключеннями й логінами
v8project.local.yaml

# Побічні файли платформи
ConfigDumpInfo.xml
DumpFilesIndex.txt
```

Шаблони без провідного слеша — щоб діяли в усіх продуктах, а не лише в корені.

- [ ] **Step 8: Пояснити порожні теки `cf/`**

Створити `BankExchange_SMB/cf/README.md` (і копії з відповідними назвами в двох інших продуктах):

```markdown
# Базова конфігурація — локально, не в git

Тут має лежати вивантаження конфігурації **BAS small business (УНФ UA)** у форматі
Designer platform XML, у підкаталозі `src/`.

Вміст цієї теки навмисно виключено з git: це код вендора, а репозиторій публічний.

Вивантажити:

```powershell
pwsh tools/dump-config.ps1 -Product BankExchange_SMB
```

Конфігурація потрібна тільки для операцій Unica, яким треба знати склад
конфігурації-власника: `cfe.borrow`, `cfe.diff`, `cfe.validate`. Для правок коду
й форм уже запозичених об'єктів вона не обов'язкова.
```

- [ ] **Step 9: Перевірити, що структура зійшлася**

```bash
git status --short | grep -v '^R' | head
ls BankExchange_SMB BankExchange_SMBru BankExchange_ACC epf
mkdir -p BankExchange_SMB/cf/src && echo probe > BankExchange_SMB/cf/src/probe.xml
git check-ignore -q BankExchange_SMB/cf/src/probe.xml && echo "OK: вміст cf/ ігнорується" || echo "ПОМИЛКА: cf/ не ігнорується"
git check-ignore -q BankExchange_SMB/cf/README.md && echo "ПОМИЛКА: README.md теж ігнорується" || echo "OK: README.md комітабельний"
rm -f BankExchange_SMB/cf/src/probe.xml
```

Expected: три теки продуктів із `cfe/`, `cf/`; `epf/` зі `src/` і `dist/`; обидва рядки — `OK`.
Негативний шаблон обов'язково перевірити фактично: звичайне `cf/` зробило б `cf/README.md`
некомітабельним, бо git не заходить у виключену теку.

- [ ] **Step 10: Коміт**

```bash
git add -A
git commit -m "Реструктуризація: продукт у корені, cfe/cf усередині

Теки перейменовано за іменем розширення в 1С: SMB був російською УНФ,
а BAS small business — українською, що збивало з пантелику.

Шляхи одразу фінальні, щоб наступна зміна формату EDT → Designer XML
не розірвала git log --follow ще й переїздом."
```

- [ ] **Step 11: Перевірити, що історія пережила переїзд**

```bash
git log --follow --oneline -- BankExchange_SMB/cfe/src/Configuration.mdo | tail -3
```

Expected: коміти 2024 року — історія тягнеться крізь перейменування.

---

## Task 7: Догнати історію по найменшому продукту

Перший реальний прогін робиться на `BankExchange_SMBru`: там одна незалита версія, тож помилки виявляться дешево.

**Files:**
- Create: `BankExchange_SMBru/storage.json`
- Modify: `AUTHORS` (за результатом перегляду)
- Modify: `BankExchange_SMBru/cfe/src/**` (вивантаження платформою)

**Interfaces:**
- Consumes: `tools/storage-sync.ps1`
- Produces: підтверджений робочий конвеєр для Task 8

- [ ] **Step 1: Створити `storage.json`**

`BankExchange_SMBru/storage.json`:

```json
{
  "storagePath": "R:\\СховищаРозширень_1С\\СМП_BankExchange_SMBru",
  "extensionName": "SMP_BankExchange_SMBru",
  "lastSyncedVersion": 15,
  "sourcePath": "cfe/src"
}
```

- [ ] **Step 2: Прогнати попередній перегляд**

Run: `pwsh -NoProfile -File tools/storage-sync.ps1 -Product BankExchange_SMBru`
Expected: `У сховищі версій: 10, максимальна: 16`, `До перенесення версій: 1`, рядок з версією 16 і повідомленням коміту. Якщо виведено перелік невідомих авторів — додати їх у `AUTHORS` (узгодивши з власником) і повторити.

- [ ] **Step 3: Виконати**

Run: `pwsh -NoProfile -File tools/storage-sync.ps1 -Product BankExchange_SMBru -Apply`
Expected: `Перенесено версій: 1`.

- [ ] **Step 4: Перевірити результат**

```bash
git log -1 --format="%h %an <%ae> %ad%n%B" --date=iso -- BankExchange_SMBru
ls BankExchange_SMBru/cfe/src | head
find BankExchange_SMBru/cfe/src -name '*.mdo' | wc -l
find BankExchange_SMBru/cfe/src -name '*.xml' | wc -l
cat BankExchange_SMBru/storage.json
```

Expected: автор і дата з 06.12.2024; трейлер `Storage-Version: 16`; **0** файлів `.mdo` і десятки `.xml` — формат перемкнувся; `lastSyncedVersion` дорівнює 16.

- [ ] **Step 5: Перевірити ідемпотентність**

Run: `pwsh -NoProfile -File tools/storage-sync.ps1 -Product BankExchange_SMBru`
Expected: `Нових версій немає — git синхронний зі сховищем.` Нових комітів не з'явилось.

- [ ] **Step 6: Перевірити, що Unica читає результат**

```
MCP unica.project.map { "cwd": "<repo>/BankExchange_SMBru/cfe" }
```
Expected: `sourceFormat: platform_xml`.

---

## Task 8: Догнати історію по решті продуктів

**Files:**
- Create: `BankExchange_ACC/storage.json`, `BankExchange_SMB/storage.json`
- Modify: `BankExchange_ACC/cfe/src/**`, `BankExchange_SMB/cfe/src/**`

**Interfaces:**
- Consumes: `tools/storage-sync.ps1`, підтверджений у Task 7
- Produces: повну історію в git по всіх трьох розширеннях

- [ ] **Step 1: Створити `BankExchange_ACC/storage.json`**

```json
{
  "storagePath": "R:\\СховищаРозширень_1С\\СМП_BankExchange_BP",
  "extensionName": "SMP_BankExchange_ACC",
  "lastSyncedVersion": 35,
  "sourcePath": "cfe/src"
}
```

Каталог сховища досі зветься `..._BP`, а розширення вже перейменоване на `SMP_BankExchange_ACC` — розбіжність історична й навмисна.

- [ ] **Step 2: Перегляд і прогін ACC**

Run: `pwsh -NoProfile -File tools/storage-sync.ps1 -Product BankExchange_ACC`
Expected: `До перенесення версій: 7` (36, 37, 38, 39, 42, 43, 44).

Run: `pwsh -NoProfile -File tools/storage-sync.ps1 -Product BankExchange_ACC -Apply`
Expected: `Перенесено версій: 7`.

- [ ] **Step 3: Створити `BankExchange_SMB/storage.json`**

```json
{
  "storagePath": "R:\\СховищаРозширень_1С\\СМП_BankExchange_SMB",
  "extensionName": "SMP_BankExchange_SMB",
  "lastSyncedVersion": 23,
  "sourcePath": "cfe/src"
}
```

- [ ] **Step 4: Перегляд SMB**

Run: `pwsh -NoProfile -File tools/storage-sync.ps1 -Product BankExchange_SMB`
Expected: `До перенесення версій: 22` (24–31, 34–47).

Це найбільший обсяг і найдовший перелік коментарів — переглянути його разом із власником до `-Apply`, бо повідомлення стануть публічними.

- [ ] **Step 5: Прогін SMB частинами**

Спершу три версії, щоб переконатись у стабільності на довгій серії:

Run: `pwsh -NoProfile -File tools/storage-sync.ps1 -Product BankExchange_SMB -Apply -MaxVersions 3`
Expected: `Перенесено версій: 3`.

```bash
git log --oneline -3 -- BankExchange_SMB
```

Далі решта:

Run: `pwsh -NoProfile -File tools/storage-sync.ps1 -Product BankExchange_SMB -Apply`
Expected: `Перенесено версій: 19`.

- [ ] **Step 6: Приймальна перевірка по всіх трьох**

```bash
for p in BankExchange_SMB BankExchange_SMBru BankExchange_ACC; do
  echo "=== $p ==="
  cat $p/storage.json | grep lastSyncedVersion
  echo "  .mdo: $(find $p/cfe/src -name '*.mdo' | wc -l)  .xml: $(find $p/cfe/src -name '*.xml' | wc -l)"
  git log -1 --format="  останній: %h %an %ad" --date=short -- $p
  pwsh -NoProfile -File tools/storage-sync.ps1 -Product $p | tail -1
done
```

Expected: `lastSyncedVersion` = 47 / 16 / 44; нуль `.mdo` скрізь; кожен продукт повідомляє «Нових версій немає».

---

## Task 9: Контур Unica

**Files:**
- Create: `BankExchange_SMB/v8project.yaml`, `BankExchange_SMBru/v8project.yaml`, `BankExchange_ACC/v8project.yaml`, `epf/v8project.yaml`
- Create: `BankExchange_SMB/v8project.local.yaml` та аналоги (gitignored)
- Create: `BankExchange_SMB/README.md` та аналоги

**Interfaces:**
- Consumes: структуру з Task 6, вихідники з Task 8
- Produces: воркспейси, у яких працюють інструменти `unica.*`

- [ ] **Step 1: Створити `v8project.yaml` розширень**

`BankExchange_SMB/v8project.yaml`:

```yaml
format: DESIGNER
builder: DESIGNER
workPath: 'build'
execution_timeout: 600000
source-set:
  - name: base
    type: CONFIGURATION
    path: 'cf/src'
  - name: BankExchange_SMB
    type: EXTENSION
    path: 'cfe/src'
```

Аналогічно для `BankExchange_SMBru` (source-set `BankExchange_SMBru`) і `BankExchange_ACC` (source-set `BankExchange_ACC`).

- [ ] **Step 2: Створити `epf/v8project.yaml`**

```yaml
format: DESIGNER
builder: DESIGNER
workPath: 'build'
execution_timeout: 600000
source-set:
  - name: bank_formats
    type: EXTERNAL_DATA_PROCESSORS
    path: 'src'
```

Пишеться руками навмисно: `config-init` відмовляє, коли в дереві немає `CONFIGURATION`-набору.

- [ ] **Step 3: Створити локальні файли з підключеннями**

Конкретні рядки підключення й логіни **навмисно не наведені тут**: цей план закомічений у
публічний репозиторій. Візьми їх із пам'яті проєкту — файл
`bankexchange-infrastructure-map.md` містить таблицю «продукт → розширення → сховище → дев-база»
з рядком підключення та ім'ям користувача для кожного з трьох продуктів. Якщо пам'ять
недоступна — спитай користувача, не вгадуй.

Формат файла (по одному на продукт, усі три gitignored):

```yaml
infobase:
  connection: '<рядок підключення з пам'яті проєкту>'
  user: '<ім'я користувача бази з пам'яті проєкту>'
```

Паролів у всіх трьох немає — поле `password` не додавати взагалі.

Перевірити, що git їх не бачить:

```bash
git status --short | grep local.yaml && echo "ПОМИЛКА: локальні файли видимі" || echo "OK: ігноруються"
```

- [ ] **Step 4: Приймальна перевірка Unica**

Для кожного з чотирьох воркспейсів:

```
MCP unica.project.map    { "cwd": "<repo>/BankExchange_SMB" }
MCP unica.project.status { "cwd": "<repo>/BankExchange_SMB" }
```

Expected: `sourceFormat: platform_xml`; для розширень — набір `kind: extension`; для `epf/` — `kind: external_processor`.

`cf/src` на цей момент **порожня**: базові конфігурації вивантажуються за потреби, скриптом із
Task 10. Якщо Unica відмовляється читати воркспейс через відсутній шлях `CONFIGURATION`-набору —
створи порожню теку `cf/src` локально (вона під `.gitignore`, у коміт не потрапить) і зазнач це
у звіті. Приймальний критерій — набір `EXTENSION` розпізнано правильно; стан `CONFIGURATION`-набору
на цьому етапі не блокує.

- [ ] **Step 5: Перевірити діагностику BSL**

```
MCP unica.code.diagnostics { "cwd": "<repo>/BankExchange_SMB", "mode": "analyze", "sourceDir": "<repo>/BankExchange_SMB/cfe/src" }
```

Expected: звіт побудовано без падіння. Знайдені зауваження на цьому етапі не виправляються — це базовий зріз.

- [ ] **Step 6: Написати README продуктів**

`BankExchange_SMB/README.md`:

```markdown
# BankExchange_SMB

Розширення підсистеми обміну з клієнт-банком для **BAS small business (УНФ, українська версія)**.

| | |
|---|---|
| Ім'я розширення в 1С | `SMP_BankExchange_SMB` |
| Вихідники | `cfe/src` — Designer platform XML |
| Базова конфігурація | `cf/src` — локально, не в git (див. `cf/README.md`) |
| Історія | синхронізується зі сховища через `tools/storage-sync.ps1` |

Обробки читання форматів виписок живуть окремо — у теці `epf/` в корені репозиторію.
```

Аналогічні файли для `BankExchange_SMBru` (УНФ, російська версія) і `BankExchange_ACC`
(BAS for accounting, українська бухгалтерія).

- [ ] **Step 7: Коміт**

```bash
git add BankExchange_SMB/v8project.yaml BankExchange_SMBru/v8project.yaml BankExchange_ACC/v8project.yaml epf/v8project.yaml
git add BankExchange_SMB/README.md BankExchange_SMBru/README.md BankExchange_ACC/README.md
git commit -m "Воркспейси Unica для трьох розширень і обробок"
```

---

## Task 10: Скрипти вивантаження й завантаження конфігурації

**Files:**
- Create: `tools/dump-config.ps1`
- Create: `tools/load-ext.ps1`

**Interfaces:**
- Consumes: `V8.psm1`
- Produces: CLI `pwsh tools/dump-config.ps1 -Product <тека> [-Apply]`, `pwsh tools/load-ext.ps1 -Product <тека> [-Apply]`

- [ ] **Step 1: Написати `dump-config.ps1`**

```powershell
#Requires -Version 7
<#
.SYNOPSIS
    Вивантажує базову конфігурацію з дев-бази продукту в <продукт>/cf/src.
.DESCRIPTION
    Потрібно для операцій Unica, яким треба знати склад конфігурації-власника:
    cfe.borrow, cfe.diff, cfe.validate. Займає 20-40 хвилин і 1-2 ГБ на диску.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Product,
    [switch]$Apply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Import-Module (Join-Path $PSScriptRoot 'lib/V8.psm1') -Force

$productPath = Join-Path $repoRoot $Product
$localFile   = Join-Path $productPath 'v8project.local.yaml'
if (-not (Test-Path -LiteralPath $localFile)) {
    throw "Не знайдено $localFile — у ньому має бути підключення до дев-бази."
}

$local = Get-Content -LiteralPath $localFile -Raw -Encoding UTF8
if ($local -notmatch "(?m)^\s*connection:\s*'(?<c>.+?)'\s*$") {
    throw "У $localFile немає рядка connection: '...'"
}
$connection = $Matches['c']
$user = ''
if ($local -match "(?m)^\s*user:\s*'(?<u>.+?)'\s*$") { $user = $Matches['u'] }

$ibSwitch = ConvertTo-V8IbSwitch -Connection $connection
$target   = Join-Path $productPath 'cf/src'

Write-Host "Продукт: $Product"
Write-Host "База:    $ibSwitch"
Write-Host "Куди:    $target"

if (-not $Apply) {
    Write-Host 'Це попередній перегляд. Для виконання додайте -Apply.' -ForegroundColor Cyan
    Write-Host 'Вивантаження триває 20-40 хвилин і займає 1-2 ГБ.' -ForegroundColor Cyan
    return
}

if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
New-Item -ItemType Directory -Path $target -Force | Out-Null

$result = Invoke-V8Designer -IbSwitch $ibSwitch -User $user -Arguments @(
    '/DumpConfigToFiles "{0}"' -f $target)

if ($result.ExitCode -ne 0) {
    throw "Вивантаження конфігурації не вдалося: $($result.Output)"
}

$count = (Get-ChildItem -LiteralPath $target -Recurse -File).Count
Write-Host "Готово. Файлів: $count" -ForegroundColor Green
```

- [ ] **Step 2: Написати `load-ext.ps1`**

```powershell
#Requires -Version 7
<#
.SYNOPSIS
    Завантажує вихідники розширення з git у дев-базу продукту.
.DESCRIPTION
    Зворотний напрямок контуру: git -> база. Крок «база -> сховище» виконує
    людина в Конфігураторі; цей скрипт сховища не торкається.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Product,
    [switch]$Apply,
    [switch]$UpdateDbCfg
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Import-Module (Join-Path $PSScriptRoot 'lib/V8.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'lib/SyncState.psm1') -Force

$productPath = Join-Path $repoRoot $Product
$state       = Read-SyncState -ProductPath $productPath
$sourceDir   = Join-Path $productPath $state.SourcePath
$localFile   = Join-Path $productPath 'v8project.local.yaml'

if (-not (Test-Path -LiteralPath $localFile)) {
    throw "Не знайдено $localFile — у ньому має бути підключення до дев-бази."
}
$local = Get-Content -LiteralPath $localFile -Raw -Encoding UTF8
if ($local -notmatch "(?m)^\s*connection:\s*'(?<c>.+?)'\s*$") {
    throw "У $localFile немає рядка connection: '...'"
}
$connection = $Matches['c']
$user = ''
if ($local -match "(?m)^\s*user:\s*'(?<u>.+?)'\s*$") { $user = $Matches['u'] }

$ibSwitch = ConvertTo-V8IbSwitch -Connection $connection

Write-Host "Продукт:    $Product"
Write-Host "Розширення: $($state.ExtensionName)"
Write-Host "Вихідники:  $sourceDir"
Write-Host "База:       $ibSwitch"

if (-not $Apply) {
    Write-Host 'Це попередній перегляд. Для виконання додайте -Apply.' -ForegroundColor Cyan
    return
}

# Не називати змінну $args — це автоматична змінна PowerShell.
$designerArgs = @('/LoadConfigFromFiles "{0}" -Extension {1}' -f $sourceDir, $state.ExtensionName)
if ($UpdateDbCfg) { $designerArgs += '/UpdateDBCfg -Extension {0}' -f $state.ExtensionName }

$result = Invoke-V8Designer -IbSwitch $ibSwitch -User $user -Arguments $designerArgs
if ($result.ExitCode -ne 0) {
    throw "Завантаження розширення не вдалося: $($result.Output)"
}

Write-Host 'Готово. Зміни у сховище заносить людина в Конфігураторі.' -ForegroundColor Green
```

- [ ] **Step 3: Перевірити попередній перегляд обох**

Run: `pwsh -NoProfile -File tools/dump-config.ps1 -Product BankExchange_SMB`
Expected: виводить базу, шлях і попередження про 20-40 хвилин; нічого не змінює.

Run: `pwsh -NoProfile -File tools/load-ext.ps1 -Product BankExchange_SMB`
Expected: виводить розширення, вихідники й базу; нічого не змінює.

- [ ] **Step 4: Коміт**

```bash
git add tools/dump-config.ps1 tools/load-ext.ps1
git commit -m "Скрипти вивантаження конфігурації та завантаження розширення"
```

---

## Task 11: Скрипт збірки

Збірка робиться платформою напряму: операція `make` в Unica на Windows падає на публікації артефакту (`Отказано в доступе, os error 5`), лишаючи файл у стейджі.

**Files:**
- Create: `tools/build.ps1`

**Interfaces:**
- Consumes: `V8.psm1`, `SyncState.psm1`
- Produces: CLI `pwsh tools/build.ps1 [-Product <тека>] [-Apply]`; артефакти в `build/artifacts/`

- [ ] **Step 1: Написати `build.ps1`**

```powershell
#Requires -Version 7
<#
.SYNOPSIS
    Збирає .cfe розширень і .epf обробок у build/artifacts.
#>
[CmdletBinding()]
param(
    [string]$Product,
    [switch]$Apply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Import-Module (Join-Path $PSScriptRoot 'lib/V8.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'lib/SyncState.psm1') -Force

$stubPath  = Join-Path $PSScriptRoot 'assets/empty-extension'
$outDir    = Join-Path $repoRoot 'build/artifacts'
$buildIb   = Join-Path $repoRoot 'build/build-ib'

$products = if ($Product) { @($Product) } else {
    @('BankExchange_SMB', 'BankExchange_SMBru', 'BankExchange_ACC', 'epf')
}

Write-Host "Збирати: $($products -join ', ')"
Write-Host "Куди:    $outDir"

if (-not $Apply) {
    Write-Host 'Це попередній перегляд. Для виконання додайте -Apply.' -ForegroundColor Cyan
    return
}

New-Item -ItemType Directory -Path $outDir -Force | Out-Null

foreach ($p in $products) {
    $productPath = Join-Path $repoRoot $p

    if ($p -eq 'epf') {
        # Кожна обробка — окремий корінь: <Name>.xml поруч із текою <Name>.
        $ibSwitch = '/F "{0}"' -f (New-V8FileInfobase -Path $buildIb)
        foreach ($desc in Get-ChildItem -LiteralPath (Join-Path $productPath 'src') -Filter '*.xml' -File) {
            $name = [System.IO.Path]::GetFileNameWithoutExtension($desc.Name)
            $target = Join-Path $outDir "$name.epf"
            Write-Host "→ $name.epf"
            $r = Invoke-V8Designer -IbSwitch $ibSwitch -Arguments @(
                '/LoadExternalDataProcessorOrReportFromFiles "{0}" "{1}"' -f $desc.FullName, $target)
            if ($r.ExitCode -ne 0) { throw "Збірка $name не вдалася: $($r.Output)" }
        }
        continue
    }

    $state = Read-SyncState -ProductPath $productPath
    $src   = Join-Path $productPath $state.SourcePath
    $target = Join-Path $outDir "$($state.ExtensionName).cfe"
    Write-Host "→ $($state.ExtensionName).cfe"

    $ibSwitch = New-ExtensionInfobase -Path $buildIb -ExtensionName $state.ExtensionName -StubPath $stubPath
    $load = Invoke-V8Designer -IbSwitch $ibSwitch -Arguments @(
        '/LoadConfigFromFiles "{0}" -Extension {1}' -f $src, $state.ExtensionName)
    if ($load.ExitCode -ne 0) { throw "Завантаження $($state.ExtensionName) не вдалося: $($load.Output)" }

    $dump = Invoke-V8Designer -IbSwitch $ibSwitch -Arguments @(
        '/DumpCfg "{0}" -Extension {1}' -f $target, $state.ExtensionName)
    if ($dump.ExitCode -ne 0) { throw "Збірка $($state.ExtensionName) не вдалася: $($dump.Output)" }
}

Get-ChildItem -LiteralPath $outDir | Select-Object Name, Length | Format-Table
Write-Host 'Готово.' -ForegroundColor Green
```

- [ ] **Step 2: Зібрати найменше розширення**

Run: `pwsh -NoProfile -File tools/build.ps1 -Product BankExchange_SMBru -Apply`
Expected: `build/artifacts/SMP_BankExchange_SMBru.cfe` ненульового розміру.

- [ ] **Step 3: Зібрати обробки**

Run: `pwsh -NoProfile -File tools/build.ps1 -Product epf -Apply`
Expected: 12 файлів `.epf` у `build/artifacts`.

Порівняти з тим, що лежить у git:

```bash
ls build/artifacts/*.epf | wc -l
ls epf/dist/*.epf | wc -l
```

Expected: обидва числа — 12. Розбіжність у розмірах допустима (платформа перезбирає), розбіжність у складі — ні.

- [ ] **Step 4: Коміт**

```bash
git add tools/build.ps1
git commit -m "Скрипт збірки .cfe та .epf"
```

---

## Task 12: Документація

`CLAUDE.md` і `.claude/settings.json` уже написані під час проєктування — у цій задачі
`CLAUDE.md` лише оновлюється, а решта документів пишеться з нуля за фактичним кодом.

**Files:**
- Create: `docs/architecture/storage-and-git.md`
- Create: `docs/architecture/overview.md`
- Create: `docs/architecture/data-processor-contract.md`
- Create: `docs/banks/README.md`
- Modify: `CLAUDE.md` (розділ «Статус»)
- Modify: `README.md`

**Interfaces:**
- Consumes: усе попереднє
- Produces: контекст, за яким нова сесія агента виходить на робочу операцію без розвідки

- [ ] **Step 1: Прибрати з `CLAUDE.md` розділ «Статус»**

Міграцію завершено, тому абзац про старі EDT-теки в корені більше не відповідає дійсності.
Видалити розділ `## Статус` цілком і замість нього лишити два рядки посилань одразу після
вступного абзацу:

```markdown
Дизайн і план перезапуску — `docs/superpowers/specs/2026-08-28-bankexchange-restart-design.md`
та `docs/superpowers/plans/2026-08-28-bankexchange-restart.md`.
```

- [ ] **Step 2: Написати `docs/architecture/storage-and-git.md`**

Каркас документа; кожен заголовок має отримати відповідь, а не залишитись порожнім:

```markdown
# Контур «сховище ↔ git»

## Три напрямки і чому вони асиметричні
<таблиця сховище→git / git→база / база→сховище; чому останній ручний>

## storage.json
<поля, хто їх читає, чому пароля немає>

## AUTHORS
<формат рядка, що робиться з невідомим автором, чому зупинка а не підстановка>

## Захист від розбіжності
<порівняння lastSyncedVersion з максимумом сховища, коли синхронізація зупиняється>

## Особливості платформи
<місце -Extension; потреба в стабі; /F замість /IBConnectionString; кирилиця в .cmd;
формат MXL-звіту; DumpConfigToFiles не видаляє зниклі об'єкти>
```

Джерело для останнього розділу — розділ «Особливості платформи» у `CLAUDE.md` і
`tools/lib/StorageReport.psm1`.

- [ ] **Step 3: Написати `docs/architecture/overview.md`**

Каркас:

```markdown
# Підсистема BankExchange

## Що робить
<завантаження виписок за період, налаштування в розрізі банківського рахунку>

## Три розширення і чим відрізняються
<таблиця: продукт, конфігурація, префікс об'єктів, що є унікального>

## Склад розширення
<CommonModules і за що кожен відповідає; заміщені документи й довідники;
точка входу — обробка СМП_КлиентБанк>

## Як підключаються обробки читання форматів
<довідник додаткових обробок БСП, налаштування на банківському рахунку>
```

Джерело — `BankExchange_SMB/cfe/src`: перелік `CommonModules`, `DataProcessors`,
`Catalogs`, `InformationRegisters` і код модуля `СМП_КлиентБанк`.

- [ ] **Step 4: Написати `docs/architecture/data-processor-contract.md`**

Каркас:

```markdown
# Контракт обробки читання формату

## Що викликає розширення
<експортні методи модуля об'єкта обробки, їхні параметри>

## Що обробка повертає
<структура або таблиця значень: колонки, типи, обов'язковість>

## Як додати новий банк
<кроки: скопіювати найближчу обробку, перейменувати, реалізувати розбір,
зібрати build.ps1, зареєструвати в довіднику>
```

Джерело — `epf/src/СМП_ОбработкаВыпискиБанка_*/Ext/ObjectModule.bsl` (взяти дві-три
обробки й вивести спільний контракт) і місце виклику в коді розширення.

- [ ] **Step 5: Написати `docs/banks/README.md`**

Таблиця по 12 банках. Колонки: банк, ім'я обробки, джерело даних (файл виписки чи API),
формат файла, статус. Джерело — імена в `epf/src` і код кожної обробки.

- [ ] **Step 6: Оновити `README.md`**

У розділі «Розробка» замінити застаріле («вивантаження проводилось на платформі 8.3.22.1923 та
EDT версії 8.3.22») на поточний контур: Designer platform XML, платформа 8.3.27.x, синхронізація
зі сховищ через `tools/storage-sync.ps1`, обробки читання форматів у теці `epf/`.

- [ ] **Step 7: Коміт**

```bash
git add CLAUDE.md README.md docs/architecture docs/banks
git commit -m "Архітектурна документація"
```

---

## Task 13: Pull Request

**Files:** немає

- [ ] **Step 1: Фінальна перевірка**

```bash
pwsh -NoProfile -File tools/tests/Run-Tests.ps1
git status --short
git log --oneline main..HEAD | wc -l
```

Expected: усі тести проходять; робоче дерево чисте; близько 40 комітів.

- [ ] **Step 2: Перевірити, що чутливого не просочилось**

```bash
git log -p main..HEAD -- . ':(exclude)docs/superpowers/**' \
  | grep -nE 'Srvr="|VSDEV|VSDATA|_РобочіФайлиПрограмістів' | head
```

Expected: порожньо. Якщо щось знайдено — виправити до пушу, бо репозиторій публічний.

`docs/superpowers/` виключено навмисно: дизайн і план самі формулюють це правило й наводять
шаблони пошуку, тому без виключення перевірка ловила б власний текст і завжди «падала».
Це не лазівка — конкретні рядки підключення й логіни з цих документів прибрані, вони живуть
лише в `v8project.local.yaml` та в пам'яті проєкту.

- [ ] **Step 3: Запушити й створити PR**

```bash
git push -u origin restructure/2026-08
gh pr create --base main --head restructure/2026-08 \
  --title "Перезапуск проєкту: Designer XML, історія сховищ, контур Unica" \
  --body-file docs/superpowers/specs/2026-08-28-bankexchange-restart-design.md
```

- [ ] **Step 4: Передати власнику**

Повідомити номер PR і три речі для перегляду: перелік нових комітів з авторами й датами,
`.gitignore` разом із відсутністю `cf/` у диффі, і склад `epf/src` після сплощення.

---

## Що залишається поза цим планом

- **Видалення 12 дубльованих обробок з UA-розширення.** Спершу потрібна перевірка на
  прямі звернення до `Обработки.СМП_ОбработкаВыпискиБанка_*` у коді розширення; зміну
  доведеться заносити у сховище. Окрема задача.
- **Політика бінарних артефактів і GitHub Releases.** `.epf` поки лишаються в `epf/dist`.
- **CI.** Локального прогону тестів достатньо, доки контур не усталився.
- **Автоматичний коміт у сховище.** Свідомо не робиться: захоплення об'єктів командою
  робить це небезпечним.
