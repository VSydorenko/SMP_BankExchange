#Requires -Version 7
<#
.SYNOPSIS
    Шим хука SessionStart для репозиторію під v8storagekit (спека §7). Закомічений у
    репозиторії-споживачі як .claude/hooks/session-start.ps1; його кладе скіл onboarding.
.DESCRIPTION
    Логіки тут немає: знайти плагін у реєстрі Claude Code, викликати kit.ps1 session-check у
    поточній теці й надрукувати контекст для сесії. Плагіна немає — мовчки, код 0. Нічого не
    змінює: рішення — людині, дія — скіл v8storagekit:sync.
    Оновлення: kit check порівнює цей файл із templates/hooks/session-start.ps1 плагіна.

    Гарантія «плагіна немає — нічого не друкує, код 0 завжди» — СТРУКТУРНА (рев'ю B4 Task 4,
    Critical C1), не перелік місць, де щось може впасти: Get-KitPluginRoot ловить власні
    винятки (перший рубіж — будь-яка форма реєстру, що не розбирається, читається як «плагіна
    немає»), а решта тіла скрипта — під зовнішнім try/catch/finally{exit 0} (другий рубіж).
    П'ять форм побитого installed_plugins.json (порожній файл, [], null, {"plugins":null},
    запис без installPath) під StrictMode кидали PropertyNotFoundException до цього фіксу —
    перевірено запуском (C1).
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# Кодування — best-effort і ізольовано від решти: без прикріпленої консолі сеттер на Windows
# може кинути "The handle is invalid" (рев'ю C1, непідтверджена гіпотеза — але провал тут не
# сміє скасувати друк реального контексту сесії нижче, тож ізольований власним try/catch).
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

function Get-KitPluginRoot {
    # Перший рубіж гарантії C1: БУДЬ-яка форма реєстру, з якої не вдається однозначно
    # дістати installPath — це те саме, що «плагіна немає» ($null), а не виняток нагору.
    try {
        $registry = if ($env:V8KIT_PLUGINS_REGISTRY) { $env:V8KIT_PLUGINS_REGISTRY } else { Join-Path $HOME '.claude/plugins/installed_plugins.json' }
        if (-not (Test-Path -LiteralPath $registry -PathType Leaf)) { return $null }
        $json = Get-Content -LiteralPath $registry -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $json -or -not ($json.PSObject.Properties.Name -contains 'plugins') -or -not $json.plugins) { return $null }
        # Ключі реєстру — '<плагін>@<маркетплейс>'; ім'я плагіна — до '@'.
        $entry = $json.plugins.PSObject.Properties | Where-Object { ($_.Name -split '@', 2)[0] -eq 'v8storagekit' } | Select-Object -First 1
        if (-not $entry) { return $null }
        $install = @($entry.Value) | Select-Object -First 1
        if (-not $install -or -not ($install.PSObject.Properties.Name -contains 'installPath')) { return $null }
        $root = [string]$install.installPath
        if (-not (Test-Path -LiteralPath (Join-Path $root 'tools/kit.ps1') -PathType Leaf)) { return $null }
        $root
    } catch {
        $null
    }
}

