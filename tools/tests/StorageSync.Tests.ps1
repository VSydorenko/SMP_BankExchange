#Requires -Version 7
# storage-sync.ps1 — сам скрипт, не модуль, тож тестуємо, запускаючи його файл. Він
# обчислює $repoRoot від власного $PSScriptRoot, тому запобіжник чистоти робочої копії
# (git status -- $Product) неможливо перевірити на модульних функціях окремо — потрібен
# справжній git-репозиторій навколо файлу продукту. Щоб не чіпати справжній репозиторій
# цієї сесії, копіюємо скрипт і всі lib/*.psm1 у повністю ізольований фейковий репозиторій
# під $TestDrive і ініціалізуємо там окремий git.
#
# Запускаємо скрипт саме окремим процесом pwsh (а не викликом "&" у поточній сесії):
# storage-sync.ps1 імпортує lib/*.psm1 під тими самими іменами модулів (V8,
# StorageReport, Authors, SyncState), що вже завантажені реальними копіями з інших
# *.Tests.ps1 у тому самому прогоні Run-Tests.ps1. Виклик "&" у процесі додав би другий
# екземпляр кожного модуля під тим самим іменем і ламав би InModuleScope в V8.Tests.ps1
# помилкою "Multiple script or manifest modules named 'V8' are currently loaded" —
# перевірено емпірично. Окремий процес повністю ізолює простір модулів.
#
# Робоча тека скрипта — <fake-repo>/build/sync/<Product>, а не <product>/build/sync:
# в обох сценаріях нижче скрипт падає до створення цієї теки (запобіжник чистоти або
# перевірка storagePath), тому сам факт релокації workDir не міняє жодного з очікувань
# нижче. Але саме тому кожен It додатково перевіряє, що ця тека не з'явилась: без цього
# тести проходили б, навіть якби порядок перевірок у скрипті зламали так, що workDir
# створюється до запобіжника — оскільки негативна перевірка "*не чиста*" сама по собі
# такого регресу не ловить.

Describe 'storage-sync.ps1 -Apply: запобіжник чистоти робочої копії' {
    BeforeAll {
        $script:FakeRepo = Join-Path $TestDrive 'fake-repo'
        $toolsDir = Join-Path $script:FakeRepo 'tools'
        $libDir   = Join-Path $toolsDir 'lib'
        New-Item -ItemType Directory -Path $libDir -Force | Out-Null

        $realTools = Resolve-Path "$PSScriptRoot/.."
        Copy-Item -LiteralPath (Join-Path $realTools 'storage-sync.ps1') -Destination (Join-Path $toolsDir 'storage-sync.ps1')
        Copy-Item -Path (Join-Path $realTools 'lib/*.psm1') -Destination $libDir

        Set-Content -LiteralPath (Join-Path $script:FakeRepo 'AUTHORS') -Encoding UTF8 -Value @(
            'gitbot=Test Bot <test@example.invalid>'
        )

        git -C $script:FakeRepo init -q
        git -C $script:FakeRepo config user.email 'test@example.invalid'
        git -C $script:FakeRepo config user.name 'Test Bot'
        git -C $script:FakeRepo config commit.gpgsign false

        $script:ScriptPath = Join-Path $toolsDir 'storage-sync.ps1'

        # Функція визначена всередині BeforeAll (а не прямо в тілі Describe), бо Pester
        # виконує тіло Describe лише на фазі discovery — оголошення поза BeforeAll/It не
        # переживає перехід до фази run і в It було б недоступне.
        function script:New-FakeProduct {
            param([Parameter(Mandatory)][string]$Name)

            $productPath = Join-Path $script:FakeRepo $Name
            New-Item -ItemType Directory -Path $productPath -Force | Out-Null
            [ordered]@{
                # Навмисно неіснуючий шлях: після запобіжника скрипт впаде на наступній
                # перевірці ("Каталог сховища не знайдено") — саме цього ми й хочемо для
                # сценарію "чиста копія", щоб довести, що впала не перевірка чистоти.
                storagePath       = (Join-Path $TestDrive 'no-such-storage')
                extensionName     = 'FAKE_EXT'
                lastSyncedVersion = 0
                sourcePath        = 'cfe/src'
            } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $productPath 'storage.json') -Encoding UTF8

            $productPath
        }

        function script:Invoke-StorageSync {
            param([Parameter(Mandatory)][string]$Name)

            $output = & pwsh -NoProfile -File $script:ScriptPath -Product $Name -Apply 2>&1 |
                Out-String
            [pscustomobject]@{
                ExitCode = $LASTEXITCODE
                Output   = $output
            }
        }
    }

    It 'на чистій копії не спрацьовує — скрипт падає далі, з іншої причини' {
        $name = 'Product_Clean'
        New-FakeProduct -Name $name | Out-Null
        git -C $script:FakeRepo add -A
        git -C $script:FakeRepo commit -q -m 'фікстура: чистий продукт'

        $result = Invoke-StorageSync -Name $name

        # Запобіжник не мав спрацювати на щойно закомічених джерелах без жодних слідів.
        # Скрипт все одно впаде (ненульовий код) — на "Каталог сховища не знайдено"
        # (storagePath вигаданий) — і це очікувано: перевіряємо саме запобіжник, а не
        # кінцевий результат прогону.
        $result.ExitCode | Should -Not -Be 0
        $result.Output   | Should -Not -BeLike '*не чиста*'

        # Скрипт падає на перевірці storagePath раніше, ніж встигає створити нову робочу
        # теку в корені репозиторію — тож її не мало лишитись.
        Join-Path $script:FakeRepo 'build/sync' $name | Should -Not -Exist
    }

    It 'v8project.local.yaml перевизначає storagePath зі storage.json (I5)' {
        # Обидва шляхи навмисно вигадані (не існують) — скрипт однаково впаде на
        # "Каталог сховища не знайдено", але яка саме адреса потрапить у повідомлення,
        # прямо доводить, який storagePath скрипт насправді використав: зі storage.json
        # (не мало б перевизначитись) чи з v8project.local.yaml (мало б).
        $name = 'Product_LocalOverride'
        $productPath = New-FakeProduct -Name $name
        $overridePath = Join-Path $TestDrive 'local-override-storage'
        Set-Content -LiteralPath (Join-Path $productPath 'v8project.local.yaml') -Encoding UTF8 -Value @(
            'infobase:'
            "  connection: 'File=""C:\bases\demo"";'"
            "storagePath: '$overridePath'"
        )
        git -C $script:FakeRepo add -A
        git -C $script:FakeRepo commit -q -m 'фікстура: продукт із локальним перевизначенням storagePath'

        $result = Invoke-StorageSync -Name $name

        $result.ExitCode | Should -Not -Be 0
        $result.Output   | Should -BeLike "*Каталог сховища не знайдено: $overridePath*"
        # storage.json несе окремий, теж вигаданий шлях — повідомлення не повинно
        # згадувати саме його, інакше перевизначення не спрацювало.
        $result.Output   | Should -Not -BeLike '*no-such-storage*'
    }

    It 'на брудній копії кидає саме повідомлення запобіжника' {
        $name = 'Product_Dirty'
        $productPath = New-FakeProduct -Name $name
        git -C $script:FakeRepo add -A
        git -C $script:FakeRepo commit -q -m 'фікстура: продукт перед забрудненням'

        # Незакомічений слід під теці продукту — так само, як лишає перерваний прогін -Apply
        # (видалення $sourceDir без наступного коміту, або коміт, що не завершився).
        Set-Content -LiteralPath (Join-Path $productPath 'stray.txt') -Value 'залишок перерваного прогону'

        $result = Invoke-StorageSync -Name $name

        $result.ExitCode | Should -Not -Be 0
        $result.Output   | Should -BeLike '*не чиста*'

        # Запобіжник спрацював до створення робочої теки в корені репозиторію — її не
        # мало з'явитись.
        Join-Path $script:FakeRepo 'build/sync' $name | Should -Not -Exist
    }
}

