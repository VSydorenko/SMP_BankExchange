#Requires -Version 7
Set-StrictMode -Version Latest

# Без -Force: якщо V8.psm1 уже завантажено в глобальній області (саме так робить
# storage-sync.ps1 — імпортує V8, тоді StorageReport), вкладений Import-Module тут
# не повинен перезавантажувати його. З -Force вкладений виклик вивантажує наявний
# глобальний екземпляр V8 і підвантажує його заново в приватну область StorageReport,
# і виклики на кшталт New-ExtensionInfobase перестають бути видимі з глобальної
# області — саме так storage-sync.ps1 і падав. Перевірено регресійним тестом
# tools/tests/ModuleImportOrder.Tests.ps1.
Import-Module "$PSScriptRoot/V8.psm1"

$script:LabelMap = @{
    'Версия:'              = 'Version'
    'Пользователь:'        = 'User'
    'Дата создания:'       = 'Date'
    'Время создания:'      = 'Time'
    'Версия конфигурации:' = 'ConfigVersion'
    'Комментарий:'         = 'Comment'
    'Метка:'               = 'Label'
    'Комментарий метки:'   = 'LabelComment'
}

# Три розділи, якими платформа доповнює запис версії, коли звіт побудований зі списком
# змінених об'єктів: за кожним заголовком іде ЗМІННА кількість комірок-імен об'єктів —
# не одна комірка-значення, як у $script:LabelMap, тому окрема мапа й окремий стан
# розбору ($pendingList у Read-StorageReport).
$script:ListLabelMap = @{
    'Добавлены:' = 'Added'
    'Изменены:'  = 'Modified'
    'Удалены:'   = 'Deleted'
}

# Преамбула звіту цілком, до першої версії: коли й о котрій годині побудований сам звіт
# (не версія). Значення свідомо не зберігається — це метадані запуску
# /ConfigurationRepositoryReport, а не факт з історії версій сховища.
$script:ReportHeaderLabels = @('Дата отчета:', 'Время отчета:')

function ConvertFrom-MxlText {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)

    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $start = 0
    $limit = [Math]::Min($bytes.Length - 2, 64)
    for ($i = 0; $i -lt $limit; $i++) {
        if ($bytes[$i] -eq 0xEF -and $bytes[$i + 1] -eq 0xBB -and $bytes[$i + 2] -eq 0xBF) {
            $start = $i + 3
            break
        }
    }
    [System.Text.Encoding]::UTF8.GetString($bytes, $start, $bytes.Length - $start) -split "`r?`n"
}

function Get-MxlStringCells {
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyCollection()][AllowEmptyString()][string[]]$Lines)

    $cells = [System.Collections.Generic.List[string]]::new()
    $buffer = $null

    foreach ($line in $Lines) {
        if ($null -ne $buffer) {
            $buffer += "`n" + $line
        }
        elseif ($line.StartsWith('{"#","')) {
            $buffer = $line.Substring(6)
        }
        else {
            continue
        }

        # Комірка закрита, коли рядок завершується лапкою й фігурною дужкою.
        if ($buffer -match '"\}[,\d]*$') {
            $value = $buffer -replace '\}[,\d]*$', ''
            $value = $value.TrimEnd()
            if ($value.EndsWith('"')) { $value = $value.Substring(0, $value.Length - 1) }
            $cells.Add($value.Replace('""', '"'))
            $buffer = $null
        }
    }

    if ($null -ne $buffer) {
        # Комірку відкрив рядок {"#","..., але жоден наступний рядок так і не закрив її
        # очікуваним патерном "}. Раніше залишок мовчки губився в кінці файлу — цей же клас
        # утрати спершу підозрювався причиною обрізаних коментарів у версіях 31/42, але
        # виявився ні до чого не причетним: справжня причина — платформа сама трактує "//"
        # у тексті коментаря як межу рядкового коментаря в /ConfigurationRepositoryReport
        # без -IncludeCommentLinesWithDoubleSlash (див. Get-StorageVersions і
        # docs/architecture/storage-and-git.md, розділ "Обрізання коментарів на //"). Сам
        # дефект незакритої комірки лишався непокритим незалежно від цього — тепер це
        # виняток з початком уже накопиченого тексту комірки, а не тихе зникнення.
        $preview = $buffer
        if ($preview.Length -gt 200) { $preview = $preview.Substring(0, 200) + '…' }
        throw "MXL-звіт обірвався всередині незакритої комірки: '$preview'"
    }

    , $cells.ToArray()
}

