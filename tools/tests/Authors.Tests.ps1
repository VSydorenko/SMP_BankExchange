BeforeAll {
    Import-Module "$PSScriptRoot/../lib/Authors.psm1" -Force
    $script:MapFile = Join-Path $TestDrive 'AUTHORS'
    @(
        "Володимир Сидоренко=Volodymyr Sydorenko <v.m.sydorenko@gmail.com>"
        "Олександр (alexsvlight)=alexsvlight <alexsv2012@gmail.com>"
        "# коментар, який треба пропустити"
        ""
    ) | Set-Content -LiteralPath $script:MapFile -Encoding UTF8
}

Describe 'Read-AuthorMap' {
    It 'читає записи у форматі Ім''я=Name <email>' {
        $map = Read-AuthorMap -Path $script:MapFile
        $map['Володимир Сидоренко'].Name  | Should -Be 'Volodymyr Sydorenko'
        $map['Володимир Сидоренко'].Email | Should -Be 'v.m.sydorenko@gmail.com'
    }

    It 'витримує дужки в імені користувача сховища' {
        $map = Read-AuthorMap -Path $script:MapFile
        $map['Олександр (alexsvlight)'].Name | Should -Be 'alexsvlight'
    }

    It 'ігнорує коментарі й порожні рядки' {
        (Read-AuthorMap -Path $script:MapFile).Count | Should -Be 2
    }
}

Describe 'Resolve-Author' {
    It 'повертає git-автора для відомого користувача' {
        $map = Read-AuthorMap -Path $script:MapFile
        (Resolve-Author -Map $map -StorageUser 'Володимир Сидоренко').Email |
            Should -Be 'v.m.sydorenko@gmail.com'
    }

    It 'кидає виняток на невідомому користувачі' {
        $map = Read-AuthorMap -Path $script:MapFile
        { Resolve-Author -Map $map -StorageUser 'Хтось Новий' } | Should -Throw '*AUTHORS*'
    }
}

Describe 'Get-UnknownAuthors' {
    It 'повертає лише тих, кого немає в мапі, без повторів' {
        $map = Read-AuthorMap -Path $script:MapFile
        Get-UnknownAuthors -Map $map -StorageUsers @(
            'Володимир Сидоренко', 'Хтось Новий', 'Хтось Новий') |
            Should -Be @('Хтось Новий')
    }

    It 'повертає порожній масив, а не $null, коли всі автори відомі' {
        # Set-StrictMode тут відтворює умову виклику з боку Task 5 (storage-sync.ps1),
        # який працює під Set-StrictMode -Version Latest: під ним $null.Count кидає
        # виняток, тоді як без strict mode PowerShell тихо повертає 0. Тест ловить
        # регресію, якщо унарну кому перед @(...) у реалізації прибрати.
        Set-StrictMode -Version Latest
        $map = Read-AuthorMap -Path $script:MapFile
        $unknown = Get-UnknownAuthors -Map $map -StorageUsers @('Володимир Сидоренко')
        { $unknown.Count } | Should -Not -Throw
        $unknown.Count | Should -Be 0
    }
}
