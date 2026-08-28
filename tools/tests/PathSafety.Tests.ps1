BeforeAll {
    Import-Module "$PSScriptRoot/../lib/PathSafety.psm1" -Force
}

Describe 'Assert-SafeWorkPath' {
    BeforeEach {
        $script:Boundary = Join-Path $TestDrive 'product'
        New-Item -ItemType Directory -Path $script:Boundary -Force | Out-Null
    }

    It 'пропускає власну підтеку межі, нічого не кидаючи' {
        $safe = Join-Path $script:Boundary 'cfe/src'
        { Assert-SafeWorkPath -Path $safe -MustBeUnder $script:Boundary -Description 'тест' } |
            Should -Not -Throw
    }

    It 'кидає виняток на порожньому рядку — I2: саме цей випадок сьогодні мовчки стирає весь каталог продукту' {
        # Join-Path $Boundary '' повертає сам $Boundary — той-таки сценарій із
        # "sourcePath": "" у storage.json, який реально видаляв весь каталог продукту
        # разом із негітованим v8project.local.yaml (I2 у фінальному ревʼю).
        $collapsedToBoundary = Join-Path $script:Boundary ''
        { Assert-SafeWorkPath -Path $collapsedToBoundary -MustBeUnder $script:Boundary -Description 'sourceDir' } |
            Should -Throw
    }

    It 'кидає виняток на самій лише пробільній стрічці' {
        { Assert-SafeWorkPath -Path '   ' -MustBeUnder $script:Boundary -Description 'sourceDir' } |
            Should -Throw
    }

    It 'кидає виняток, якщо шлях дорівнює самій межі (не власна підтека)' {
        { Assert-SafeWorkPath -Path $script:Boundary -MustBeUnder $script:Boundary -Description 'sourceDir' } |
            Should -Throw '*не є підтекою*'
    }

    It 'кидає виняток, якщо шлях містить сегмент ".."' {
        $escaping = Join-Path $script:Boundary '..\..\Windows'
        { Assert-SafeWorkPath -Path $escaping -MustBeUnder $script:Boundary -Description 'sourceDir' } |
            Should -Throw '*..*'
    }

    It 'кидає виняток, якщо шлях лежить поза межею навіть без ".."' {
        $outside = Join-Path $TestDrive 'not-the-product'
        { Assert-SafeWorkPath -Path $outside -MustBeUnder $script:Boundary -Description 'sourceDir' } |
            Should -Throw '*не є підтекою*'
    }

    It 'повідомлення про помилку називає Description, щоб було видно, яке саме поле завинило' {
        { Assert-SafeWorkPath -Path '' -MustBeUnder $script:Boundary -Description 'sourcePath у storage.json продукту XYZ' } |
            Should -Throw '*sourcePath у storage.json продукту XYZ*'
    }
}
