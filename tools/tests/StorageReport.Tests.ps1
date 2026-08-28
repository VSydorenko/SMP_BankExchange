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

Describe 'Read-StorageReport (час без провідного нуля в годині)' {
    BeforeAll {
        $script:ShortHourFixture = Join-Path $PSScriptRoot 'fixtures/storage-report-short-hour.txt'
        $script:ShortHourVersions = Read-StorageReport -Path $script:ShortHourFixture
    }

    It 'розбирає "Время создания:" без провідного нуля в годині (1:27:39)' {
        $script:ShortHourVersions[0].Time | Should -Be '1:27:39'
    }

    It 'складає Timestamp коректно навіть без провідного нуля' {
        $script:ShortHourVersions[0].Timestamp | Should -Be ([datetime]'2022-05-24T01:27:39')
    }
}

Describe 'Read-StorageReport (звіт без версій)' {
    BeforeAll { $script:EmptyFixture = Join-Path $PSScriptRoot 'fixtures/storage-report-empty.txt' }

    It 'повертає порожній масив, а не $null' {
        # Set-StrictMode тут відтворює умову виклику з боку Task 5 (storage-sync.ps1),
        # який працює під Set-StrictMode -Version Latest: під ним $null.Count кидає
        # виняток, тоді як без strict mode PowerShell тихо повертає 0.
        Set-StrictMode -Version Latest
        $versions = Read-StorageReport -Path $script:EmptyFixture
        { $versions.Count } | Should -Not -Throw
        $versions.Count | Should -Be 0
    }
}