function Read-StorageReport {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)

    $cells = Get-MxlStringCells -Lines (ConvertFrom-MxlText -Path $Path)
    $result = [System.Collections.Generic.List[object]]::new()
    $current = $null
    $pending = $null
    $pendingList = $null
    $skipHeaderValue = $false
    # Перед "Дата отчета:" MXL несе титульний рядок друкованої форми — оформлення
    # табличного документа (стилі, GUID області друку) з вкраплення тексту заголовка
    # звіту й шляху до сховища, усе як ОДНА комірка, без пари "мітка:"/"значення".
    # Форма цього рядка залежить від верстки друкованої форми, тому замість того щоб
    # розпізнавати його вміст, розбір просто ігнорує будь-які комірки до першого
    # відомого заголовка — і перестає це робити одразу, як тільки такий заголовок
    # зустрівся, щоб не проковтнути мовчки щось справді неочікуване всередині звіту.
    $sawKnownLabel = $false

    foreach ($cell in $cells) {
        if ($skipHeaderValue) {
            # Значення "Дата отчета:"/"Время отчета:" з попередньої ітерації — свідомо
            # відкидається, див. коментар біля $script:ReportHeaderLabels.
            $skipHeaderValue = $false
            continue
        }

        if ($script:ReportHeaderLabels -contains $cell) {
            $sawKnownLabel = $true
            $skipHeaderValue = $true
            continue
        }

        if ($script:LabelMap.ContainsKey($cell)) {
            $sawKnownLabel = $true
            if ($cell -eq 'Версия:') {
                if ($current) { $result.Add($current) }
                $current = [ordered]@{
                    Version = 0; User = ''; Date = ''; Time = ''
                    ConfigVersion = ''; Comment = ''; Label = ''; LabelComment = ''
                    Added = [System.Collections.Generic.List[string]]::new()
                    Modified = [System.Collections.Generic.List[string]]::new()
                    Deleted = [System.Collections.Generic.List[string]]::new()
                }
            }
            $pending = $script:LabelMap[$cell]
            $pendingList = $null
            continue
        }

        if ($script:ListLabelMap.ContainsKey($cell)) {
            if (-not $current) {
                throw "Розділ '$cell' зустрівся до першої версії у звіті сховища — неочікувана форма звіту."
            }
            $pendingList = $script:ListLabelMap[$cell]
            $pending = $null
            continue
        }

        if ($pending -and $current) {
            if ($pending -eq 'Version') {
                $current['Version'] = [int]$cell
            } else {
                $current[$pending] = $cell
            }
            $pending = $null
            continue
        }

        if ($pendingList -and $current) {
            $current[$pendingList].Add($cell)
            continue
        }

        if (-not $sawKnownLabel) {
            # Титульний рядок звіту (див. коментар біля $sawKnownLabel вище) — до першого
            # відомого заголовка все ще нічого не втрачено, бо жодна версія ще не почалась.
            continue
        }

        # Жоден із відомих заголовків і жодне активне поле не претендує на цю комірку.
        # Раніше вона мовчки губилась тут — цей же клас утрати спершу підозрювався причиною
        # обрізаних коментарів у версіях 31/42, але це не підтвердилось: втрата виявилась
        # вище, всередині самого /ConfigurationRepositoryReport (він трактує "//" у
        # коментарі як межу рядкового коментаря без -IncludeCommentLinesWithDoubleSlash —
        # діагностика й спосіб уникнути в Get-StorageVersions і
        # docs/architecture/storage-and-git.md, розділ "Обрізання коментарів на //"). Але
        # сам дефект — тихе зникнення комірки в інструменті, що пише незамінну історію в
        # git, — лишається дефектом незалежно від цього конкретного випадку: тепер
        # невпізнана форма зупиняє розбір, а не мовчки минає його.
        throw "Неочікувана комірка звіту сховища (немає активного поля для неї): '$cell'"
    }
    if ($current) { $result.Add($current) }

    , @($result |
        ForEach-Object {
            $stamp = [datetime]::MinValue
            if ($_.Date -and $_.Time) {
                # Платформа не доповнює нулем жодну односимвольну складову дати чи часу
                # ("Время создания:" може бути "1:27:39", "Дата создания:" — теоретично так само
                # "3.5.2022"). Подвоєні специфікатори (dd/MM/HH/mm/ss) вимагають рівно дві цифри
                # й падають на першій-ліпшій односимвольній складовій — саме так падало на годині.
                # Одинарні специфікатори (d/M/H/m/s) приймають і одну, і дві цифри, лишаючись при
                # цьому строго прив'язаними до позиції в форматному рядку: "d" завжди читається
                # як день, "M" — як місяць, незалежно від кількості цифр у значенні, тому порядок
                # "день-місяць" не стає неоднозначним.
                $stamp = [datetime]::ParseExact(
                    "$($_.Date) $($_.Time)", 'd.M.yyyy H:m:s',
                    [cultureinfo]::InvariantCulture)
            }
            [pscustomobject]@{
                Version       = $_.Version
                User          = $_.User
                Date          = $_.Date
                Time          = $_.Time
                ConfigVersion = $_.ConfigVersion
                Comment       = $_.Comment
                Label         = $_.Label
                LabelComment  = $_.LabelComment
                Added         = @($_.Added)
                Modified      = @($_.Modified)
                Deleted       = @($_.Deleted)
                Timestamp     = $stamp
            }
        } |
        Sort-Object Version)
}

