#Requires -Version 7
<#
.SYNOPSIS
    Допоміжний скрипт для ModuleImportOrder.Tests.ps1. Імпортує п'ять lib-модулів
    точно в тому порядку, в якому це робить tools/storage-sync.ps1, і для кожної
    переданої команди друкує "Ім'я=True" або "Ім'я=False" залежно від того, чи
    видно її в глобальній області після всіх імпортів.

    Навмисно окремий файл, а не інлайн-рядок у тесті: так probe можна прогнати й
    вручну (наприклад, щоб побачити дефект наживо, а не лише в PesterAssertion).
#>
param(
    [Parameter(Mandatory)][string]$LibDir,
    [Parameter(Mandatory)][string]$CommandsCsv
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $LibDir 'PathSafety.psm1') -Force
Import-Module (Join-Path $LibDir 'V8.psm1') -Force
Import-Module (Join-Path $LibDir 'StorageReport.psm1') -Force
Import-Module (Join-Path $LibDir 'Authors.psm1') -Force
Import-Module (Join-Path $LibDir 'SyncState.psm1') -Force

foreach ($name in ($CommandsCsv -split ',')) {
    $found = [bool](Get-Command -Name $name -ErrorAction SilentlyContinue)
    "$name=$found"
}
