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
