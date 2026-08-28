#Requires -Version 7
# Регресія на дефект вкладеного Import-Module -Force: storage-sync.ps1 імпортує
# PathSafety, V8, StorageReport, Authors, SyncState по черзі в такому самому порядку і
# потім з власної (глобальної) області викликає функції з кожного з них напряму —
# New-ExtensionInfobase, Invoke-V8Designer, Assert-SafeWorkPath тощо. tools/lib/
# StorageReport.psm1 сам усередині себе робить "Import-Module V8.psm1 -Force"; викликаний
# як вкладений імпорт (модуль завантажується під час імпорту іншого модуля), -Force
# вивантажує вже наявний глобальний екземпляр V8 і підвантажує його заново в приватну
# область StorageReport — глобальна область втрачає доступ до експортів V8. Той самий
# ризик тепер стоїть і за PathSafety, яку вкладено (без -Force) імпортують і V8.psm1, і
# SyncState.psm1. Жоден інший тест не імпортує всі п'ять модулів у цьому порядку з
# глобальної області, тож дефект не ловився.
#
# Запускається окремим процесом pwsh (fixtures/module-visibility-probe.ps1), а не
# Import-Module у поточній сесії Pester: інші *.Tests.ps1 у тому самому прогоні
# Run-Tests.ps1 вже тримають завантаженими окремі екземпляри V8/StorageReport під
# тими самими іменами модулів; повторний імпорт тут у процесі призводить до
# "Multiple script or manifest modules named 'V8' are currently loaded" — той самий
# конфлікт, що вже описаний у StorageSync.Tests.ps1. Окремий процес повністю
# ізолює простір модулів.

Describe 'Порядок імпорту модулів у storage-sync.ps1' {
    BeforeAll {
        $script:LibDir   = (Resolve-Path "$PSScriptRoot/../lib").Path
        $script:ProbeFile = (Resolve-Path "$PSScriptRoot/fixtures/module-visibility-probe.ps1").Path

        # Саме ті команди, які storage-sync.ps1 викликає напряму з власного тіла
        # (а не лише зсередини одного з lib-модулів) — тобто ті, що мають лишитись
        # видимими в глобальній області після всіх чотирьох імпортів.
        $script:RequiredCommands = @(
            'Assert-SafeWorkPath'
            'New-ExtensionInfobase'
            'Invoke-V8Designer'
            'Get-StorageVersions'
            'Read-AuthorMap'
            'Resolve-Author'
            'Get-UnknownAuthors'
            'Read-SyncState'
            'Write-SyncState'
            'Get-PendingVersions'
        )

        $csv = $script:RequiredCommands -join ','
        $output = & pwsh -NoProfile -File $script:ProbeFile -LibDir $script:LibDir -CommandsCsv $csv 2>&1 |
            Out-String

        $script:ProbeExitCode = $LASTEXITCODE
        $script:ProbeOutput   = $output

        $script:Visibility = @{}
        foreach ($line in ($output -split "`r?`n")) {
            if ($line -match '^(?<name>\S+)=(?<value>True|False)$') {
                $script:Visibility[$Matches.name] = [bool]::Parse($Matches.value)
            }
        }
    }

    It 'усі функції, які storage-sync.ps1 викликає напряму, лишаються видимими після імпорту всіх чотирьох модулів' {
        $script:ProbeExitCode | Should -Be 0 -Because "probe мав відпрацювати без винятку; вивід:`n$script:ProbeOutput"

        foreach ($name in $script:RequiredCommands) {
            $script:Visibility.ContainsKey($name) |
                Should -BeTrue -Because "probe мав вивести результат для '$name'; повний вивід:`n$script:ProbeOutput"
            $script:Visibility[$name] |
                Should -BeTrue -Because "'$name' має бути видимою у глобальній області після імпорту всіх модулів у порядку storage-sync.ps1"
        }
    }
}