Describe 'storage-sync.ps1 -Apply: M4 — "git add" перевіряється так само, як "git commit"' {
    # Цикл по версіях (storage-sync.ps1:107+) вимагає реальної платформи й реального
    # сховища задовго до "git add -A -- $Product" — тому цей рядок не можна дійти
    # наскрізним прогоном скрипту в ізольованій фікстурі (як два тести вище). Замість
    # цього тест доводить саму передумову фіксу: що провалений "git add" насправді
    # виставляє ненульовий $LASTEXITCODE — той самий сигнал, який storage-sync.ps1:189
    # тепер перевіряє одразу після виклику (дзеркалячи вже наявну перевірку "git commit"
    # трьома рядками нижче). До фіксу цей код ігнорувався: --allow-empty на "git commit"
    # означає, що провалений "git add" усе одно завершується успішним порожнім комітом,
    # який просуває lastSyncedVersion, лишаючи джерела цієї версії поза git.
    It '"git add -A" завершується ненульовим кодом, коли git реально не може виконати команду' {
        $repo = Join-Path $TestDrive 'git-add-fail-repo'
        New-Item -ItemType Directory -Path $repo -Force | Out-Null
        git -C $repo init -q
        git -C $repo config user.email 'test@example.invalid'
        git -C $repo config user.name 'Test Bot'

        New-Item -ItemType Directory -Path (Join-Path $repo 'Product') -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $repo 'Product/file.txt') -Value 'початковий вміст'
        git -C $repo add -A | Out-Null
        git -C $repo commit -q -m 'початковий коміт'

        Set-Content -LiteralPath (Join-Path $repo 'Product/file.txt') -Value 'зміна, яку не вдасться заіндексувати'

        # index.lock, що лишився від "завислого" git-процесу, — найнадійніший спосіб
        # відтворити реальний провал "git add" без залежності від платформи чи сховища.
        $lockFile = Join-Path $repo '.git/index.lock'
        Set-Content -LiteralPath $lockFile -Value ''
        try {
            git -C $repo add -A -- Product 2>&1 | Out-Null
            $LASTEXITCODE | Should -Not -Be 0
        }
        finally {
            Remove-Item -LiteralPath $lockFile -Force -ErrorAction SilentlyContinue
        }
    }
}
