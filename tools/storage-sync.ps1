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
# PathSafety — першою: V8.psm1 і SyncState.psm1 самі вкладено імпортують її (без -Force,
# та сама обережність, що й довкола V8.psm1 у StorageReport.psm1 — див. коментар там).
# Завантаживши її тут глобально й раніше за них, вкладені імпорти лише підтвердять, що
# вона вже є, замість ризикувати повторним перезавантаженням у приватну область.
Import-Module (Join-Path $PSScriptRoot 'lib/PathSafety.psm1') -Force
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
$workDir   = Join-Path $repoRoot 'build/sync' $Product
$ibPath    = Join-Path $workDir 'ib'
$stubPath  = Join-Path $PSScriptRoot 'assets/empty-extension'

Write-Host "Продукт:    $Product"
Write-Host "Розширення: $($state.ExtensionName)"
Write-Host "Сховище:    $($state.StoragePath)"
Write-Host "Залито:     версія $($state.LastSyncedVersion)"

if ($Apply) {
    # Запобіжник: якщо попередній прогін -Apply перервався між видаленням $sourceDir і його
    # повторним наповненням (або між комітом і оновленням storage.json), робоча копія лишається
    # "брудною" — git status це покаже. Починати новий прогін поверх такого стану небезпечно:
    # наступний виток мовчки закомітить чужі рештки або перезапише запис версії. Тому зупиняємось
    # і віддаємо розбір людині, а не вгадуємо. Перевірка стоїть тут — до створення тимчасової ІБ
    # і до звернення до сховища — щоб падати одразу, а не після хвилини роботи платформи.
    $dirty = git -C $repoRoot status --porcelain -- $Product
    if ($dirty) {
        throw "Робоча копія '$Product' не чиста перед запуском -Apply — можливо, попередній прогін " +
              "перервався на середині версії. Перевірте 'git status' і приведіть дерево до стану HEAD " +
              "(або завершіть коміт вручну), перш ніж повторювати -Apply."
    }
}

if (-not (Test-Path -LiteralPath $state.StoragePath)) {
    throw "Каталог сховища не знайдено: $($state.StoragePath)"
}

# Робоча тека створюється з нуля на кожен запуск — щоб не тягнути стан попереднього.
if (Test-Path -LiteralPath $workDir) { Remove-Item -LiteralPath $workDir -Recurse -Force }
New-Item -ItemType Directory -Path $workDir -Force | Out-Null

Write-Host 'Створюю тимчасову ІБ і читаю історію сховища...'
$ibSwitch = New-ExtensionInfobase -Path $ibPath -ExtensionName $state.ExtensionName `
    -StubPath $stubPath -MustBeUnder $workDir
$all      = Get-StorageVersions -IbSwitch $ibSwitch -StoragePath $state.StoragePath `
                -ExtensionName $state.ExtensionName -StorageUser $StorageUser -WorkDir $workDir

Write-Host "У сховищі версій: $($all.Count), максимальна: $(($all | Select-Object -Last 1).Version)"

$pending = Get-PendingVersions -AllVersions $all -LastSynced $state.LastSyncedVersion
# @(...) навколо Select-Object -First — інакше рівно один елемент, що лишився після обрізання
# -MaxVersions, розгортається PowerShell у скаляр, і подальші $pending.Count падають під StrictMode.
if ($MaxVersions -gt 0) { $pending = @($pending | Select-Object -First $MaxVersions) }

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
    # Assert-SafeWorkPath тут — друга лінія оборони поверх перевірки в Read-SyncState
    # (state вже прочитаний раніше й не змінюється між ними, але видалення — це саме та
    # операція, для якої I2 просить перевірку безпосередньо перед нею, а не лише один раз
    # десь раніше в скрипті).
    Assert-SafeWorkPath -Path $sourceDir -MustBeUnder $productPath -Description "sourceDir продукту $Product"
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
    # Сирий користувач сховища — окремо від author.Name (яке могло бути власницьким
    # рішенням, а не стабільним фактом, як у разових мапінгів AUTHORS). Трейлер лишає факт
    # доступним для перевірки й виправлення навіть якщо атрибуція виявиться неточною.
    $message.Add("Storage-User: $($v.User)")

    $msgFile = Join-Path $workDir 'commit-message.txt'
    ($message -join "`n") | Set-Content -LiteralPath $msgFile -Encoding UTF8

    $stamp = $v.Timestamp.ToString('yyyy-MM-ddTHH:mm:ss')
    $env:GIT_AUTHOR_DATE    = $stamp
    $env:GIT_COMMITTER_DATE = $stamp
    try {
        git -C $repoRoot add -A -- $Product

        # Дві сусідні версії сховища можуть дати побайтово однаковий дамп (версія змінила щось
        # поза XML-вивантаженням) — тоді "git commit" без --allow-empty впав би з ненульовим
        # кодом на кожному такому прогоні. Коміт все одно потрібен: він — єдиний носій автора,
        # дати й коментаря цієї версії сховища. --allow-empty дозволяє порожній за вмістом
        # коміт, не приховуючи при цьому жодної реальної помилки git — код виходу перевіряється
        # так само нижче.
        git -C $repoRoot diff --cached --quiet -- $Product
        if ($LASTEXITCODE -eq 0) {
            Write-Host '  (без змін у джерелах — коміт лише фіксує запис версії сховища)' -ForegroundColor DarkGray
        }

        git -C $repoRoot commit --author="$($author.Name) <$($author.Email)>" -F $msgFile --quiet --allow-empty
        if ($LASTEXITCODE -ne 0) { throw "git commit завершився з кодом $LASTEXITCODE" }
    }
    finally {
        Remove-Item Env:GIT_AUTHOR_DATE, Env:GIT_COMMITTER_DATE -ErrorAction SilentlyContinue
    }
}

Write-Host ''
Write-Host "Готово. Перенесено версій: $($pending.Count)." -ForegroundColor Green
