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

    It 'кидає виняток на порожньому sourcePath — I2: сьогодні саме це мовчки стирає весь каталог продукту' {
        # Відтворює репродукцію ревʼювера буквально: "sourcePath": "" у storage.json
        # робить Join-Path $productPath "" рівним самому продукту, і -Apply стирав би
        # увесь каталог, включно з негітованим v8project.local.yaml. Перевірка тут ловить
        # це при читанні storage.json, до будь-якого Remove-Item.
        @{
            storagePath       = 'R:\Сховища\Тест'
            extensionName     = 'Test_Extension'
            lastSyncedVersion = 23
            sourcePath        = ''
        } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $script:Product 'storage.json') -Encoding UTF8

        { Read-SyncState -ProductPath $script:Product } | Should -Throw '*sourcePath*'
    }

    It 'кидає виняток, якщо sourcePath містить ".."' {
        @{
            storagePath       = 'R:\Сховища\Тест'
            extensionName     = 'Test_Extension'
            lastSyncedVersion = 23
            sourcePath        = '..\..\Windows'
        } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $script:Product 'storage.json') -Encoding UTF8

        { Read-SyncState -ProductPath $script:Product } | Should -Throw '*sourcePath*'
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

    It 'повертає порожній масив, а не $null, коли все залито' {
        # Set-StrictMode тут відтворює умову виклику з боку Task 5 (storage-sync.ps1),
        # який працює під Set-StrictMode -Version Latest: під ним $null.Count кидає
        # виняток, тоді як без strict mode PowerShell тихо повертає 0. Тест ловить
        # регресію, якщо унарну кому перед @(...) у реалізації прибрати.
        Set-StrictMode -Version Latest
        $pending = Get-PendingVersions -AllVersions $script:All -LastSynced 47
        { $pending.Count } | Should -Not -Throw
        $pending.Count | Should -Be 0
    }

    It 'кидає виняток, коли git попереду сховища' {
        { Get-PendingVersions -AllVersions $script:All -LastSynced 99 } |
            Should -Throw '*попереду*'
    }

    It 'M1: не падає на СПРАВДІ порожньому $AllVersions (сховище без жодної версії)' {
        # На відміну від "повертає порожній масив, а не $null, коли все залито" вище,
        # $All там ніколи не порожній сам по собі — фільтрація до порожнього набору
        # відбувається вже ВСЕРЕДИНІ функції. Тут $AllVersions порожній із самого початку:
        # "(@() | Measure-Object -Property Version -Maximum)" не дає об'єкт із Maximum=$null,
        # а не дає нічого, і ".Maximum" на цьому падає під Set-StrictMode -Version Latest —
        # рядком раніше за дружню гілку "Нових версій немає" у storage-sync.ps1.
        Set-StrictMode -Version Latest
        { Get-PendingVersions -AllVersions @() -LastSynced 0 } | Should -Not -Throw
        (Get-PendingVersions -AllVersions @() -LastSynced 0).Count | Should -Be 0
    }
}
