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

Describe 'Read-StorageReport (день, місяць, хвилина й секунда без провідного нуля)' {
    BeforeAll {
        $script:ShortComponentsFixture = Join-Path $PSScriptRoot 'fixtures/storage-report-short-components.txt'
        $script:ShortComponentsVersions = Read-StorageReport -Path $script:ShortComponentsFixture
    }

    It 'розбирає "Дата создания:" без провідного нуля в дні й місяці (3.5.2022)' {
        $script:ShortComponentsVersions[0].Date | Should -Be '3.5.2022'
    }

    It 'розбирає "Время создания:" без провідного нуля в хвилині й секунді (1:2:3)' {
        $script:ShortComponentsVersions[0].Time | Should -Be '1:2:3'
    }

    It 'складає Timestamp коректно й зберігає день перед місяцем (не плутає їх місцями)' {
        $script:ShortComponentsVersions[0].Timestamp | Should -Be ([datetime]'2022-05-03T01:02:03')
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

    It 'M1: обчислення максимальної версії (як у storage-sync.ps1) не падає на порожньому звіті' {
        # storage-sync.ps1 не імпортується як модуль (це скрипт-точка входу, а не
        # tools/lib/*.psm1) і не запускається у прогоні без реальної платформи чи
        # сховища, тому цей рядок перевіряється тут — на тому самому $all, який
        # storage-sync.ps1 отримує від Get-StorageVersions/Read-StorageReport для
        # порожнього сховища. Раніше storage-sync.ps1:89 робив
        # "($all | Select-Object -Last 1).Version", що під Set-StrictMode -Version
        # Latest падає на .Version від $null на порожньому $all — на рядок раніше за
        # дружню гілку "Нових версій немає".
        #
        # "Measure-Object -Property Version -Maximum" сам собою тут НЕ рятує: на справді
        # порожньому вводі він не дає об'єкт із Maximum=$null, а не дає нічого, і
        # ".Maximum" так само падає під strict mode — це підтверджує окремий It нижче.
        # Тому справжній фікс (і в storage-sync.ps1, і в Get-PendingVersions) перевіряє
        # Count першим.
        Set-StrictMode -Version Latest
        $versions = Read-StorageReport -Path $script:EmptyFixture

        $maxVersion = $null
        { if ($versions.Count -gt 0) { $maxVersion = ($versions | Measure-Object -Property Version -Maximum).Maximum } } |
            Should -Not -Throw
        $maxVersion | Should -BeNullOrEmpty
    }

    It 'Measure-Object -Maximum без перевірки Count все ще падає на СПРАВДІ порожньому вводі (документує, чому Count-перевірка обов''язкова)' {
        Set-StrictMode -Version Latest
        $versions = Read-StorageReport -Path $script:EmptyFixture

        { ($versions | Measure-Object -Property Version -Maximum).Maximum } | Should -Throw
    }
}

Describe 'Read-StorageReport (повна форма реального звіту: титул, мітка версії, розділи змінених об''єктів)' {
    # Фікстура відтворює форму, знайдену у справжніх звітах BankExchange_SMB/BankExchange_ACC
    # під час діагностики I1 (обрізаних коментарів у версіях 31/42): титульний рядок
    # табличного документа перед "Дата отчета:", пара "Метка:"/"Комментарий метки:" і три
    # розділи "Добавлены:"/"Изменены:"/"Удалены:" зі змінною кількістю об'єктів. Раніше все
    # це мовчки губилось (StorageReport.psm1:80-95 у версії до фіксу) — тепер розбирається
    # явно, нічого не кидаючи як помилку.
    BeforeAll {
        $script:FullShapeFixture = Join-Path $PSScriptRoot 'fixtures/storage-report-full-shape.txt'
        $script:FullShapeVersions = Read-StorageReport -Path $script:FullShapeFixture
    }

    It 'розбирає звіт, не спотикаючись об титульний рядок і "Дата отчета:"/"Время отчета:"' {
        $script:FullShapeVersions.Count | Should -Be 1
        $script:FullShapeVersions[0].Version | Should -Be 31
    }

    It 'зберігає посилання у коментарі цілим — не обрізає на "//"' {
        $script:FullShapeVersions[0].Comment |
            Should -Be 'Комітет з посиланням https://vsydorenko.worksection.com/project/43783/12712786/'
    }

    It 'не губить мітку версії й коментар до мітки' {
        $script:FullShapeVersions[0].Label        | Should -Be 'v851'
        $script:FullShapeVersions[0].LabelComment | Should -Be 'база не обновляється, поки не виправлять регістр'
    }

    It 'збирає розділи змінених об''єктів замість того, щоб їх губити' {
        $script:FullShapeVersions[0].Added    | Should -Be @('Документ.ПлатежноеПоручение', 'Обработка.БанкИКасса')
        $script:FullShapeVersions[0].Modified | Should -Be @('SMP_BankExchange_SMB')
        $script:FullShapeVersions[0].Deleted  | Should -Be @('Обработка.Старий')
    }
}

Describe 'Get-MxlStringCells (незакрита комірка)' {
    It 'кидає виняток, якщо файл обривається всередині відкритої комірки, а не мовчки губить її' {
        $fixture = Join-Path $PSScriptRoot 'fixtures/storage-report-unterminated-cell.txt'
        { Get-MxlStringCells -Lines (ConvertFrom-MxlText -Path $fixture) } |
            Should -Throw '*обірвався*'
    }
}

Describe 'Read-StorageReport (невідома форма комірки поза структурою)' {
    It 'кидає виняток замість того, щоб мовчки пропустити невпізнану комірку' {
        $fixture = Join-Path $PSScriptRoot 'fixtures/storage-report-unknown-cell.txt'
        { Read-StorageReport -Path $fixture } | Should -Throw '*Неочікувана комірка*'
    }
}

Describe 'Get-StorageVersions (команда, побудована для платформи — I1: -IncludeCommentLinesWithDoubleSlash)' {
    # Get-StorageVersions реально запускає 1cv8.exe (Invoke-V8Designer з V8.psm1) — тут
    # платформа не потрібна: мокається сам Invoke-V8Designer у приватній області модуля
    # StorageReport (де він з'являється як імпортована з V8.psm1 команда), щоб перевірити
    # САМЕ побудовані аргументи команди /ConfigurationRepositoryReport, а не поведінку
    # платформи. Мок не звертається до диска сховища — лише копіює вже наявну фікстуру
    # туди, куди мала б записати звіт платформа, щоб Read-StorageReport усередині
    # Get-StorageVersions відпрацював на реальному вмісті, а не впав на відсутньому файлі.
    BeforeAll {
        Mock -ModuleName StorageReport Invoke-V8Designer {
            param($IbSwitch, $Arguments, $User, $Password, $V8Path)
            $reportArg = $Arguments | Where-Object { $_ -like '/ConfigurationRepositoryReport*' }
            if ($reportArg -match '/ConfigurationRepositoryReport "([^"]+)"') {
                Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'fixtures/storage-report-sample.txt') `
                    -Destination $Matches[1] -Force
            }
            [pscustomobject]@{ ExitCode = 0; Output = '' }
        }
    }

    It 'вимагає -IncludeCommentLinesWithDoubleSlash — без цього ключа платформа сама обрізає коментар на "//" ще до того, як звіт потрапляє в цей інструмент (I1, підтверджено на v20/v31 BankExchange_SMB і v42 BankExchange_ACC)' {
        $workDir = Join-Path $TestDrive 'get-storage-versions-workdir'

        $null = Get-StorageVersions -IbSwitch '/F "X"' -StoragePath 'X' `
            -ExtensionName 'EXT' -StorageUser 'gitbot' -WorkDir $workDir

        Should -Invoke -ModuleName StorageReport Invoke-V8Designer -Times 1 -ParameterFilter {
            ($Arguments -join ' ') -match '-IncludeCommentLinesWithDoubleSlash'
        }
    }
}
