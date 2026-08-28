BeforeAll {
    Import-Module "$PSScriptRoot/../lib/Authors.psm1" -Force
    $script:MapFile = Join-Path $TestDrive 'AUTHORS'
    @(
        "Перший Тестовий=First Testovych <first.testovych@example.com>"
        "Другий Тестовий (nick2)=nick2 <nick2@example.com>"
        "# коментар, який треба пропустити"
        ""
    ) | Set-Content -LiteralPath $script:MapFile -Encoding UTF8
}

Describe 'Read-AuthorMap' {
    It 'читає записи у форматі Ім''я=Name <email>' {
        $map = Read-AuthorMap -Path $script:MapFile
        $map['Перший Тестовий'].Name  | Should -Be 'First Testovych'
        $map['Перший Тестовий'].Email | Should -Be 'first.testovych@example.com'
    }

    It 'витримує дужки в імені користувача сховища' {
        $map = Read-AuthorMap -Path $script:MapFile
        $map['Другий Тестовий (nick2)'].Name | Should -Be 'nick2'
    }

    It 'ігнорує коментарі й порожні рядки' {
        (Read-AuthorMap -Path $script:MapFile).Count | Should -Be 2
    }
}

Describe 'Resolve-Author' {
    It 'повертає git-автора для відомого користувача' {
        $map = Read-AuthorMap -Path $script:MapFile
        (Resolve-Author -Map $map -StorageUser 'Перший Тестовий').Email |
            Should -Be 'first.testovych@example.com'
    }

    It 'кидає виняток на невідомому користувачі' {
        $map = Read-AuthorMap -Path $script:MapFile
        { Resolve-Author -Map $map -StorageUser 'Хтось Новий' } | Should -Throw '*AUTHORS*'
    }

    It 'кидає виняток з поясненням причини, а не звинувачує AUTHORS, коли автор порожній' {
        # Порожній User — ознака обрізаного/пошкодженого звіту сховища (Task 2), а не
        # "автора немає в AUTHORS". Це різні проблеми з різними виправленнями, тому
        # перевіряємо саме зміст повідомлення, а не сам факт винятку.
        $map = Read-AuthorMap -Path $script:MapFile
        $err = { Resolve-Author -Map $map -StorageUser '' } | Should -Throw -PassThru
        $err.Exception.Message | Should -Match 'пошкодж'
        $err.Exception.Message | Should -Not -Match 'AUTHORS'
    }
}

Describe 'Get-UnknownAuthors' {
    It 'повертає лише тих, кого немає в мапі, без повторів' {
        $map = Read-AuthorMap -Path $script:MapFile
        Get-UnknownAuthors -Map $map -StorageUsers @(
            'Перший Тестовий', 'Хтось Новий', 'Хтось Новий') |
            Should -Be @('Хтось Новий')
    }

    It 'повертає порожній масив, а не $null, коли всі автори відомі' {
        # Set-StrictMode тут відтворює умову виклику з боку Task 5 (storage-sync.ps1),
        # який працює під Set-StrictMode -Version Latest: під ним $null.Count кидає
        # виняток, тоді як без strict mode PowerShell тихо повертає 0. Тест ловить
        # регресію, якщо унарну кому перед @(...) у реалізації прибрати.
        Set-StrictMode -Version Latest
        $map = Read-AuthorMap -Path $script:MapFile
        $unknown = Get-UnknownAuthors -Map $map -StorageUsers @('Перший Тестовий')
        { $unknown.Count } | Should -Not -Throw
        $unknown.Count | Should -Be 0
    }

    It 'позначає порожній запис автора зрозумілим повідомленням замість порожнього рядка' {
        # Порожній StorageUser не повинен ні впасти на байндингу параметра, ні мовчки
        # зникнути в результаті як невидимий порожній рядок — оператор має побачити
        # причину прямо в прев'ю-виводі storage-sync.ps1.
        $map = Read-AuthorMap -Path $script:MapFile
        $unknown = Get-UnknownAuthors -Map $map -StorageUsers @('Перший Тестовий', '')
        $unknown.Count | Should -Be 1
        $unknown[0] | Should -Not -BeNullOrEmpty
        $unknown[0] | Should -Match 'пошкодж'
    }
}
