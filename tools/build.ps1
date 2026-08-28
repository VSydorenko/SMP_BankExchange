#Requires -Version 7
<#
.SYNOPSIS
    Збирає .cfe розширень і .epf обробок у build/artifacts.
.DESCRIPTION
    Збірка йде платформою напряму, а не через Unica: операція make в Unica на Windows
    падає на публікації артефакту ("Отказано в доступе, os error 5"), лишаючи файл
    у стейджі.
.EXAMPLE
    pwsh tools/build.ps1 -Product BankExchange_SMBru -Apply
    pwsh tools/build.ps1 -Product epf -Apply
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
        $ibSwitch = '/F "{0}"' -f (New-V8FileInfobase -Path $buildIb -MustBeUnder (Join-Path $repoRoot 'build'))
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

    $ibSwitch = New-ExtensionInfobase -Path $buildIb -ExtensionName $state.ExtensionName `
        -StubPath $stubPath -MustBeUnder (Join-Path $repoRoot 'build')
    $load = Invoke-V8Designer -IbSwitch $ibSwitch -Arguments @(
        '/LoadConfigFromFiles "{0}" -Extension {1}' -f $src, $state.ExtensionName)
    if ($load.ExitCode -ne 0) { throw "Завантаження $($state.ExtensionName) не вдалося: $($load.Output)" }

    $dump = Invoke-V8Designer -IbSwitch $ibSwitch -Arguments @(
        '/DumpCfg "{0}" -Extension {1}' -f $target, $state.ExtensionName)
    if ($dump.ExitCode -ne 0) { throw "Збірка $($state.ExtensionName) не вдалася: $($dump.Output)" }
}

Get-ChildItem -LiteralPath $outDir | Select-Object Name, Length | Format-Table
Write-Host 'Готово.' -ForegroundColor Green
