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

Describe 'Read-V8LocalStoragePath' {
    BeforeEach {
        $script:LocalFile = Join-Path $TestDrive ([guid]::NewGuid().ToString('N') + '.yaml')
    }

    It 'повертає порожній рядок, а не кидає виняток, якщо файл відсутній — перевизначення просто немає' {
        $missing = Join-Path $TestDrive 'no-such.yaml'
        Read-V8LocalStoragePath -Path $missing | Should -Be ''
    }

    It 'повертає порожній рядок, якщо файл є, а рядка storagePath: немає' {
        Set-Content -LiteralPath $script:LocalFile -Encoding UTF8 -Value @(
            'infobase:'
            "  connection: 'File=""C:\bases\demo"";'"
        )

        Read-V8LocalStoragePath -Path $script:LocalFile | Should -Be ''
    }

    It 'читає storagePath: з верхнього рівня, поза infobase:' {
        Set-Content -LiteralPath $script:LocalFile -Encoding UTF8 -Value @(
            'infobase:'
            "  connection: 'File=""C:\bases\demo"";'"
            "storagePath: 'D:\Сховища\ІншийРозробник'"
        )

        Read-V8LocalStoragePath -Path $script:LocalFile | Should -Be 'D:\Сховища\ІншийРозробник'
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

Describe 'New-V8FileInfobase (запобіжник шляху, без звернення до платформи)' {
    It 'кидає виняток на шляху поза -MustBeUnder — до Get-V8Path, незалежно від того, чи встановлена платформа' {
        $outside = Join-Path $TestDrive 'not-the-work-dir'
        $boundary = Join-Path $TestDrive 'work-dir'
        New-Item -ItemType Directory -Path $boundary -Force | Out-Null

        { New-V8FileInfobase -Path $outside -MustBeUnder $boundary } | Should -Throw '*не є підтекою*'
    }

    It 'кидає виняток на порожньому Path' {
        $boundary = Join-Path $TestDrive 'work-dir-2'
        New-Item -ItemType Directory -Path $boundary -Force | Out-Null

        { New-V8FileInfobase -Path '' -MustBeUnder $boundary } | Should -Throw
    }
}

Describe 'New-ExtensionInfobase' -Tag 'Integration' {
    It 'створює базу з розширенням, адресованим під заданим іменем' {
        $ib = Join-Path $TestDrive 'ext-ib'
        $stub = Join-Path $PSScriptRoot '../assets/empty-extension'

        $ibSwitch = New-ExtensionInfobase -Path $ib -ExtensionName 'PROBE_EXT' -StubPath $stub -MustBeUnder $TestDrive
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
