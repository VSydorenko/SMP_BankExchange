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
