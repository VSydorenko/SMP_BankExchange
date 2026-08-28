BeforeAll {
    Import-Module "$PSScriptRoot/../lib/V8.psm1" -Force
}

Describe 'ConvertTo-V8IbSwitch' {
    It 'перетворює файловий рядок підключення на /F' {
        ConvertTo-V8IbSwitch -Connection 'File="C:\bases\demo";' |
            Should -Be '/F "C:\bases\demo"'
    }

    It 'перетворює серверний рядок підключення на /S' {
        ConvertTo-V8IbSwitch -Connection 'Srvr="SRV01";Ref="DEMO_BASE";' |
            Should -Be '/S "SRV01\DEMO_BASE"'
    }

    It 'не залежить від регістру ключів і зайвих пробілів' {
        ConvertTo-V8IbSwitch -Connection '  srvr = "SRV01" ; ref = "DEMO_BASE" ; ' |
            Should -Be '/S "SRV01\DEMO_BASE"'
    }

    It 'приймає голий шлях як файлову базу' {
        ConvertTo-V8IbSwitch -Connection 'C:\bases\demo' |
            Should -Be '/F "C:\bases\demo"'
    }

    It 'кидає виняток на порожньому значенні' {
        { ConvertTo-V8IbSwitch -Connection '' } | Should -Throw
    }
}

Describe 'Read-V8LocalConnection' {
    BeforeEach {
        $script:LocalFile = Join-Path $TestDrive ([guid]::NewGuid().ToString('N') + '.yaml')
    }

    It 'читає і connection, і user з одного файлу правильно (ловить помилку порядку читання $Matches)' {
        # $Matches — одна спільна змінна на обидва -match. Якщо реалізація дістає значення
        # connection з $Matches ПІСЛЯ того, як виконався -match для user (а не одразу після
        # свого власного -match), Connection повернеться порожнім/іншим, бо іменована група
        # 'c' у $Matches до того моменту вже перезаписана групою 'u'. Значення тут навмисно
        # різні й неспівпадаючі за формою, щоб таку підміну неможливо було не помітити.
        Set-Content -LiteralPath $script:LocalFile -Encoding UTF8 -Value @(
            'infobase:'
            "  connection: 'Srvr=""SRV01"";Ref=""DEMO_BASE"";'"
            "  user: 'probe-user'"
        )

        $result = Read-V8LocalConnection -Path $script:LocalFile

        $result.Connection | Should -Be 'Srvr="SRV01";Ref="DEMO_BASE";'
        $result.User       | Should -Be 'probe-user'
    }

    It 'кидає виняток з дією, якщо файл відсутній' {
        $missing = Join-Path $TestDrive 'no-such.yaml'
        { Read-V8LocalConnection -Path $missing } | Should -Throw '*Не знайдено*'
    }

    It 'кидає виняток, якщо рядка connection: немає' {
        Set-Content -LiteralPath $script:LocalFile -Encoding UTF8 -Value @(
            'infobase:'
            "  user: 'probe-user'"
        )

        { Read-V8LocalConnection -Path $script:LocalFile } | Should -Throw '*connection*'
    }

    It 'кидає виняток, якщо рядок connection: не збігається з очікуваним форматом' {
        Set-Content -LiteralPath $script:LocalFile -Encoding UTF8 -Value @(
            'infobase:'
            '  connection: без лапок'
        )

        { Read-V8LocalConnection -Path $script:LocalFile } | Should -Throw '*connection*'
    }

    It 'повертає порожній User, якщо рядка user: немає — не кидає виняток' {
        Set-Content -LiteralPath $script:LocalFile -Encoding UTF8 -Value @(
            'infobase:'
            "  connection: 'File=""C:\bases\demo"";'"
        )

        $result = Read-V8LocalConnection -Path $script:LocalFile

        $result.Connection | Should -Be 'File="C:\bases\demo";'
        $result.User       | Should -Be ''
    }
}

Describe 'Assert-NoLicenseProblem' {
    It 'пропускає чистий рядок без згадки ліцензії' {
        InModuleScope V8 {
            { Assert-NoLicenseProblem -Output 'Конфигурация обновлена успешно' } | Should -Not -Throw
        }
    }

    It 'кидає виняток, якщо у виводі є HASP' {
        InModuleScope V8 {
            { Assert-NoLicenseProblem -Output 'Ошибка: HASP-ключ не найден' } | Should -Throw
        }
    }

    It 'кидає виняток, якщо у виводі є "лиценз"' {
        InModuleScope V8 {
            { Assert-NoLicenseProblem -Output 'Не удалось получить лицензию' } | Should -Throw
        }
    }

    It 'пропускає порожній рядок' {
        InModuleScope V8 {
            { Assert-NoLicenseProblem -Output '' } | Should -Not -Throw
        }
    }
}

Describe 'New-ExtensionInfobase' -Tag 'Integration' {
    It 'створює базу з розширенням, адресованим під заданим іменем' {
        $ib = Join-Path $TestDrive 'ext-ib'
        $stub = Join-Path $PSScriptRoot '../assets/empty-extension'

        $ibSwitch = New-ExtensionInfobase -Path $ib -ExtensionName 'PROBE_EXT' -StubPath $stub
        $ibSwitch | Should -Be ('/F "{0}"' -f $ib)

        $dump = Join-Path $TestDrive 'ext-dump'
        New-Item -ItemType Directory -Path $dump -Force | Out-Null
        $res = Invoke-V8Designer -IbSwitch $ibSwitch -Arguments @(
            '/DumpConfigToFiles "{0}" -Extension PROBE_EXT' -f $dump)
        $res.ExitCode | Should -Be 0
        Test-Path (Join-Path $dump 'Configuration.xml') | Should -BeTrue

        $dumpMissing = Join-Path $TestDrive 'ext-dump-missing'
        New-Item -ItemType Directory -Path $dumpMissing -Force | Out-Null
        $resMissing = Invoke-V8Designer -IbSwitch $ibSwitch -Arguments @(
            '/DumpConfigToFiles "{0}" -Extension NEVER_CREATED' -f $dumpMissing)
        $resMissing.ExitCode | Should -Not -Be 0
    }
}