function Get-StorageVersions {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$IbSwitch,
        [Parameter(Mandatory)][string]$StoragePath,
        [Parameter(Mandatory)][string]$ExtensionName,
        [Parameter(Mandatory)][string]$StorageUser,
        [Parameter(Mandatory)][string]$WorkDir
    )

    New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null
    $reportPath = Join-Path $WorkDir 'storage-report.mxl'
    if (Test-Path -LiteralPath $reportPath) { Remove-Item -LiteralPath $reportPath -Force }

    # -IncludeCommentLinesWithDoubleSlash: без цього ключа /ConfigurationRepositoryReport
    # сам трактує "//" у тексті коментаря як межу рядкового коментаря — усе від "//" до
    # кінця рядка зникає з MXL ще до того, як звіт узагалі потрапляє в цей інструмент (не
    # дефект парсера тут — підтверджено побайтово на "живих" звітах, докладно в
    # docs/architecture/storage-and-git.md, розділ "Обрізання коментарів на //"). Ключ
    # знайдено не експериментом з прапорцями, а читанням джерела oscript-library/gitsync
    # (через залежність oscript-library/v8storage,
    # МенеджерХранилищаКонфигурации.os:596) — той самий інструмент, який відтворив повний
    # текст коментаря версії 20 BankExchange_SMB у коміті 0ccd83c ще до появи цього
    # тулсету. Платформа підтримує ключ з 8.3.17 (gitsync вмикає його умовно за версією);
    # тут це не потрібно — Get-V8Path працює лише з гілкою 8.3.27.x.
    $result = Invoke-V8Designer -IbSwitch $IbSwitch -Arguments @(
        '/ConfigurationRepositoryF "{0}"' -f $StoragePath
        '/ConfigurationRepositoryN "{0}"' -f $StorageUser
        '/ConfigurationRepositoryP ""'
        '/ConfigurationRepositoryReport "{0}" -NBegin 1 -Extension {1} -IncludeCommentLinesWithDoubleSlash' -f $reportPath, $ExtensionName
    )

    if ($result.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $reportPath)) {
        throw "Не вдалося побудувати звіт сховища $StoragePath : $($result.Output)"
    }

    Read-StorageReport -Path $reportPath
}

Export-ModuleMember -Function ConvertFrom-MxlText, Get-MxlStringCells, Read-StorageReport, Get-StorageVersions