# Другий рубіж гарантії C1: усе між сюди й друком JSON — під одним try/catch/finally{exit 0},
# а не переліком того, що там може впасти. Get-KitPluginRoot уже ловить власні винятки —
# цей рубіж ловить решту (наприклад ConvertTo-Json чи щось, чого сьогодні тут ще немає).
try {
    $plugin = Get-KitPluginRoot
    if ($plugin) {
        $context = ''
        try {
            $intro = ''
            $skill = Join-Path $plugin 'skills/using-v8storagekit/SKILL.md'
            if (Test-Path -LiteralPath $skill -PathType Leaf) {
                $intro = Get-Content -LiteralPath $skill -Raw -Encoding UTF8
                $intro = [regex]::Replace($intro, '\A---\r?\n.*?\r?\n---\r?\n', '', [System.Text.RegularExpressions.RegexOptions]::Singleline)
                $intro = $intro.Replace('<корінь плагіна>', $plugin)
            }

            $cwd = (Get-Location).Path
            $status = ''
            if (-not (Test-Path -LiteralPath (Join-Path $cwd 'v8storagekit.yaml') -PathType Leaf)) {
                $status = "У теці $cwd немає v8storagekit.yaml: репозиторій не підключено до kit (скіл v8storagekit:onboarding) або сесія відкрита не в корені репозиторію."
            } else {
                # Стеля часу — обов'язкова: цей код виконується на старті КОЖНОЇ сесії, а session-check обходить
                # data/objects (часто SMB) і викликає повний check. Перевищення показуємо рядком, не мовчанням:
                # мовчання читалось би як «нових версій немає» — та сама логіка, що для непередбаченого коду.
                # Стеля — через змінну оточення, а не через накладку: шим за конструкцією не читає YAML
                # (жодних модулів kit, жодного парсера) — інакше він перестав би бути шимом.
                $timeoutSec = 15
                # Мінімальний фікс (рев'ю Minor): TryParse замість [int] — '99999999999' проходить
                # ^\d+$, але [int] на ньому кидає OverflowException; діапазон 1…600 — та сама стеля,
                # що в tools/tests/Run-Tests.ps1 (600000 мс).
                $parsedTimeout = 0
                if ($env:V8KIT_SESSION_CHECK_TIMEOUT -and [int]::TryParse($env:V8KIT_SESSION_CHECK_TIMEOUT, [ref]$parsedTimeout) -and $parsedTimeout -ge 1 -and $parsedTimeout -le 600) {
                    $timeoutSec = $parsedTimeout
                }
                $outFile = $null
                $errFile = $null
                try {
                    # Обидва тимчасові файли — усередині try (рев'ю Minor): якщо другий
                    # GetTempFileName() кине, finally нижче все одно прибере вже створений
                    # перший — без цього перший лишався б сиротою на диску.
                    $outFile = [System.IO.Path]::GetTempFileName()
                    $errFile = [System.IO.Path]::GetTempFileName()
                    # Вивід — у ФАЙЛИ, не в пайп: пайп без асинхронного читання дає дедлок на великому виводі
                    # (знахідка B2 в Invoke-KitGitProcess). Список аргументів закритий: -Apply шим не передає
                    # ніколи — session-check нічого не змінює, і передавати його нема чого.
                    $proc = Start-Process -FilePath 'pwsh' -PassThru -NoNewWindow -RedirectStandardOutput $outFile -RedirectStandardError $errFile `
                        -ArgumentList @('-NoProfile', '-File', (Join-Path $plugin 'tools/kit.ps1'), 'session-check', '-RepoRoot', $cwd)
                    if ($proc.WaitForExit($timeoutSec * 1000)) {
                        $raw = (((Get-Content -LiteralPath $outFile -Raw -Encoding UTF8) + (Get-Content -LiteralPath $errFile -Raw -Encoding UTF8)) | Out-String).Trim()
                        # Коди за змістом (спека §5): 0 — тиша, 3 — є сигнал — обидва друкуються як є;
                        # БУДЬ-ЯКИЙ інший код (1 — перевірка не відпрацювала, або взагалі непередбачений
                        # — процес убито антивірусом/OOM, pwsh не стартував) — мовчати не можна (рев'ю I5:
                        # раніше розрізнялось лише "1" проти "решта", і "решта" з порожнім $raw читалась
                        # би як «нових версій немає» — та сама заборонена тиша).
                        $status = if ($proc.ExitCode -eq 0 -or $proc.ExitCode -eq 3) {
                            $raw
                        } else {
                            "УВАГА: kit session-check завершився неочікуваним кодом $($proc.ExitCode) (очікувалось 0 або 3) — стан сховищ НЕВІДОМИЙ, не «без змін». Зупинка:`n$raw"
                        }
                    } else {
                        # Убивати процес дозволено рівно тому, що session-check нічого не мутує (§5).
                        try { $proc.Kill($true) } catch { }
                        $status = "УВАГА: kit session-check не вклався в $timeoutSec с — стан сховищ НЕВІДОМИЙ, не «без змін». Найчастіша причина — повільний доступ до сховища (SMB); перевірити вручну: kit.ps1 session-check -RepoRoot ."
                        # Те, що kit устиг надрукувати, не пропадає: знахідки check виходять раніше за сигнали джерел.
                        # Позначка «частково» обов'язкова — без неї обрізаний вивід читався б як повний, тобто як
                        # «інших джерел не згадано, отже з ними все гаразд».
                        $partial = ''
                        try { $partial = ((Get-Content -LiteralPath $outFile -Raw -Encoding UTF8) | Out-String).Trim() } catch { }
                        if ($partial) { $status = "$status`n`nЧастково (kit устиг надрукувати до зупинки; повнота НЕ гарантована):`n$partial" }
                    }
                } finally {
                    if ($outFile) { Remove-Item -LiteralPath $outFile -Force -ErrorAction SilentlyContinue }
                    if ($errFile) { Remove-Item -LiteralPath $errFile -Force -ErrorAction SilentlyContinue }
                }
            }

            $context = "<v8storagekit>`n$intro`n`n## Стан сховищ (kit session-check)`n`n$status`n</v8storagekit>"
        } catch {
            $context = "<v8storagekit>`nХук v8storagekit не зміг зібрати стан: $($_.Exception.Message)`n</v8storagekit>"
        }

        [ordered]@{
            hookSpecificOutput = [ordered]@{ hookEventName = 'SessionStart'; additionalContext = $context }
        } | ConvertTo-Json -Depth 4 -Compress
    }
} catch {
    # Останній рубіж гарантії C1: будь-який неврахований збій (навіть тут) не сміє друкувати
    # нічого й не сміє лишити код виходу відмінним від 0 — «плагіна немає» і «щось незрозуміле
    # впало ще до того, як зібрався контекст» з погляду виклику виглядають однаково: тиша.
} finally {
    exit 0
}
