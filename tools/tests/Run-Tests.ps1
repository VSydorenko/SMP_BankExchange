#Requires -Version 7
Import-Module Pester -MinimumVersion 5.0
$config = New-PesterConfiguration
$config.Run.Path = $PSScriptRoot
$config.Output.Verbosity = 'Detailed'
$config.Run.Exit = $true
Invoke-Pester -Configuration $config
