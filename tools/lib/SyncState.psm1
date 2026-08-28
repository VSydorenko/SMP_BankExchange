#Requires -Version 7
Set-StrictMode -Version Latest

# Без -Force: те саме застереження, що й у StorageReport.psm1 для V8 — вкладений
# Import-Module тут не повинен перезавантажувати вже наявний глобальний PathSafety.
Import-Module "$PSScriptRoot/PathSafety.psm1"

function Read-SyncState {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$ProductPath)

    $file = Join-Path $ProductPath 'storage.json'
    if (-not (Test-Path -LiteralPath $file)) {
        throw "Файл storage.json не знайдено в $ProductPath"
    }

    $json = Get-Content -LiteralPath $file -Raw -Encoding UTF8 | ConvertFrom-Json

    # storage.json пишеться вручну при підключенні продукту — sourcePath доходить
    # звідси прямісінько до Remove-Item -Recurse -Force у storage-sync.ps1. Порожній чи
    # такий, що містить "..", рядок мав би провалитись глибоко всередині -Apply, під час
    # видалення; перевірка тут ловить його одразу при читанні й називає файл, що завинив.
    # Join-Path на порожньому sourcePath повертає сам $ProductPath незмінним — саме тому
    # Assert-SafeWorkPath отримує вже складений шлях, а не сирий фрагмент: перевірка
    # "не дорівнює межі" має побачити результат так само, як його побачить Remove-Item.
    Assert-SafeWorkPath -Path (Join-Path $ProductPath ([string]$json.sourcePath)) `
        -MustBeUnder $ProductPath -Description "sourcePath у $file"

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

    # M1 (розширено): на СПРАВДІ порожньому $AllVersions (сховище без жодної версії)
    # "(@() | Measure-Object -Property Version -Maximum)" не повертає об'єкт із Maximum=$null,
    # а не повертає нічого — і ".Maximum" на цьому "нічого" падає під
    # Set-StrictMode -Version Latest з "властивість 'Maximum' не знайдено", а не тихо дає
    # $null. Той самий клас дефекту, що й у storage-sync.ps1 на сусідньому рядку (обчислення
    # максимальної версії для виводу) — і без цієї перевірки тут дружня гілка "Нових версій
    # немає" у storage-sync.ps1 однаково лишалась би недосяжною для порожнього сховища:
    # виняток стався б тут, на рядок раніше.
    $max = $null
    if ($AllVersions.Count -gt 0) {
        $max = ($AllVersions | Measure-Object -Property Version -Maximum).Maximum
    }
    if ($null -ne $max -and $LastSynced -gt $max) {
        throw "git попереду сховища: залито версію $LastSynced, а у сховищі максимум $max. " +
              "Синхронізацію зупинено, розберіться з розбіжністю вручну."
    }

    , @($AllVersions | Where-Object { $_.Version -gt $LastSynced } | Sort-Object Version)
}

Export-ModuleMember -Function Read-SyncState, Write-SyncState, Get-PendingVersions
