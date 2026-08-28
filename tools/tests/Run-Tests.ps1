#Requires -Version 7
<#
.SYNOPSIS
    Прогін тестового набору tools/tests через Pester.
.DESCRIPTION
    За замовчуванням запускає все, включно з тестами під тегом Integration
    (New-ExtensionInfobase у V8.Tests.ps1), які реально запускають 1cv8.exe,
    створюють файлову інформаційну базу й завантажують у неї розширення — це вже
    не read-only операція. M8 фінального ревʼю: .claude/settings.json auto-allow
    (без запиту) дозволяє лише виклик із -ExcludeTag Integration, який лишається
    суто читанням; повний прогін (цей файл без параметрів, як у "Типових операціях"
    CLAUDE.md) і надалі питає підтвердження.
.EXAMPLE
    pwsh tools/tests/Run-Tests.ps1                            # усе, разом з Integration
    pwsh tools/tests/Run-Tests.ps1 -ExcludeTag Integration     # без запуску платформи
#>
[CmdletBinding()]
param(
    [string[]]$ExcludeTag = @()
)

Import-Module Pester -MinimumVersion 5.0
$config = New-PesterConfiguration
$config.Run.Path = $PSScriptRoot
$config.Output.Verbosity = 'Detailed'
$config.Run.Exit = $true
if ($ExcludeTag) { $config.Filter.ExcludeTag = $ExcludeTag }
Invoke-Pester -Configuration $config
