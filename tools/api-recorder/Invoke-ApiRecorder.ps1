#Requires -Version 7.5
<#
.SYNOPSIS
  Рекордер відповідей API ПриватБанку («Автоклієнт»), monobank юросіб (corp-api), monobank ФОП (персональне API) і ПУМБ (Vega/VegaNet).
.DESCRIPTION
  Лише читання в банку: методи й шляхи (метод + хост + порт + шлях) — з білого списку (ApiRecorder.Lib.ps1); POST лише там, де
  банк вимагає його для читання (ПУМБ: форма на токен-ендпоінт, searcher, period-transactions). ПУМБ — лише за явним -Bank pumb
  (у 'all' не входить) і лише з ключем LoginApproved = $true у конфігурації (його виставляє власник). Відповіді зберігаються як
  упорядкована послідовність обмінів (FORMAT.md): тіло — байтами, заголовка запиту з токеном у записі немає.
  Після прогону рекордер сам шукає значення кожного токена в кожному записаному файлі в усіх кодуваннях.
  Режими: звичайний; -CheckRun (перевірка наявного запису на токени); -DryRun (план запитів без мережі); -SelfTest (перевірка самого пошуку секретів, без мережі).
  Запускає власник. Див. README.md.
#>
[CmdletBinding()]
param(
    # Справжня конфігурація — лише в temp основного дерева (гітігнорована), поза git.
    [string]$Config = 'R:/github/SMP_BankExchange/temp/api-recorder/config.psd1',
    [ValidateSet('all', 'privat', 'monoCorp', 'monoFop', 'pumb')][string[]]$Bank = 'all',
    # Мітка прогону = назва теки запису. Другий прогін — та сама команда з новою міткою.
    [string]$RunLabel = (Get-Date -Format 'yyyyMMdd-HHmmss'),
    [string]$OutRoot = 'R:/github/SMP_BankExchange/temp/api-recordings',
    # Файли звірки із сумами — ПОЗА текою записів (її читає агент), поруч із конфігурацією.
    [string]$OwnerRoot = 'R:/github/SMP_BankExchange/temp/api-recorder/owner-only',
    [switch]$DryRun,
    [switch]$SelfTest,
    # Перевірити НАЯВНУ теку запису (-Bank, -RunLabel) і відповідну теку owner-only на токени з конфігурації. Без мережі.
    [switch]$CheckRun,
    # Файл, у який власник перенаправив stderr прогону (2> файл): самоперевірка шукає секрети й у ньому (як і в консольному журналі console.log теки запису).
    [string]$StderrLog = '',
    [string]$SelfTestDir = ''
)

$ErrorActionPreference = 'Stop'
$OutRoot = [System.IO.Path]::GetFullPath($OutRoot)
$OwnerRoot = [System.IO.Path]::GetFullPath($OwnerRoot)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
. (Join-Path $PSScriptRoot 'ApiRecorder.Lib.ps1')

# Вигадані очевидно фальшиві значення для сценаріїв «свідомі помилки». Не похідні від справжніх.
$script:FakeToken = 'INVALID-TOKEN-FOR-RECORDER-0000000000000000'
$script:FakeId = 'INVALID-ID-00000'
$script:FakeIban = 'UA000000000000000000000000000'
$script:FakeMonoAccountId = 'invalidAccountId0000'
$script:UserAgent = "SMP-ApiRecorder/$script:RecorderVersion"
$script:Http = $null
$script:FopPageMax = 500   # максимум операцій на сторінку виписки ФОП (документація)

# =============================================================================================
# Контекст, зведення, пауза
# =============================================================================================
function New-Ctx {
    param([string]$BankKey, [string]$HostName, [double]$MinIntervalSec, $Rec, $Secrets, [bool]$Dry)
    [pscustomobject]@{
        BankKey = $BankKey; HostName = $HostName; MinIntervalSec = $MinIntervalSec; Rec = $Rec; Secrets = $Secrets; Dry = $Dry
        BaseHeaders = @{}; ContentType = ''; NextGap = 0.0; LastEnd = $null; PlannedSeconds = 0.0
        Stats = [ordered]@{}; Cur = $null; Owner = [System.Collections.Generic.List[string]]::new()
        Abort = ''; Failed = $false; Requests = 0
        Captured = [System.Collections.Generic.List[object]]::new()
    }
}

function Write-Owner {
    param($Ctx, [string]$Text)
    Write-Host $Text
    $Ctx.Owner.Add($Text)
}

function Start-ScenarioStats {
    param($Ctx, [string]$Name)
    $s = [pscustomobject]@{
        Name = $Name; Exchanges = 0; Pages = 0; Ops = 0
        Counts = [ordered]@{}; IdTotal = @{}; IdSet = @{}; Sums = [ordered]@{}; Notes = [System.Collections.Generic.List[string]]::new()
    }
    $Ctx.Stats[$Name] = $s
    $Ctx.Cur = $s
    $Ctx.Captured = [System.Collections.Generic.List[object]]::new()   # сторінки виписки поточного сценарію в пам'яті (для вибору операції пар меж)
    Write-Host ''
    Write-Host "=== $Name ==="
}

function Add-Count {
    param($Ctx, [string]$Group, [string]$Key, [int]$N = 1)
    $s = $Ctx.Cur
    if ([string]::IsNullOrEmpty($Key)) { $Key = '(порожньо)' }
    if (-not $s.Counts.Contains($Group)) { $s.Counts[$Group] = [ordered]@{} }
    if (-not $s.Counts[$Group].Contains($Key)) { $s.Counts[$Group][$Key] = 0 }
    $s.Counts[$Group][$Key] += $N
}
function Add-Note { param($Ctx, [string]$Text) $Ctx.Cur.Notes.Add($Text); Write-Host "  · $Text" }
function Add-IdValue {
    param($Ctx, [string]$Kind, $Value)
    if ($null -eq $Value -or [string]$Value -eq '') { return }
    $s = $Ctx.Cur
    if (-not $s.IdSet.ContainsKey($Kind)) { $s.IdSet[$Kind] = [System.Collections.Generic.HashSet[string]]::new(); $s.IdTotal[$Kind] = 0 }
    $s.IdTotal[$Kind]++
    [void]$s.IdSet[$Kind].Add([string]$Value)
}
function Add-Sum {
    param($Ctx, [string]$Key, [decimal]$Value)
    $s = $Ctx.Cur
    if (-not $s.Sums.Contains($Key)) { $s.Sums[$Key] = [decimal]0 }
    $s.Sums[$Key] += $Value
}
function ConvertTo-DecimalSafe {
    param($Text)
    $d = [decimal]0
    if ([decimal]::TryParse(([string]$Text).Replace(',', '.'), [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$d)) { return $d }
    [decimal]0
}

function Invoke-Scenario {
    param($Ctx, [string]$Name, [scriptblock]$Block)
    if ($Ctx.Abort) { Write-Host "[пропуск] $Name — $($Ctx.Abort)"; return }
    Start-ScenarioStats $Ctx $Name
    try { & $Block }
    catch {
        $m = Remove-SecretValues ([string]$_.Exception.Message) $Ctx.Secrets
        if ($m -like 'SCENARIO_STOP:*') { Add-Note $Ctx ('Сценарій зупинено: ' + $m.Substring(14).Trim()) }
        else { $Ctx.Failed = $true; Add-Note $Ctx "Помилка рекордера в сценарії: $m" }
    }
}

# =============================================================================================
# HTTP (тіло байтами, без автоперенаправлень; GET — три банки, POST — лише ПУМБ за білим списком)
# =============================================================================================
function Get-HttpClient {
    if ($null -eq $script:Http) {
        $h = [System.Net.Http.HttpClientHandler]::new()
        $h.AllowAutoRedirect = $false          # токен у заголовку не має піти на чужу адресу
        $h.AutomaticDecompression = [System.Net.DecompressionMethods]::All
        $script:Http = [System.Net.Http.HttpClient]::new($h)
        $script:Http.Timeout = [TimeSpan]::FromSeconds(60)
    }
    $script:Http
}

function Invoke-HttpSend {
    param([string]$Method, [string]$Uri, [hashtable]$Headers, [string]$ContentType, $Body = $null)
    $client = Get-HttpClient
    $req = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($Method), $Uri)
    foreach ($k in $Headers.Keys) { [void]$req.Headers.TryAddWithoutValidation($k, [string]$Headers[$k]) }
    if ($ContentType -or $null -ne $Body) {
        $bytes = if ($null -ne $Body) { [byte[]]$Body } else { [byte[]]@() }
        $req.Content = [System.Net.Http.ByteArrayContent]::new($bytes)
        if ($ContentType) { [void]$req.Content.Headers.TryAddWithoutValidation('Content-Type', $ContentType) }
    }
    try {
        $resp = $client.SendAsync($req).GetAwaiter().GetResult()
        $bytes = $resp.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
        $pairs = [System.Collections.Generic.List[object]]::new()
        foreach ($h in $resp.Headers) { $pairs.Add(@($h.Key, (@($h.Value) -join ','))) }
        foreach ($h in $resp.Content.Headers) { $pairs.Add(@($h.Key, (@($h.Value) -join ','))) }
        return [pscustomobject]@{ Status = [int]$resp.StatusCode; Headers = $pairs.ToArray(); Body = $bytes; Failure = $null }
    }
    catch {
        $ex = $_.Exception
        while ($ex.InnerException -and $ex -isnot [System.Threading.Tasks.TaskCanceledException]) { $ex = $ex.InnerException }
        $kind = if ($ex -is [System.Threading.Tasks.TaskCanceledException] -or $ex -is [System.OperationCanceledException]) { 'timeout' }
        elseif ($_.Exception -is [System.Net.Http.HttpRequestException] -or $_.Exception.InnerException -is [System.Net.Http.HttpRequestException]) { 'network' }
        else { 'other' }
        return [pscustomobject]@{ Status = $null; Headers = @(); Body = [byte[]]@(); Failure = [pscustomobject]@{ Kind = $kind; Text = "$($ex.GetType().Name): $($ex.Message)" } }
    }
    finally { $req.Dispose() }
}

function Invoke-HttpGet {
    param([string]$Uri, [hashtable]$Headers, [string]$ContentType)
    Invoke-HttpSend 'GET' $Uri $Headers $ContentType $null
}

function Get-HeaderValue {
    param($Pairs, [string]$Name)
    foreach ($p in $Pairs) { if (([string]$p[0]) -ieq $Name) { return [string]$p[1] } }
    $null
}

function Get-RetryWaitSeconds {
    param($Pairs)
    foreach ($n in 'x-rate-limit-retry-after-seconds', 'retry-after') {
        $v = Get-HeaderValue $Pairs $n
        $i = 0
        if ($v -and [int]::TryParse($v.Trim(), [ref]$i) -and $i -gt 0) { return [math]::Min($i, 300) }
    }
    60
}

function Wait-Gap {
    param($Ctx)
    $gap = $Ctx.NextGap
    if ($null -ne $Ctx.LastEnd -and -not $Ctx.Dry) { $gap -= ([datetime]::UtcNow - $Ctx.LastEnd).TotalSeconds }
    if ($gap -le 0) { return }
    if ($Ctx.Dry) {
        $Ctx.PlannedSeconds += $gap
        if ($gap -ge 5) { Write-Host ("  [пауза {0:N0} с]" -f $gap) }
    }
    else {
        if ($gap -ge 5) { Write-Host ("  пауза {0:N0} с" -f $gap) }
        Start-Sleep -Milliseconds ([int]($gap * 1000))
    }
}

# Єдина точка запиту. Повертає Status, Body (байти), Headers, Failure. 429: пауза за retry-after і один повтор, далі — стоп сценарію.
function Invoke-Api {
    param($Ctx, [string]$Path, [string]$Query = '', [hashtable]$Headers = $null, [string]$ContentType = $null,
        [string]$DryStub = '[]', [switch]$NoGap, [switch]$NoRetry)
    if ($null -eq $Headers) { $Headers = $Ctx.BaseHeaders }
    if (-not $ContentType) { $ContentType = $Ctx.ContentType }
    Assert-ReadOnlyRequest 'GET' $Ctx.HostName $Path
    $result = $null
    for ($attempt = 1; $attempt -le 2; $attempt++) {
        if ($NoGap -and $attempt -eq 1) { $Ctx.NextGap = 0.0 }
        Wait-Gap $Ctx
        $started = [datetime]::UtcNow
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $Ctx.Requests++
        $uri = "https://$($Ctx.HostName)$Path" + $(if ($Query) { "?$Query" } else { '' })
        if ($Ctx.Dry) {
            Write-Host ("[план] GET {0}" -f (Format-Mask ($Path + $(if ($Query) { "?$Query" } else { '' }))))
            $r = [pscustomobject]@{ Status = 200; Headers = @(, @('content-type', 'application/json')); Body = $script:Utf8NoBom.GetBytes($DryStub); Failure = $null }
        }
        else { $r = Invoke-HttpGet $uri $Headers $ContentType }
        $sw.Stop()
        $Ctx.LastEnd = [datetime]::UtcNow
        $Ctx.NextGap = $Ctx.MinIntervalSec
        $Ctx.Cur.Exchanges++
        if ($null -ne $r.Failure) { Add-Count $Ctx 'HTTP' ('збій:' + $r.Failure.Kind) } else { Add-Count $Ctx 'HTTP' ([string]$r.Status) }
        if (-not $Ctx.Dry) {
            [void](Save-Exchange $Ctx.Rec $Ctx.Cur.Name $Ctx.HostName $Path $Query $r.Status $r.Headers $r.Body $r.Failure $started ([int]$sw.ElapsedMilliseconds))
            $line = if ($null -ne $r.Failure) { "збій мережі ($($r.Failure.Kind))" } else { "HTTP $($r.Status), $($r.Body.Length) байт" }
            Write-Host ("  [{0:D4}] GET {1} -> {2}" -f $Ctx.Rec.Seq, (Format-Mask ($Path + $(if ($Query) { "?$Query" } else { '' }))), $line)
        }
        # ліміти за заголовками
        $rem = Get-HeaderValue $r.Headers 'x-rate-limit-remaining'
        if ($rem -eq '0' -and $r.Status -eq 200) { $Ctx.NextGap = [math]::Max($Ctx.NextGap, (Get-RetryWaitSeconds $r.Headers)) }
        $result = $r
        if ($r.Status -eq 429 -and $NoRetry) {
            Add-Note $Ctx '429 на запит без повтору — записано, сценарій завершено без очікування й повтору'
            break
        }
        if ($r.Status -eq 429) {
            $wait = Get-RetryWaitSeconds $r.Headers
            if ($attempt -eq 1) {
                Add-Note $Ctx "банк відповів 429 — чекаю $wait с і повторюю один раз"
                $Ctx.NextGap = $wait
                continue
            }
            throw 'SCENARIO_STOP: 429 повторно після паузи — сценарій зупинено, ліміт не провокується'
        }
        break
    }
    $result
}

# =============================================================================================
# Конфігурація
# =============================================================================================
function Test-DateText {
    param($Text, [ref]$Out)
    $d = [datetime]::MinValue
    if ([datetime]::TryParseExact([string]$Text, 'yyyy-MM-dd', [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::None, [ref]$d)) { $Out.Value = $d; return $true }
    $false
}

function Resolve-BankConfig {
    param([string]$Key, $Raw, [bool]$Dry)
    $problems = [System.Collections.Generic.List[string]]::new()
    $notes = [System.Collections.Generic.List[string]]::new()
    $c = @{}
    foreach ($k in $Raw.Keys) { $c[$k] = $Raw[$k] }
    $sc = @{}
    if ($Raw.Scenarios -is [System.Collections.IDictionary]) { foreach ($k in $Raw.Scenarios.Keys) { $sc[$k] = [bool]$Raw.Scenarios[$k] } }
    $c.Scenarios = $sc
    $label = @{ Privat = 'Privat'; MonoCorp = 'MonoCorp'; MonoFop = 'MonoFop'; Pumb = 'Pumb' }[$Key]

    $needText = {
        param([string]$Field, [string]$Fake, [string]$Hint)
        if (Test-Placeholder $c[$Field]) {
            if ($Dry) { $c[$Field] = $Fake; $notes.Add("$label.$Field — заглушка, для dry-run підставлено вигадане значення") }
            else { $problems.Add("$label.$Field не заповнено (стоїть заглушка або порожньо). $Hint") }
        }
    }
    $isIban = { param($v) ([string]$v) -match '^UA\d{27}$' }

    switch ($Key) {
        'Privat' {
            & $needText 'ClientId' 'DRYRUN-FAKE-ID' 'Ідентифікатор із налаштувань застосунку «Інтеграція (Автоклієнт)» («ID i Token»).'
            & $needText 'Token' 'DRYRUN-FAKE-TOKEN-0000000000' 'Токен із налаштувань застосунку «Інтеграція (Автоклієнт)».'
        }
        'MonoCorp' { & $needText 'Token' 'DRYRUN-FAKE-TOKEN-0000000000' 'Токен із web.monobank.ua (кабінет юросіб, розділ токенів, обрана компанія).' }
        'MonoFop' { & $needText 'Token' 'DRYRUN-FAKE-TOKEN-0000000000' 'Особистий токен із api.monobank.ua.' }
        'Pumb' {
            & $needText 'ClientId' 'DRYRUN-FAKE-CLIENT' 'client_id із файлу налаштувань ПУМБ (settings.txt).'
            & $needText 'ClientSecret' 'DRYRUN-FAKE-SECRET-0000000000' 'client_secret із файлу налаштувань ПУМБ (settings.txt).'
            & $needText 'Login' 'dryrun-fake-login' 'Логін користувача інтернет-клієнт-банку ПУМБ.'
            & $needText 'Password' 'DRYRUN-FAKE-PASSWORD-0000' 'Пароль користувача інтернет-клієнт-банку ПУМБ.'
        }
    }

    # рахунки
    if ($Key -eq 'MonoFop') {
        if (Test-Placeholder $c.Iban) {
            if ($Dry) { $c.Iban = $script:FakeIban; $notes.Add("$label.Iban — заглушка, для dry-run підставлено вигаданий IBAN") }
            else { $problems.Add("$label.Iban не заповнено. IBAN рахунку ФОП: UA + 27 цифр.") }
        }
        elseif (-not (& $isIban $c.Iban)) { $problems.Add("$label.Iban має бути UA + 27 цифр.") }
    }
    else {
        $accs = @($c.Accounts | Where-Object { -not (Test-Placeholder $_) })
        if ($accs.Count -eq 0) {
            if ($Dry) { $accs = @($script:FakeIban); $notes.Add("$label.Accounts — заглушки, для dry-run підставлено вигаданий IBAN") }
            else { $problems.Add("$label.Accounts: немає жодного заповненого IBAN (UA + 27 цифр).") }
        }
        foreach ($a in $accs) { if (-not (& $isIban $a)) { $problems.Add("$label.Accounts: значення не схоже на IBAN (UA + 27 цифр).") } }
        $c.Accounts = $accs
    }

    # періоди
    $parsePeriod = {
        param([string]$Name, $P, [bool]$Required, [string]$FakeFrom, [string]$FakeTo)
        $empty = ($null -eq $P) -or ((Test-Placeholder $P.From) -and (Test-Placeholder $P.To))
        if ($empty) {
            if ($Required) {
                if ($Dry) { $notes.Add("$label.$Name — заглушка, для dry-run підставлено вигаданий період"); return @{ From = [datetime]$FakeFrom; To = [datetime]$FakeTo } }
                $problems.Add("$label.$Name не заповнено (From/To у форматі РРРР-ММ-ДД).")
            }
            return $null
        }
        $f = [datetime]::MinValue; $t = [datetime]::MinValue
        if (-not (Test-DateText $P.From ([ref]$f)) -or -not (Test-DateText $P.To ([ref]$t))) { $problems.Add("$label.$Name`: дати мають бути у форматі РРРР-ММ-ДД, обидві."); return $null }
        if ($f -gt $t) { $problems.Add("$label.$Name`: From пізніше за To."); return $null }
        if ($t -ge (ConvertFrom-UnixKyiv ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())).Date) { $problems.Add("$label.$Name`: період має закінчуватись до сьогоднішнього дня (сьогодні ще проміжний)."); return $null }
        @{ From = $f; To = $t }
    }
    $fakeTo = if ($Key -eq 'MonoFop') { '2020-02-20' } else { '2020-01-03' }
    $c.PeriodParsed = & $parsePeriod 'Period' $Raw.Period $true '2020-01-01' $fakeTo
    $c.ReversalParsed = & $parsePeriod 'ReversalPeriod' $Raw.ReversalPeriod $false '' ''
    if ($Key -in 'MonoFop', 'MonoCorp', 'Pumb') { $c.SaturatedParsed = & $parsePeriod 'SaturatedPeriod' $Raw.SaturatedPeriod $false '' '' }
    # за замовчуванням сценарій «період із поверненням» вмикається, лише якщо період заданий
    foreach ($n in 'Reversal') { if (-not $c.ReversalParsed) { $c.Scenarios[$n] = $false } }
    [pscustomobject]@{ Problems = $problems.ToArray(); Notes = $notes.ToArray(); Cfg = $c }
}

function Test-ScenarioOn {
    param($Cfg, [string]$Name, [bool]$Default = $true)
    if ($Cfg.Scenarios.ContainsKey($Name)) { return [bool]$Cfg.Scenarios[$Name] }
    $Default
}

# =============================================================================================
# Розбір сторінок для зведень (лише кількості; суми — власнику)
# =============================================================================================
function Add-PrivatTxDigest {
    param($Ctx, $Json, [string]$Key)
    $Ctx.Cur.Pages++
    $tx = @($Json[$Key])
    Add-Count $Ctx 'розмір сторінки' ([string]$tx.Count)
    foreach ($t in $tx) {
        $Ctx.Cur.Ops++
        Add-Count $Ctx 'PR_PR' ([string]$t['PR_PR'])
        Add-Count $Ctx 'FL_REAL' ([string]$t['FL_REAL'])
        Add-Count $Ctx 'CCY' ([string]$t['CCY'])
        Add-Count $Ctx 'TRANTYPE' ([string]$t['TRANTYPE'])
        Add-IdValue $Ctx 'REF+REFN' ("$($t['REF'])|$($t['REFN'])")
        Add-IdValue $Ctx 'TECHNICAL_TRANSACTION_ID' $t['TECHNICAL_TRANSACTION_ID']
        Add-IdValue $Ctx 'ID' $t['ID']
        Add-Sum $Ctx ("$($t['CCY']) $($t['TRANTYPE']) PR_PR=$($t['PR_PR'])") (ConvertTo-DecimalSafe $t['SUM'])
    }
}

function Add-MonoTxDigest {
    param($Ctx, $Items, [bool]$IsFop)
    $Ctx.Cur.Pages++
    Add-Count $Ctx 'розмір сторінки' ([string]@($Items).Count)
    $times = @()
    foreach ($t in @($Items)) {
        $Ctx.Cur.Ops++
        if ($IsFop) { Add-Count $Ctx 'hold' ([string]$t['hold']) }
        else { Add-Count $Ctx 'status' ([string]$t['status'] + $(if ($t['reverse']) { '+reverse' } else { '' })) }
        Add-Count $Ctx 'currencyCode' ([string]$t['currencyCode'])
        if ($null -ne $t['completedTime']) { Add-Count $Ctx 'є completedTime' 'так' }
        if ($null -ne $t['comment']) { Add-Count $Ctx 'є comment' 'так' }
        Add-IdValue $Ctx 'id' $t['id']
        if ($null -ne $t['time']) { $times += [long]$t['time'] }
        $amt = (ConvertTo-DecimalSafe $t['amount']) / 100
        $stat = if ($IsFop) { "hold=$($t['hold'])" } else { [string]$t['status'] + $(if ($t['reverse']) { '+reverse' } else { '' }) }
        Add-Sum $Ctx ("$($t['currencyCode']) $stat $(if ($amt -ge 0) { 'надходження' } else { 'списання' })") $amt
    }
    if ($times.Count -ge 2) {
        $asc = $true; $desc = $true
        for ($i = 1; $i -lt $times.Count; $i++) { if ($times[$i] -lt $times[$i - 1]) { $asc = $false }; if ($times[$i] -gt $times[$i - 1]) { $desc = $false } }
        Add-Count $Ctx 'порядок time на сторінці' $(if ($desc -and -not $asc) { 'нові->старі' } elseif ($asc -and -not $desc) { 'старі->нові' } elseif ($asc) { 'однаковий time' } else { 'змішаний' })
    }
}

# =============================================================================================
# ПриватБанк
# =============================================================================================
function Join-Query { param([string[]]$Parts) ($Parts | Where-Object { $_ }) -join '&' }
function Format-PrivatDate { param([datetime]$D) $D.ToString('dd-MM-yyyy', [System.Globalization.CultureInfo]::InvariantCulture) }

function Read-PrivatPages {
    param($Ctx, [string]$Path, [string[]]$QueryParts, [string]$Key, [int]$MaxPages, [string]$ContentType = $null)
    $follow = $null
    $stub = '{"status":"SUCCESS","type":"x","exist_next_page":false,"' + $Key + '":[]}'
    while ($true) {
        $q = Join-Query ($QueryParts + $(if ($follow) { "followId=$([uri]::EscapeDataString($follow))" }))
        $r = Invoke-Api $Ctx $Path $q -DryStub $stub -ContentType $ContentType
        if ($null -ne $r.Failure -or $r.Status -ne 200) { Add-Note $Ctx 'сторінка не отримана (збій або не 200) — читання зупинено'; return }
        $j = ConvertFrom-BodyBytes $r.Body $r.Headers
        if ($j -isnot [System.Collections.IDictionary]) { Add-Note $Ctx 'тіло не JSON-об''єкт — читання зупинено'; return }
        if ([string]$j['status'] -ne 'SUCCESS') { Add-Count $Ctx 'status у тілі' ([string]$j['status']); Add-Note $Ctx 'status у тілі не SUCCESS — читання зупинено'; return }
        Add-Count $Ctx 'status у тілі' 'SUCCESS'
        if ($Key -eq 'transactions') { Add-PrivatTxDigest $Ctx $j $Key; $Ctx.Captured.Add(@($j[$Key])) }
        else {
            $Ctx.Cur.Pages++
            foreach ($b in @($j[$Key])) {
                $Ctx.Cur.Ops++
                Add-Count $Ctx 'currency' ([string]$b['currency'])
                Add-Count $Ctx 'is_final_bal' ([string]$b['is_final_bal'])
                Write-Owner $Ctx ("  баланс {0}: вхідний {1}, вихідний {2}, оборот Дт {3} Кт {4}, is_final_bal={5}" -f $b['currency'], $b['balanceIn'], $b['balanceOut'], $b['turnoverDebt'], $b['turnoverCred'], $b['is_final_bal'])
            }
        }
        if (-not $j['exist_next_page']) { return }
        $follow = [string]$j['next_page_id']
        if (-not $follow) { Add-Note $Ctx 'exist_next_page=true без next_page_id'; return }
        if ($Ctx.Cur.Pages -ge $MaxPages) { Add-Note $Ctx "досягнуто ліміту сторінок рекордера ($MaxPages) — решту не читано"; return }
    }
}

# Кандидат для виміру DAT_KL: операція, у якої день DAT_KL (dd.MM.yyyy) відмінний від дня DAT_OD. З кількох — з найбільшою
# відстанню (у днях) від DAT_OD до найближчої межі періоду, щоб запит не збігся з основним. $Pages: масиви операцій сторінок.
function Select-DatKlCandidate {
    param($Pages, [datetime]$PeriodFrom, [datetime]$PeriodTo)
    $ci = [System.Globalization.CultureInfo]::InvariantCulture
    $best = $null; $bestDist = -1; $n = 0
    foreach ($pg in @($Pages)) {
        foreach ($t in @($pg)) {
            $od = [datetime]::MinValue; $kl = [datetime]::MinValue
            if (-not [datetime]::TryParseExact([string]$t['DAT_OD'], 'dd.MM.yyyy', $ci, [System.Globalization.DateTimeStyles]::None, [ref]$od)) { continue }
            if (-not [datetime]::TryParseExact([string]$t['DAT_KL'], 'dd.MM.yyyy', $ci, [System.Globalization.DateTimeStyles]::None, [ref]$kl)) { continue }
            if ($od -eq $kl) { continue }
            $n++
            $dist = [int][math]::Min(($od - $PeriodFrom.Date).TotalDays, ($PeriodTo.Date - $od).TotalDays)
            if ($dist -gt $bestDist) { $best = $od; $bestDist = $dist }
        }
    }
    if ($null -eq $best) { return $null }
    [pscustomobject]@{ Day = $best; Dist = $bestDist; Candidates = $n }
}

function Invoke-PrivatRun {
    param($Cfg, $Ctx)
    $Ctx.BaseHeaders = @{ token = $Cfg.Token; id = $Cfg.ClientId; 'User-Agent' = $script:UserAgent }
    $Ctx.ContentType = 'application/json;charset=utf8'
    $P = $Cfg.PeriodParsed
    $from = Format-PrivatDate $P.From; $to = Format-PrivatDate $P.To
    $small = [int]($Cfg.SmallLimit ?? 5); $work = [int]($Cfg.WorkLimit ?? 100)
    $maxPages = [int]($Cfg.MaxPages ?? 100); $maxSmall = [int]($Cfg.MaxSmallPages ?? 40)
    $tx = '/api/statements/transactions'

    if (Test-ScenarioOn $Cfg 'Settings') {
        Invoke-Scenario $Ctx 'privat_settings' {
            $r = Invoke-Api $Ctx '/api/statements/settings' '' -DryStub '{"status":"SUCCESS","settings":{"phase":"WRK","work_balance":"N"}}'
            $j = ConvertFrom-BodyBytes $r.Body $r.Headers
            if ($j -is [System.Collections.IDictionary] -and $j['settings'] -is [System.Collections.IDictionary]) {
                $s = $j['settings']
                Add-Count $Ctx 'phase' ([string]$s['phase']); Add-Count $Ctx 'work_balance' ([string]$s['work_balance'])
                Write-Owner $Ctx ("  settings: today={0}, lastday={1}, date_final_statement={2}, server_date_time={3}, phase={4}, work_balance={5}" -f $s['today'], $s['lastday'], $s['date_final_statement'], $s['server_date_time'], $s['phase'], $s['work_balance'])
                if ([string]$s['work_balance'] -eq 'Y') { $Ctx.Abort = 'банк повідомив work_balance=Y (йде регламент) — запити не робити, повторіть пізніше' }
            }
            else { Add-Note $Ctx 'відповідь settings не розібрана' }
        }
    }

    $i = 0
    foreach ($iban in $Cfg.Accounts) {
        $i++; $tag = "a$i"
        $acc14 = $iban.Substring($iban.Length - 14)
        if (Test-ScenarioOn $Cfg 'Balances') {
            Invoke-Scenario $Ctx "privat_${tag}_balance_period" { Read-PrivatPages $Ctx '/api/statements/balance' @("acc=$acc14", "startDate=$from", "endDate=$to") 'balances' $maxPages }
        }
        if (Test-ScenarioOn $Cfg 'BalanceInterimFinal') {
            Invoke-Scenario $Ctx "privat_${tag}_balance_interim" { Read-PrivatPages $Ctx '/api/statements/balance/interim' @("acc=$acc14", 'limit=100') 'balances' $maxPages }
            Invoke-Scenario $Ctx "privat_${tag}_balance_final" { Read-PrivatPages $Ctx '/api/statements/balance/final' @("acc=$acc14", 'limit=100') 'balances' $maxPages }
        }
        if (Test-ScenarioOn $Cfg 'TxSmallLimit') {
            Invoke-Scenario $Ctx "privat_${tag}_tx_small_limit" { Read-PrivatPages $Ctx $tx @("acc=$acc14", "startDate=$from", "endDate=$to", "limit=$small") 'transactions' $maxSmall }
        }
        $memoTx = $null   # операції TxWorkLimit цього прогону (для виміру DAT_KL)
        if (Test-ScenarioOn $Cfg 'TxWorkLimit') {
            Invoke-Scenario $Ctx "privat_${tag}_tx_work_limit" { Read-PrivatPages $Ctx $tx @("acc=$acc14", "startDate=$from", "endDate=$to", "limit=$work") 'transactions' $maxPages }
            $memoTx = @($Ctx.Captured)
        }
        if (Test-ScenarioOn $Cfg 'DatKlBoundary' $false) {
            if ($null -eq $memoTx) {
                Invoke-Scenario $Ctx "privat_${tag}_datkl_source" { Read-PrivatPages $Ctx $tx @("acc=$acc14", "startDate=$from", "endDate=$to", "limit=$work") 'transactions' $maxPages }
                $memoTx = @($Ctx.Captured)
            }
            $dk = Select-DatKlCandidate $memoTx $P.From $P.To
            if ($null -eq $dk -and $Ctx.Dry) { Write-Host '[dry-run] у заглушках немає операцій — для плану запитів підставлено синтетичного кандидата'; $dk = [pscustomobject]@{ Day = $P.From; Dist = 0; Candidates = 0 } }
            if ($null -eq $dk) {
                Invoke-Scenario $Ctx "privat_${tag}_datkl_boundary" {
                    Add-RecorderFailure $Ctx $tx (Join-Query @("acc=$acc14", "startDate=$from", "endDate=$to", "limit=$work")) 'no_candidate' 'немає операції з днем DAT_KL, відмінним від дня DAT_OD, у прочитаних сторінках; запиту не робили'
                }
            }
            else {
                $dkDay = Format-PrivatDate $dk.Day
                Invoke-Scenario $Ctx "privat_${tag}_datkl_boundary" {
                    Add-Note $Ctx "кандидат обрано: придатних операцій $($dk.Candidates); днів до найближчої межі періоду: $($dk.Dist)"
                    Read-PrivatPages $Ctx $tx @("acc=$acc14", "startDate=$dkDay", "endDate=$dkDay", "limit=$work") 'transactions' $maxPages
                }
            }
        }
        if (Test-ScenarioOn $Cfg 'TxDefaultLimit') {
            Invoke-Scenario $Ctx "privat_${tag}_tx_default_limit" { Read-PrivatPages $Ctx $tx @("acc=$acc14", "startDate=$from", "endDate=$to") 'transactions' $maxSmall }
        }
        if (Test-ScenarioOn $Cfg 'TxNoEndDate') {
            # без endDate: startDate = початок періоду; що банк віддає до «сьогодні» (порівняння з тим самим періодом з endDate)
            Invoke-Scenario $Ctx "privat_${tag}_tx_no_enddate" { Read-PrivatPages $Ctx $tx @("acc=$acc14", "startDate=$from", "limit=$work") 'transactions' $maxPages }
        }
        if (Test-ScenarioOn $Cfg 'TxFullIban') {
            Invoke-Scenario $Ctx "privat_${tag}_tx_acc_full_iban" { Read-PrivatPages $Ctx $tx @("acc=$iban", "startDate=$from", "endDate=$to", "limit=$work") 'transactions' $maxPages }
        }
        if (Test-ScenarioOn $Cfg 'TxInterim') {
            Invoke-Scenario $Ctx "privat_${tag}_tx_interim" { Read-PrivatPages $Ctx "$tx/interim" @("acc=$acc14", 'limit=100') 'transactions' $maxPages }
        }
        if (Test-ScenarioOn $Cfg 'TxFinal') {
            Invoke-Scenario $Ctx "privat_${tag}_tx_final" { Read-PrivatPages $Ctx "$tx/final" @("acc=$acc14", 'limit=100') 'transactions' $maxPages }
        }
        if (Test-ScenarioOn $Cfg 'TxCp1251') {
            # банк може відповідати в cp1251: той самий запит із Content-Type charset=cp1251
            Invoke-Scenario $Ctx "privat_${tag}_tx_charset_cp1251" { Read-PrivatPages $Ctx $tx @("acc=$acc14", "startDate=$from", "endDate=$to", "limit=$small") 'transactions' 3 'application/json;charset=cp1251' }
        }
        if ((Test-ScenarioOn $Cfg 'Reversal') -and $Cfg.ReversalParsed) {
            $rf = Format-PrivatDate $Cfg.ReversalParsed.From; $rt = Format-PrivatDate $Cfg.ReversalParsed.To
            Invoke-Scenario $Ctx "privat_${tag}_tx_reversal_period" { Read-PrivatPages $Ctx $tx @("acc=$acc14", "startDate=$rf", "endDate=$rt", "limit=$work") 'transactions' $maxPages }
        }
        if ((Test-ScenarioOn $Cfg 'Errors') -and $i -eq 1) {
            $fakeHdr = @{ token = $script:FakeToken; id = $script:FakeId; 'User-Agent' = $script:UserAgent }
            $today = (ConvertFrom-UnixKyiv ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())).Date
            Invoke-Scenario $Ctx 'privat_errors_invalid_token' {
                [void](Invoke-Api $Ctx '/api/statements/settings' '' -Headers $fakeHdr)
                [void](Invoke-Api $Ctx $tx (Join-Query @("acc=$acc14", "startDate=$from", "endDate=$to", "limit=$small")) -Headers $fakeHdr)
            }
            Invoke-Scenario $Ctx 'privat_errors_start_after_end' { [void](Invoke-Api $Ctx $tx (Join-Query @("acc=$acc14", "startDate=$to", "endDate=$from", "limit=$small"))) }
            Invoke-Scenario $Ctx 'privat_errors_future_period' {
                [void](Invoke-Api $Ctx $tx (Join-Query @("acc=$acc14", "startDate=$(Format-PrivatDate $today.AddDays(30))", "endDate=$(Format-PrivatDate $today.AddDays(60))", "limit=$small")))
            }
            Invoke-Scenario $Ctx 'privat_errors_foreign_account' {
                [void](Invoke-Api $Ctx $tx (Join-Query @("acc=$($script:FakeIban.Substring(15))", "startDate=$from", "endDate=$to", "limit=$small")))
            }
        }
    }
}

# =============================================================================================
# Межі запиту monobank: збій рекордера, вибір операції, пари запитів (D36 п. 11)
# =============================================================================================
# Збій на боці рекордера (запит НЕ надсилався): обмін без response, failure.kind = stuck_cursor | no_candidate.
# Поле request — запит, який було б надіслано (stuck_cursor) або вибірка, з якої операцію не знайдено (no_candidate). FORMAT.md.
function Add-RecorderFailure {
    param($Ctx, [string]$Path, [string]$Query, [string]$Kind, [string]$Text)
    Assert-ReadOnlyRequest 'GET' $Ctx.HostName $Path
    Add-Count $Ctx 'HTTP' ('збій:' + $Kind)
    Add-Note $Ctx "$Kind — $Text"
    if ($Ctx.Dry) { return }
    [void](Save-Exchange $Ctx.Rec $Ctx.Cur.Name $Ctx.HostName $Path $Query $null @() ([byte[]]@()) ([pscustomobject]@{ Kind = $Kind; Text = $Text }) ([datetime]::UtcNow) 0)
}

# Обирає операцію, єдину у своїй секунді time (серед усіх сторінок вибірки), лише зі сторінки, НЕ повної за її limit.
# З кількох придатних — ту, що найдалі від найближчої іншої операції (щоб сусідня секунда не плутала пару). $Pages: @{Items; Limit}.
function Select-BoundaryCandidate {
    param($Pages)
    $count = @{}
    foreach ($pg in @($Pages)) {
        foreach ($op in @($pg.Items)) {
            if ($null -eq $op['time']) { continue }
            $k = [long]$op['time']
            $count[$k] = 1 + [int]($count[$k] ?? 0)
        }
    }
    $cand = [System.Collections.Generic.HashSet[long]]::new()
    foreach ($pg in @($Pages)) {
        if (@($pg.Items).Count -ge [int]$pg.Limit) { continue }
        foreach ($op in @($pg.Items)) {
            if ($null -eq $op['time']) { continue }
            $k = [long]$op['time']
            if ($count[$k] -eq 1) { [void]$cand.Add($k) }
        }
    }
    if ($cand.Count -eq 0) { return $null }
    $sorted = @($count.Keys | ForEach-Object { [long]$_ } | Sort-Object)
    $best = $null; $bestGap = [long]-1
    for ($i = 0; $i -lt $sorted.Count; $i++) {
        $t = [long]$sorted[$i]
        if (-not $cand.Contains($t)) { continue }
        $gap = [long]31536000
        if ($i -gt 0) { $gap = [math]::Min($gap, $t - [long]$sorted[$i - 1]) }
        if ($i -lt $sorted.Count - 1) { $gap = [math]::Min($gap, [long]$sorted[$i + 1] - $t) }
        if ($gap -gt $bestGap) { $best = $t; $bestGap = $gap }
    }
    [pscustomobject]@{ Time = [long]$best; Gap = $bestGap; Candidates = $cand.Count }
}

# Пари запитів на включність меж: from = t і t - 1 (to — t + 3600, не пізніше кінця періоду); to = t і t + 1
# (from — t - 3600, не раніше початку періоду). Кожен запит — окремий сценарій. Висновку рекордер не робить.
function Invoke-BoundaryPairs {
    param($Ctx, [string]$Prefix, $Pages, [long]$PeriodFrom, [long]$PeriodTo, [scriptblock]$PathFor, [string]$Query, [bool]$IsFop)
    $cand = Select-BoundaryCandidate $Pages
    if ($null -eq $cand -and $Ctx.Dry) {
        Write-Host '[dry-run] у заглушках немає операцій — для плану запитів підставлено синтетичного кандидата'
        $cand = [pscustomobject]@{ Time = $PeriodFrom + 86400; Gap = 0; Candidates = 0 }
    }
    if ($null -eq $cand) {
        Invoke-Scenario $Ctx "${Prefix}_boundary_candidate" {
            Add-RecorderFailure $Ctx (& $PathFor $PeriodFrom $PeriodTo) $Query 'no_candidate' 'немає операції, єдиної у своїй секунді, на неповній сторінці вибірки; пар не робили'
        }
        return
    }
    $t = [long]$cand.Time
    $toA = [math]::Min($t + 3600, $PeriodTo)
    $fromB = [math]::Max($t - 3600, $PeriodFrom)
    $steps = @(
        @{ Tag = 'from_eq'; F = $t; T = $toA }
        @{ Tag = 'from_shift'; F = ($t - 1); T = $toA }
        @{ Tag = 'to_eq'; F = $fromB; T = $t }
        @{ Tag = 'to_shift'; F = $fromB; T = ($t + 1) }
    )
    $first = $true
    foreach ($st in $steps) {
        $qf = [long]$st.F; $qt = [long]$st.T; $isFirst = $first; $first = $false
        Invoke-Scenario $Ctx "${Prefix}_boundary_$($st.Tag)" {
            if ($isFirst) { Add-Note $Ctx "кандидат обрано: придатних операцій $($cand.Candidates); секунд до найближчої іншої операції: $($cand.Gap)" }
            $r = Invoke-Api $Ctx (& $PathFor $qf $qt) $Query -DryStub '[]'
            $j = ConvertFrom-BodyBytes $r.Body $r.Headers
            if ($j -is [array]) { Add-MonoTxDigest $Ctx @($j) $IsFop }
        }
    }
}

# =============================================================================================
# monobank юросіб (corp-api)
# =============================================================================================
# -Overlap (D36 п. 11): продовження з to = найраніша time + 1, тож межова секунда потрапляє в наступний запит знову.
# Якщо наступний запит збігся б із попереднім (повна сторінка в одній секунді), пишеться збій stuck_cursor і читання зупиняється.
function Read-MonoCorpStatement {
    param($Ctx, [string]$Iban, [long]$FromUnix, [long]$ToUnix, [int]$Limit, [int]$MaxPages, [string]$Extra = '', [switch]$Overlap)
    $upper = $ToUnix
    while ($true) {
        $r = Invoke-Api $Ctx "/ext/v1/statement/$Iban/$FromUnix/$upper" (Join-Query @("limit=$Limit", $Extra)) -DryStub '[]'
        if ($null -ne $r.Failure -or $r.Status -ne 200) { Add-Note $Ctx 'сторінка не отримана (збій або не 200) — читання зупинено'; return }
        $j = ConvertFrom-BodyBytes $r.Body $r.Headers
        if ($j -isnot [array]) { Add-Note $Ctx 'тіло не JSON-масив — читання зупинено'; return }
        $page = @($j)
        Add-MonoTxDigest $Ctx $page $false
        $Ctx.Captured.Add([pscustomobject]@{ Items = $page; Limit = $Limit })
        if ($page.Count -lt $Limit) { return }
        $earliest = ($page | ForEach-Object { [long]$_['time'] } | Measure-Object -Minimum).Minimum
        if ($earliest -le $FromUnix) { Add-Note $Ctx 'повна сторінка дійшла до початку періоду'; return }
        if ($Overlap) {
            $next = $earliest + 1
            if ($next -ge $upper) {
                Add-RecorderFailure $Ctx "/ext/v1/statement/$Iban/$FromUnix/$next" (Join-Query @("limit=$Limit", $Extra)) 'stuck_cursor' 'продовження збіглось би з попереднім запитом: повна сторінка в одній секунді; читання зупинено'
                return
            }
        }
        elseif ($earliest -ge $upper) { Add-Note $Ctx 'верхня межа не зменшилась (багато операцій в одну секунду) — читання зупинено'; return }
        if ($Ctx.Cur.Pages -ge $MaxPages) { Add-Note $Ctx "досягнуто ліміту сторінок рекордера ($MaxPages)"; return }
        $upper = $(if ($Overlap) { $next } else { $earliest })
    }
}

function Invoke-MonoCorpRun {
    param($Cfg, $Ctx)
    $Ctx.BaseHeaders = @{ 'x-token' = $Cfg.Token; accept = 'application/json'; 'User-Agent' = $script:UserAgent }
    $P = $Cfg.PeriodParsed
    $fromU = ConvertTo-UnixKyiv $P.From
    $toU = ConvertTo-UnixKyiv $P.To.AddDays(1).AddSeconds(-1)
    $iso = { param([datetime]$d) $d.ToString('yyyy-MM-dd', [System.Globalization.CultureInfo]::InvariantCulture) }
    $small = [int]($Cfg.SmallLimit ?? 10); $maxPages = [int]($Cfg.MaxPages ?? 200); $maxSmall = [int]($Cfg.MaxSmallPages ?? 60)

    if (Test-ScenarioOn $Cfg 'Accounts') {
        Invoke-Scenario $Ctx 'corp_accounts' {
            $r = Invoke-Api $Ctx '/ext/v1/accounts' '' -DryStub '[]'
            $j = ConvertFrom-BodyBytes $r.Body $r.Headers
            if ($j -is [array]) {
                Add-Count $Ctx 'рахунків у відповіді' ([string]@($j).Count)
                foreach ($a in $j) { Add-Count $Ctx 'currency' ([string]$a['currency']); Write-Owner $Ctx ("  рахунок {0}: валюта {1}, залишок {2}" -f (Format-Mask ([string]$a['iban'])), $a['currency'], $a['balance']) }
            }
            else { Add-Note $Ctx 'відповідь не масив' }
        }
    }
    $i = 0
    foreach ($iban in $Cfg.Accounts) {
        $i++; $tag = "a$i"
        if (Test-ScenarioOn $Cfg 'Balances') {
            Invoke-Scenario $Ctx "corp_${tag}_balances" {
                $r = Invoke-Api $Ctx "/ext/v1/accounts/$iban/balances" "dateFrom=$(& $iso $P.From)&dateTo=$(& $iso $P.To)" -DryStub '[]'
                $j = ConvertFrom-BodyBytes $r.Body $r.Headers
                if ($j -is [array]) {
                    Add-Count $Ctx 'елементів' ([string]@($j).Count)
                    foreach ($b in $j) { Add-Count $Ctx 'isFinal' ([string]$b['isFinal']); Write-Owner $Ctx ("  баланс {0}: {1} (isFinal={2})" -f $b['date'], $b['balance'], $b['isFinal']) }
                }
            }
        }
        $memo500 = $null   # сторінки limit500 за основний період, якщо сценарій цього прогону їх прочитав (для пар меж)
        if (Test-ScenarioOn $Cfg 'StatementLimit500') {
            Invoke-Scenario $Ctx "corp_${tag}_statement_limit500" { Read-MonoCorpStatement $Ctx $iban $fromU $toU 500 $maxPages }
            $memo500 = @($Ctx.Captured)
        }
        # Насичений період (необов'язковий; відсутній блок чи перемикач = вимкнено, не помилка): limit=500, сторінки зсувом
        # верхньої межі до найраніша time + 1 (D36 п. 11, -Overlap; збіг запитів — збій stuck_cursor), доки сторінка повна, — максимум сторінки банку. Розміри сторінок — у summary-agent.txt.
        if ((Test-ScenarioOn $Cfg 'Saturated' $false) -and $Cfg.SaturatedParsed) {
            $sf = ConvertTo-UnixKyiv $Cfg.SaturatedParsed.From; $st = ConvertTo-UnixKyiv $Cfg.SaturatedParsed.To.AddDays(1).AddSeconds(-1)
            Invoke-Scenario $Ctx "corp_${tag}_statement_saturated_limit500" { Read-MonoCorpStatement $Ctx $iban $sf $st 500 $maxPages -Overlap }
        }
        else { Write-Host "[вимкнено] corp_${tag}_statement_saturated_limit500 — немає SaturatedPeriod або Scenarios.Saturated не ввімкнено" }
        if (Test-ScenarioOn $Cfg 'StatementSmallLimit') {
            Invoke-Scenario $Ctx "corp_${tag}_statement_small_limit" { Read-MonoCorpStatement $Ctx $iban $fromU $toU $small $maxSmall }
        }
        if (Test-ScenarioOn $Cfg 'StatementSmallLimitOverlap' $false) {
            # той самий період і limit, але продовження з to = найраніша time + 1 (D36 п. 11)
            Invoke-Scenario $Ctx "corp_${tag}_statement_small_limit_overlap" { Read-MonoCorpStatement $Ctx $iban $fromU $toU $small $maxSmall -Overlap }
        }
        if (Test-ScenarioOn $Cfg 'StatementOrder') {
            # без direction (за замовчуванням) і з deprecated direction UP/DOWN — одна коротка сторінка кожен
            foreach ($dir in @('', 'UP', 'DOWN')) {
                $name = "corp_${tag}_statement_order_" + $(if ($dir) { $dir } else { 'default' })
                Invoke-Scenario $Ctx $name {
                    $r = Invoke-Api $Ctx "/ext/v1/statement/$iban/$fromU/$toU" (Join-Query @('limit=5', $(if ($dir) { "direction=$dir" } else { '' }))) -DryStub '[]'
                    $j = ConvertFrom-BodyBytes $r.Body $r.Headers
                    if ($j -is [array]) { Add-MonoTxDigest $Ctx @($j) $false }
                }
            }
        }
        if (Test-ScenarioOn $Cfg 'DailyWindows') {
            # добові вікна (київська доба), limit=500 — еталон повноти
            Invoke-Scenario $Ctx "corp_${tag}_daily_windows" {
                $full = 0
                for ($d = $P.From; $d -le $P.To; $d = $d.AddDays(1)) {
                    $r = Invoke-Api $Ctx "/ext/v1/statement/$iban/$(ConvertTo-UnixKyiv $d)/$(ConvertTo-UnixKyiv $d.AddDays(1).AddSeconds(-1))" 'limit=500' -DryStub '[]'
                    if ($null -ne $r.Failure -or $r.Status -ne 200) { continue }
                    $j = ConvertFrom-BodyBytes $r.Body $r.Headers
                    if ($j -is [array]) { Add-MonoTxDigest $Ctx @($j) $false; if (@($j).Count -ge 500) { $full++ } }
                }
                Add-Note $Ctx "діб із повною сторінкою (500): $full"
            }
        }
        if ((Test-ScenarioOn $Cfg 'Reversal') -and $Cfg.ReversalParsed) {
            $rf = ConvertTo-UnixKyiv $Cfg.ReversalParsed.From; $rt = ConvertTo-UnixKyiv $Cfg.ReversalParsed.To.AddDays(1).AddSeconds(-1)
            Invoke-Scenario $Ctx "corp_${tag}_statement_reversal_period" { Read-MonoCorpStatement $Ctx $iban $rf $rt 500 $maxPages }
        }
        if (Test-ScenarioOn $Cfg 'BoundaryPairs' $false) {
            $pages = $memo500
            if ($null -eq $pages) {
                Invoke-Scenario $Ctx "corp_${tag}_boundary_source" {
                    $r = Invoke-Api $Ctx "/ext/v1/statement/$iban/$fromU/$toU" 'limit=500' -DryStub '[]'
                    $j = ConvertFrom-BodyBytes $r.Body $r.Headers
                    if ($j -is [array]) { Add-MonoTxDigest $Ctx @($j) $false; $Ctx.Captured.Add([pscustomobject]@{ Items = @($j); Limit = 500 }) }
                }
                $pages = @($Ctx.Captured)
            }
            $pathFor = { param($f, $t) "/ext/v1/statement/$iban/$f/$t" }.GetNewClosure()
            Invoke-BoundaryPairs $Ctx "corp_${tag}" $pages $fromU $toU $pathFor 'limit=500' $false
        }
        if ((Test-ScenarioOn $Cfg 'Errors') -and $i -eq 1) {
            $fakeHdr = @{ 'x-token' = $script:FakeToken; accept = 'application/json'; 'User-Agent' = $script:UserAgent }
            $today = (ConvertFrom-UnixKyiv ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())).Date
            Invoke-Scenario $Ctx 'corp_errors_invalid_token' { [void](Invoke-Api $Ctx '/ext/v1/accounts' '' -Headers $fakeHdr -DryStub '[]') }
            Invoke-Scenario $Ctx 'corp_errors_from_after_to' { [void](Invoke-Api $Ctx "/ext/v1/statement/$iban/$toU/$fromU" 'limit=5' -DryStub '[]') }
            Invoke-Scenario $Ctx 'corp_errors_future_period' {
                [void](Invoke-Api $Ctx "/ext/v1/statement/$iban/$(ConvertTo-UnixKyiv $today.AddDays(30))/$(ConvertTo-UnixKyiv $today.AddDays(60))" 'limit=5' -DryStub '[]')
            }
            Invoke-Scenario $Ctx 'corp_errors_foreign_account' {
                [void](Invoke-Api $Ctx "/ext/v1/statement/$($script:FakeIban)/$fromU/$toU" 'limit=5' -DryStub '[]')
                [void](Invoke-Api $Ctx "/ext/v1/accounts/$($script:FakeIban)/balances" "dateFrom=$(& $iso $P.From)&dateTo=$(& $iso $P.To)" -DryStub '[]')
            }
            Invoke-Scenario $Ctx 'corp_errors_balances_from_after_to' {
                [void](Invoke-Api $Ctx "/ext/v1/accounts/$iban/balances" "dateFrom=$(& $iso $P.To)&dateTo=$(& $iso $P.From)" -DryStub '[]')
            }
        }
    }
}

# =============================================================================================
# monobank ФОП (персональне API)
# =============================================================================================
# Відрізки ≤ 31 доби (документація: 31 доба + 1 година). Повертає масив @{From=unix;To=unix}.
function Get-FopSegments {
    param([datetime]$From, [datetime]$To)
    $segs = [System.Collections.Generic.List[object]]::new()
    $s = $From
    while ($s -le $To) {
        $e = $s.AddDays(31)
        if ($e -gt $To.AddDays(1)) { $e = $To.AddDays(1) }
        $segs.Add(@{ From = (ConvertTo-UnixKyiv $s); To = ((ConvertTo-UnixKyiv $e) - 1) })
        $s = $e
    }
    , $segs.ToArray()
}

# Читає відрізок: наступна сторінка — зсув верхньої межі до найранішої операції. Умова продовження:
# UntilEmpty — доки сторінка непорожня (вимір розміру сторінки); інакше — доки сторінка має щонайменше ContinueAtLeast операцій.
# -Overlap: продовження з to = найраніша time + 1 (D36 п. 11); збіг із попереднім запитом — збій stuck_cursor.
function Read-FopSegment {
    param($Ctx, [string]$AccId, [long]$FromUnix, [long]$ToUnix, [bool]$UntilEmpty, [int]$ContinueAtLeast, [int]$MaxPages, [switch]$Overlap)
    $upper = $ToUnix; $pages = 0
    while ($true) {
        $r = Invoke-Api $Ctx "/personal/statement/$AccId/$FromUnix/$upper" '' -DryStub '[]'
        $pages++
        if ($null -ne $r.Failure -or $r.Status -ne 200) { Add-Note $Ctx 'сторінка не отримана (збій або не 200) — відрізок зупинено'; return }
        $j = ConvertFrom-BodyBytes $r.Body $r.Headers
        if ($j -isnot [array]) { Add-Note $Ctx 'тіло не JSON-масив — відрізок зупинено'; return }
        $page = @($j)
        Add-MonoTxDigest $Ctx $page $true
        $Ctx.Captured.Add([pscustomobject]@{ Items = $page; Limit = $script:FopPageMax })
        if ($page.Count -eq 0) { return }
        if (-not $UntilEmpty -and $page.Count -lt $ContinueAtLeast) { return }
        $earliest = ($page | ForEach-Object { [long]$_['time'] } | Measure-Object -Minimum).Minimum
        if ($earliest -le $FromUnix) { return }
        if ($Overlap) {
            $next = $earliest + 1
            if ($next -ge $upper) {
                Add-RecorderFailure $Ctx "/personal/statement/$AccId/$FromUnix/$next" '' 'stuck_cursor' 'продовження збіглось би з попереднім запитом: повна сторінка в одній секунді; відрізок зупинено'
                return
            }
        }
        elseif ($earliest -ge $upper) { Add-Note $Ctx 'верхня межа не зменшилась — відрізок зупинено'; return }
        if ($pages -ge $MaxPages) { Add-Note $Ctx "досягнуто ліміту сторінок на відрізок ($MaxPages)"; return }
        $upper = $(if ($Overlap) { $next } else { $earliest })
    }
}

function Get-FopAccountId {
    param($Ctx, $Cfg, $Response)
    $j = ConvertFrom-BodyBytes $Response.Body $Response.Headers
    if ($j -isnot [System.Collections.IDictionary] -or $j['accounts'] -isnot [array]) { Add-Note $Ctx 'client-info: немає масиву accounts'; return $null }
    Add-Count $Ctx 'рахунків у client-info' ([string]@($j['accounts']).Count)
    if ($j['jars'] -is [array]) { Add-Count $Ctx 'банок у client-info' ([string]@($j['jars']).Count) }
    foreach ($a in $j['accounts']) { if ([string]$a['iban'] -eq $Cfg.Iban) { return [string]$a['id'] } }
    Add-Note $Ctx 'IBAN із конфігурації не знайдено серед рахунків client-info'
    $null
}

function Invoke-MonoFopRun {
    param($Cfg, $Ctx)
    $Ctx.BaseHeaders = @{ 'X-Token' = $Cfg.Token; 'User-Agent' = $script:UserAgent }
    $P = $Cfg.PeriodParsed
    $cont = [int]($Cfg.ContinueAtLeast ?? 100); $maxPages = [int]($Cfg.MaxPagesPerSegment ?? 20)
    $accId = $null
    $script:fopAcc = $null
    $stubInfo = '{"accounts":[{"id":"DRYRUN","iban":"' + $Cfg.Iban + '"}],"jars":[]}'

    if (Test-ScenarioOn $Cfg 'ClientInfoThenStatement') {
        # D36 п. 9: чи дає банк виписку одразу після client-info (без паузи 60 с). Один запит, без паузи — свідомо.
        Invoke-Scenario $Ctx 'fop_client_info_then_statement_immediately' {
            $r = Invoke-Api $Ctx '/personal/client-info' '' -DryStub $stubInfo
            $script:fopAcc = Get-FopAccountId $Ctx $Cfg $r
            if ($script:fopAcc) {
                $dayFrom = ConvertTo-UnixKyiv $P.To; $dayTo = ConvertTo-UnixKyiv $P.To.AddDays(1).AddSeconds(-1)
                $r2 = Invoke-Api $Ctx "/personal/statement/$($script:fopAcc)/$dayFrom/$dayTo" '' -NoGap -NoRetry -DryStub '[]'
                $j = ConvertFrom-BodyBytes $r2.Body $r2.Headers
                if ($j -is [array]) { Add-MonoTxDigest $Ctx @($j) $true }
            }
        }
        $accId = $script:fopAcc
    }
    if (-not $accId -and ((Test-ScenarioOn $Cfg 'StatementSegments') -or (Test-ScenarioOn $Cfg 'Saturated') -or (Test-ScenarioOn $Cfg 'BoundaryPairs' $false) -or (Test-ScenarioOn $Cfg 'SaturatedOverlap' $false) -or ((Test-ScenarioOn $Cfg 'Reversal') -and $Cfg.ReversalParsed))) {
        if (-not $accId) {
            Invoke-Scenario $Ctx 'fop_client_info' {
                $r = Invoke-Api $Ctx '/personal/client-info' '' -DryStub $stubInfo
                $script:fopAcc = Get-FopAccountId $Ctx $Cfg $r
            }
            $accId = $script:fopAcc
        }
    }
    if (-not $accId) { Write-Host '[увага] ідентифікатор рахунку ФОП не отримано — сценарії виписок пропущено'; if (-not $Ctx.Dry) { $Ctx.Failed = $true }; return }

    $fopMemo = $null   # сторінки відрізків основного періоду, прочитані в цьому прогоні (для пар меж)
    if (Test-ScenarioOn $Cfg 'StatementSegments') {
        $segs = Get-FopSegments $P.From $P.To
        $n = 0
        $fopMemo = [System.Collections.Generic.List[object]]::new()
        foreach ($sg in $segs) {
            $n++
            Invoke-Scenario $Ctx ("fop_statement_segment_{0:D2}" -f $n) { Read-FopSegment $Ctx $accId $sg.From $sg.To $false $cont $maxPages }
            $fopMemo.AddRange(@($Ctx.Captured))
        }
    }
    if ((Test-ScenarioOn $Cfg 'Saturated') -and $Cfg.SaturatedParsed) {
        # насичений період: читаємо, доки сторінка непорожня, — щоб побачити, скільки операцій банк віддає за раз
        $n = 0
        foreach ($sg in (Get-FopSegments $Cfg.SaturatedParsed.From $Cfg.SaturatedParsed.To)) {
            $n++
            Invoke-Scenario $Ctx ("fop_saturated_segment_{0:D2}" -f $n) { Read-FopSegment $Ctx $accId $sg.From $sg.To $true $cont ([math]::Max($maxPages, 20)) }
        }
    }
    if ((Test-ScenarioOn $Cfg 'Reversal') -and $Cfg.ReversalParsed) {
        $n = 0
        foreach ($sg in (Get-FopSegments $Cfg.ReversalParsed.From $Cfg.ReversalParsed.To)) {
            $n++
            Invoke-Scenario $Ctx ("fop_reversal_segment_{0:D2}" -f $n) { Read-FopSegment $Ctx $accId $sg.From $sg.To $false $cont $maxPages }
        }
    }
    if (Test-ScenarioOn $Cfg 'SaturatedOverlap' $false) {
        # насичений період до неповної сторінки (< 500): продовження з to = найраніша time + 1, пауза 61 с між запитами
        if ($Cfg.SaturatedParsed) {
            $maxSat = [int]($Cfg.MaxSaturatedPages ?? 40)
            Invoke-Scenario $Ctx 'fop_a1_saturated' {
                foreach ($sg in (Get-FopSegments $Cfg.SaturatedParsed.From $Cfg.SaturatedParsed.To)) {
                    $left = $maxSat - $Ctx.Cur.Pages
                    if ($left -le 0) { Add-Note $Ctx "досягнуто ліміту сторінок рекордера ($maxSat)"; break }
                    Read-FopSegment $Ctx $accId $sg.From $sg.To $false $script:FopPageMax $left -Overlap
                }
            }
        }
        else { Invoke-Scenario $Ctx 'fop_a1_saturated' { Add-Note $Ctx 'пропущено: SaturatedPeriod порожній (заглушки) — сценарій не виконувався' } }
    }
    if (Test-ScenarioOn $Cfg 'BoundaryPairs' $false) {
        $pages = $fopMemo
        if ($null -eq $pages) {
            $s0 = (Get-FopSegments $P.From $P.To)[0]
            Invoke-Scenario $Ctx 'fop_a1_boundary_source' { Read-FopSegment $Ctx $accId $s0.From $s0.To $false $script:FopPageMax 1 }
            $pages = @($Ctx.Captured)
        }
        $pathFor = { param($f, $t) "/personal/statement/$accId/$f/$t" }.GetNewClosure()
        Invoke-BoundaryPairs $Ctx 'fop_a1' $pages (ConvertTo-UnixKyiv $P.From) (ConvertTo-UnixKyiv $P.To.AddDays(1).AddSeconds(-1)) $pathFor '' $true
    }
    if (Test-ScenarioOn $Cfg 'Errors') {
        $fakeHdr = @{ 'X-Token' = $script:FakeToken; 'User-Agent' = $script:UserAgent }
        $today = (ConvertFrom-UnixKyiv ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())).Date
        $dayFrom = ConvertTo-UnixKyiv $P.To; $dayTo = ConvertTo-UnixKyiv $P.To.AddDays(1).AddSeconds(-1)
        Invoke-Scenario $Ctx 'fop_errors_invalid_token' { [void](Invoke-Api $Ctx '/personal/client-info' '' -Headers $fakeHdr -DryStub '{}') }
        Invoke-Scenario $Ctx 'fop_errors_from_after_to' { [void](Invoke-Api $Ctx "/personal/statement/$accId/$dayTo/$dayFrom" '' -DryStub '[]') }
        Invoke-Scenario $Ctx 'fop_errors_future_period' {
            [void](Invoke-Api $Ctx "/personal/statement/$accId/$(ConvertTo-UnixKyiv $today.AddDays(30))/$(ConvertTo-UnixKyiv $today.AddDays(60))" '' -DryStub '[]')
        }
        Invoke-Scenario $Ctx 'fop_errors_foreign_account' { [void](Invoke-Api $Ctx "/personal/statement/$($script:FakeMonoAccountId)/$dayFrom/$dayTo" '' -DryStub '[]') }
    }
}

# =============================================================================================
# ПУМБ (Vega/VegaNet): автентифікація password grant і читальні операції
# =============================================================================================
$script:PumbAuthHost = 'auth.fuib.com'
$script:PumbAuthPath = '/auth/realms/VegaNet/protocol/openid-connect/token'
$script:PumbApiHost = 'service.fuib.com'
$script:PumbApiPort = 4103
$script:PumbApiPrefix = '/war_veganet_api'
# Вигадані очевидно фальшиві значення для сценаріїв «свідомі помилки». Справжній логін із хибним паролем не використовується ніколи.
$script:FakeLogin = 'invalid-user-for-recorder'
$script:FakePassword = 'INVALID-PASSWORD-FOR-RECORDER'
$script:FakeClientSecret = 'INVALID-SECRET-FOR-RECORDER-0000'
$script:FakePumbAccountId = '999999999'

# Ключ «вхід погоджено»: його виставляє лише власник (після відповіді на питання, чи не заважає вхід рекордера робочій інтеграції).
# Рівно булеве $true; відсутній, $false, рядок — відмова. Повертає текст відмови або $null, якщо вхід погоджено.
function Test-PumbLoginGate {
    param($Cfg)
    $v = $null
    if ($Cfg -is [System.Collections.IDictionary] -and $Cfg.Contains('LoginApproved')) { $v = $Cfg['LoginApproved'] }
    if ($v -is [bool] -and $v) { return $null }
    'Вхід у банк не погоджено: у блоці Pumb конфігурації немає LoginApproved = $true. Цей ключ виставляє власник, коли відповів, що вхід рекордера (password grant) не заважає робочій інтеграції ПУМБ і що ліміт сесій це витримує (README, «Перед першим запуском»). До банку нічого не надіслано.'
}

# Єдина точка запиту до ПУМБ. Auth: тіло запиту в запис не потрапляє (bodyOmitted), відповідь замасковується, видані банком значення
# додаються до набору секретів; справжнє тіло автентифікації не друкується й не зберігається (повертається лише розібране в .AuthReal).
function Invoke-PumbApi {
    param($Ctx, [string]$Method, [string]$HostName, [int]$Port, [string]$Path, $BodyBytes = $null, [string]$Token = '',
        [switch]$Auth, [string]$DryStub = '[]', [switch]$NoRetry, [switch]$NoReauth)
    Assert-ReadOnlyRequest $Method $HostName $Path $Port
    $useCtxToken = (-not $Auth) -and (-not $Token)
    $retried429 = $false; $reauthed = $false
    $result = $null
    for ($try = 1; $try -le 3; $try++) {
        if ($useCtxToken) {
            if (-not $Ctx.Dry -and $Ctx.TokenExpiry -and [datetime]::UtcNow -gt $Ctx.TokenExpiry) { Update-PumbToken $Ctx 'строк дії токена добігає кінця' }
            $Token = [string]$Ctx.Token
        }
        Wait-Gap $Ctx
        $started = [datetime]::UtcNow
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $Ctx.Requests++
        $uri = "https://$HostName" + $(if ($Port -ne 443) { ":$Port" } else { '' }) + $Path
        if ($Auth) { $headers = @{ 'User-Agent' = $script:UserAgent }; $ct = 'application/x-www-form-urlencoded' }
        else {
            $headers = @{ 'User-Agent' = $script:UserAgent; 'Authorization' = "Bearer $Token"; 'X-App-Channel' = 'pure-api'; 'X-Flow-ID' = '5:6:EX' }
            $ct = 'application/json'
        }
        if ($Ctx.Dry) {
            Write-Host ("[план] {0} {1}{2}{3}" -f $Method, $HostName, $(if ($Port -ne 443) { ":$Port" } else { '' }), $Path)
            $r = [pscustomobject]@{ Status = 200; Headers = @(, @('content-type', 'application/json')); Body = $script:Utf8NoBom.GetBytes($DryStub); Failure = $null }
        }
        else { $r = Invoke-HttpSend $Method $uri $headers $ct $BodyBytes }
        $sw.Stop()
        $Ctx.LastEnd = [datetime]::UtcNow
        $Ctx.NextGap = $Ctx.MinIntervalSec
        $Ctx.Cur.Exchanges++
        if ($null -ne $r.Failure) { Add-Count $Ctx 'HTTP' ('збій:' + $r.Failure.Kind) } else { Add-Count $Ctx 'HTTP' ([string]$r.Status) }
        $authReal = $null
        if ($Auth -and $null -eq $r.Failure -and -not $Ctx.Dry) {
            $real = ConvertFrom-BodyBytes $r.Body $r.Headers
            if ($real -is [System.Collections.IDictionary]) { $authReal = $real }
            $prot = Protect-AuthResponse $r.Body $r.Headers $Ctx.Secrets
            $r = [pscustomobject]@{ Status = $r.Status; Headers = $r.Headers; Body = $prot.Body; Failure = $null }
        }
        if (-not $Ctx.Dry) {
            if ($Auth) {
                [void](Save-Exchange $Ctx.Rec $Ctx.Cur.Name $HostName $Path '' $r.Status $r.Headers $r.Body $r.Failure $started ([int]$sw.ElapsedMilliseconds) `
                        -Method $Method -Port $Port -BodyOmittedReason 'автентифікація: пароль і секрет клієнта в запис не потрапляють')
            }
            else {
                $reqBody = $null
                if ($Method -ceq 'POST') { $reqBody = [byte[]]$BodyBytes }
                [void](Save-Exchange $Ctx.Rec $Ctx.Cur.Name $HostName $Path '' $r.Status $r.Headers $r.Body $r.Failure $started ([int]$sw.ElapsedMilliseconds) `
                        -Method $Method -Port $Port -RequestBody $reqBody)
            }
            $line = if ($null -ne $r.Failure) { "збій мережі ($($r.Failure.Kind))" } elseif ($Auth) { "HTTP $($r.Status) (тіло автентифікації не друкується)" } else { "HTTP $($r.Status), $($r.Body.Length) байт" }
            Write-Host ("  [{0:D4}] {1} {2} -> {3}" -f $Ctx.Rec.Seq, $Method, $Path, $line)
        }
        $result = [pscustomobject]@{ Status = $r.Status; Headers = $r.Headers; Body = $r.Body; Failure = $r.Failure; AuthReal = $authReal }
        if ($r.Status -eq 429) {
            if ($NoRetry) { Add-Note $Ctx '429 на запит без повтору — записано, повтору немає'; break }
            $wait = Get-RetryWaitSeconds $r.Headers
            if (-not $retried429) { $retried429 = $true; Add-Note $Ctx "банк відповів 429 — чекаю $wait с і повторюю один раз"; $Ctx.NextGap = $wait; continue }
            throw 'SCENARIO_STOP: 429 повторно після паузи — сценарій зупинено, ліміт не провокується'
        }
        if ($r.Status -eq 401 -and $useCtxToken -and -not $NoReauth -and -not $reauthed -and -not $Ctx.Dry) {
            $reauthed = $true
            Update-PumbToken $Ctx 'банк відповів 401 на запит зі справжнім токеном'
            continue
        }
        break
    }
    $result
}

# Вхід (password grant). Справжній вхід — один, без повторних спроб: хибна спроба входу ризикує блокуванням облікового запису.
# -Fake: сценарій «свідомі помилки» — вигадані логін, пароль і секрет клієнта (справжній логін із хибним паролем не використовується).
function Invoke-PumbLogin {
    param($Ctx, $Cfg, [switch]$Fake)
    $esc = { param($v) [uri]::EscapeDataString([string]$v) }
    if ($Fake) { $login = $script:FakeLogin; $pw = $script:FakePassword; $sec = $script:FakeClientSecret }
    else { $login = [string]$Cfg.Login; $pw = [string]$Cfg.Password; $sec = [string]$Cfg.ClientSecret }
    $form = 'grant_type=password&client_id={0}&username={1}&password={2}&client_secret={3}' -f (& $esc $Cfg.ClientId), (& $esc $login), (& $esc $pw), (& $esc $sec)
    $bytes = $script:Utf8NoBom.GetBytes($form)
    $form = $null
    if ($Ctx.Dry) {
        Write-Host "[план] POST $($script:PumbAuthHost)$($script:PumbAuthPath) (тіло автентифікації не друкується)"
        $Ctx.Requests++; $Ctx.Cur.Exchanges++
        if (-not $Fake) { $Ctx.Token = 'DRYRUN-TOKEN' }
        return
    }
    $Ctx.Logins++
    $r = Invoke-PumbApi $Ctx 'POST' $script:PumbAuthHost 443 $script:PumbAuthPath $bytes -Auth -NoRetry
    $bytes = $null
    if ($Fake) { return }
    $tok = $null; $expires = 0
    if ($r.Status -eq 200 -and $r.AuthReal -is [System.Collections.IDictionary]) {
        $tok = [string]$r.AuthReal['access_token']
        [void][int]::TryParse([string]$r.AuthReal['expires_in'], [ref]$expires)
    }
    if (-not $tok) {
        $Ctx.Abort = "вхід не вдався (HTTP $($r.Status)); повторних спроб немає — хибна спроба входу ризикує блокуванням облікового запису"
        throw 'SCENARIO_STOP: вхід не вдався'
    }
    $Ctx.Token = $tok
    $Ctx.TokenExpiry = if ($expires -gt 0) { [datetime]::UtcNow.AddSeconds([math]::Max($expires - 30, 30)) } else { $null }
}

function Update-PumbToken {
    param($Ctx, [string]$Why)
    if ($Ctx.Reauths -ge 3) { throw 'SCENARIO_STOP: повторних входів у прогоні вже 3 — зупинено, щоб не навантажувати автентифікацію' }
    $Ctx.Reauths++
    Add-Note $Ctx "повторний вхід ($Why)"
    Invoke-PumbLogin $Ctx $Ctx.Cfg
}

# --- розбір відповідей для зведень (лише кількості; суми — власнику) -----------------------------
function Add-PumbItemsDigest {
    param($Ctx, $Items)
    $Ctx.Cur.Pages++
    $it = @($Items)
    Add-Count $Ctx 'розмір сторінки' ([string]$it.Count)
    foreach ($t in $it) {
        if ($t -isnot [System.Collections.IDictionary]) { continue }
        $Ctx.Cur.Ops++
        Add-Count $Ctx 'state' ([string]$t['state'])
        Add-Count $Ctx 'direction' ([string]$t['direction'])
        Add-Count $Ctx 'type' ([string]$t['type'])
        Add-Count $Ctx 'currencyCode' ([string]$t['currencyCode'])
        Add-IdValue $Ctx 'id' $t['id']
        Add-IdValue $Ctx 'docId' $t['docId']
        Add-Sum $Ctx ("{0} {1}" -f $t['direction'], $t['currencyCode']) (ConvertTo-DecimalSafe $t['amount'])
    }
}

function Format-PumbDate { param([datetime]$D, [string]$Fmt = 'dd.MM.yyyy HH:mm:ss') $D.ToString($Fmt, [System.Globalization.CultureInfo]::InvariantCulture) }

function ConvertFrom-PumbDate {
    param($Text)
    $d = [datetime]::MinValue
    $fmts = [string[]]@('dd.MM.yyyy HH:mm:ss', 'yyyy-MM-ddTHH:mm:ss', 'yyyy-MM-dd HH:mm:ss')
    if ([datetime]::TryParseExact([string]$Text, $fmts, [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::None, [ref]$d)) { return $d }
    $null
}

function New-PumbSearchBody {
    param([string]$AccountId, [string]$From, [string]$To, $States, $Types, $Paging)
    $b = [ordered]@{ fromDate = $From; toDate = $To }
    if ($null -ne $States) { $b['documentState'] = [string[]]@($States) }
    if ($null -ne $Types) { $b['documentType'] = [string[]]@($Types) }
    $b['documentAccounts'] = [string[]]@($AccountId)
    if ($null -ne $Paging) { $b['pagingRequest'] = $Paging }
    , $script:Utf8NoBom.GetBytes(($b | ConvertTo-Json -Depth 6 -Compress))
}

function Send-PumbSearch {
    param($Ctx, [byte[]]$Body)
    $r = Invoke-PumbApi $Ctx 'POST' $script:PumbApiHost $script:PumbApiPort "$($script:PumbApiPrefix)/document/searcher" $Body -DryStub '[]'
    $j = ConvertFrom-BodyBytes $r.Body $r.Headers
    $items = $null
    if ($j -is [array]) { $items = @($j) }
    [pscustomobject]@{ R = $r; Items = $items }
}

# Читає searcher. PageSize 0 — без pagingRequest. -Cursor: продовження за orderedLastId останньої операції сторінки; зупинка на порожній
# сторінці, неповній сторінці, курсорі, що не просувається, або MaxPages. Ознаку «є ще» рекордер не вигадує — лише записує відповіді.
function Read-PumbSearcher {
    param($Ctx, [string]$AccId, [string]$From, [string]$To, $States, $Types, [int]$PageSize, [int]$MaxPages, [switch]$Cursor)
    $last = $null; $prevFirst = $null; $pageNo = 0
    while ($true) {
        $paging = $null
        if ($PageSize -gt 0) { $paging = [ordered]@{ pageSize = $PageSize }; if ($null -ne $last) { $paging['orderedLastId'] = [long]$last['id'] } }
        $s = Send-PumbSearch $Ctx (New-PumbSearchBody $AccId $From $To $States $Types $paging)
        if ($null -eq $s.Items) { Add-Note $Ctx "відповідь не масив (HTTP $($s.R.Status)) — читання зупинено"; return }
        $items = @($s.Items)
        Add-PumbItemsDigest $Ctx $items
        $Ctx.Captured.Add([pscustomobject]@{ Items = $items; Limit = $PageSize })
        if ($items.Count -eq 0) { Add-Note $Ctx 'порожня сторінка — кінець'; return }
        if (-not $Cursor -or $PageSize -le 0) { return }
        if ($items.Count -lt $PageSize) { Add-Note $Ctx "неповна сторінка ($($items.Count) < $PageSize) — кінець"; return }
        $newLast = $items[$items.Count - 1]
        if ($newLast -isnot [System.Collections.IDictionary] -or $null -eq $newLast['id']) { Add-Note $Ctx 'в останній операції сторінки немає id — продовження неможливе'; return }
        $first = $items[0]
        if ($null -ne $prevFirst -and $first -is [System.Collections.IDictionary] -and [string]$first['id'] -ceq $prevFirst) { Add-Note $Ctx 'курсор не просувається (перша операція сторінки та сама) — зупинено'; return }
        $prevFirst = if ($first -is [System.Collections.IDictionary]) { [string]$first['id'] } else { $null }
        $pageNo++
        if ($pageNo -ge $MaxPages) { Add-Note $Ctx "досягнуто ліміту сторінок рекордера ($MaxPages)"; return }
        $last = $newLast
    }
}

function Invoke-PumbPeriodTx {
    param($Ctx, [string]$AccId, [string]$From, [string]$To)
    $body = $script:Utf8NoBom.GetBytes(([ordered]@{ accountId = [long]$AccId; dateFrom = $From; dateTo = $To } | ConvertTo-Json -Compress))
    $r = Invoke-PumbApi $Ctx 'POST' $script:PumbApiHost $script:PumbApiPort "$($script:PumbApiPrefix)/document/period-transactions" $body -DryStub '{"header":{},"transactions":[]}'
    $j = ConvertFrom-BodyBytes $r.Body $r.Headers
    if ($j -isnot [System.Collections.IDictionary]) { Add-Note $Ctx "відповідь не об'єкт (HTTP $($r.Status))"; return }
    $Ctx.Cur.Pages++
    $tx = @($j['transactions'])
    $Ctx.Cur.Ops += $tx.Count
    Add-Count $Ctx 'транзакцій у відповіді' ([string]$tx.Count)
    if ($j['header'] -is [System.Collections.IDictionary]) {
        Add-Note $Ctx ('поля header: ' + ((@($j['header'].Keys) | Sort-Object) -join ', '))
        foreach ($k in 'inSaldo', 'outSaldo') { if ($null -ne $j['header'][$k]) { Add-Sum $Ctx $k (ConvertTo-DecimalSafe $j['header'][$k]) } }
    }
    if ($tx.Count -gt 0 -and $tx[0] -is [System.Collections.IDictionary]) {
        Add-Note $Ctx ('поля транзакції: ' + ((@($tx[0].Keys) | Sort-Object) -join ', '))
        foreach ($t in $tx) { if ($t -is [System.Collections.IDictionary]) { Add-IdValue $Ctx 'transactionId' $t['transactionId'] } }
    }
}

# Операція, єдина у своїй секунді operationDate (серед усіх сторінок вибірки), лише зі сторінки, НЕ повної за її pageSize.
function Select-PumbBoundary {
    param($Pages)
    $count = @{}
    foreach ($pg in @($Pages)) {
        foreach ($op in @($pg.Items)) {
            if ($op -isnot [System.Collections.IDictionary]) { continue }
            $d = ConvertFrom-PumbDate $op['operationDate']
            if ($null -eq $d) { continue }
            $k = [long]($d.Ticks / 10000000)
            $count[$k] = 1 + [int]($count[$k] ?? 0)
        }
    }
    $cand = [System.Collections.Generic.HashSet[long]]::new()
    foreach ($pg in @($Pages)) {
        if ([int]$pg.Limit -gt 0 -and @($pg.Items).Count -ge [int]$pg.Limit) { continue }
        foreach ($op in @($pg.Items)) {
            if ($op -isnot [System.Collections.IDictionary]) { continue }
            $d = ConvertFrom-PumbDate $op['operationDate']
            if ($null -eq $d) { continue }
            $k = [long]($d.Ticks / 10000000)
            if ($count[$k] -eq 1) { [void]$cand.Add($k) }
        }
    }
    if ($cand.Count -eq 0) { return $null }
    $sorted = @($count.Keys | ForEach-Object { [long]$_ } | Sort-Object)
    $best = $null; $bestGap = [long]-1
    for ($i = 0; $i -lt $sorted.Count; $i++) {
        $t = [long]$sorted[$i]
        if (-not $cand.Contains($t)) { continue }
        $gap = [long]31536000
        if ($i -gt 0) { $gap = [math]::Min($gap, $t - [long]$sorted[$i - 1]) }
        if ($i -lt $sorted.Count - 1) { $gap = [math]::Min($gap, [long]$sorted[$i + 1] - $t) }
        if ($gap -gt $bestGap) { $best = $t; $bestGap = $gap }
    }
    [pscustomobject]@{ Time = [datetime]::new([long]$best * 10000000); Gap = $bestGap; Candidates = $cand.Count }
}

# Пари запитів на включність меж: fromDate = t і t - 1 (toDate — t + 1 год, не пізніше кінця періоду); toDate = t і t + 1
# (fromDate — t - 1 год, не раніше початку періоду). Кожен запит — окремий сценарій. Висновку про включність рекордер не робить.
function Invoke-PumbBoundaryPairs {
    param($Ctx, [string]$Prefix, [string]$AccId, $Pages, [datetime]$PeriodFrom, [datetime]$PeriodTo, [int]$PageSize)
    $cand = Select-PumbBoundary $Pages
    if ($null -eq $cand -and $Ctx.Dry) {
        Write-Host '[dry-run] у заглушках немає операцій — для плану запитів підставлено синтетичного кандидата'
        $cand = [pscustomobject]@{ Time = $PeriodFrom.AddDays(1); Gap = 0; Candidates = 0 }
    }
    if ($null -eq $cand) {
        Invoke-Scenario $Ctx "${Prefix}_boundary_candidate" { Add-Note $Ctx 'немає операції, єдиної у своїй секунді, на неповній сторінці вибірки; пар не робили (запитів немає)' }
        return
    }
    $t = [datetime]$cand.Time
    $toA = if ($t.AddHours(1) -lt $PeriodTo) { $t.AddHours(1) } else { $PeriodTo }
    $fromB = if ($t.AddHours(-1) -gt $PeriodFrom) { $t.AddHours(-1) } else { $PeriodFrom }
    $steps = @(
        @{ Tag = 'from_eq'; F = $t; T = $toA }
        @{ Tag = 'from_shift'; F = $t.AddSeconds(-1); T = $toA }
        @{ Tag = 'to_eq'; F = $fromB; T = $t }
        @{ Tag = 'to_shift'; F = $fromB; T = $t.AddSeconds(1) }
    )
    $first = $true
    foreach ($st in $steps) {
        $qf = Format-PumbDate $st.F; $qt = Format-PumbDate $st.T; $isFirst = $first; $first = $false
        Invoke-Scenario $Ctx "${Prefix}_boundary_$($st.Tag)" {
            if ($isFirst) { Add-Note $Ctx "кандидат обрано: придатних операцій $($cand.Candidates); секунд до найближчої іншої операції: $($cand.Gap)" }
            $paging = if ($PageSize -gt 0) { [ordered]@{ pageSize = $PageSize } } else { $null }
            $s = Send-PumbSearch $Ctx (New-PumbSearchBody $AccId $qf $qt 'PROCESSED' 'UAH' $paging)
            if ($null -ne $s.Items) { Add-PumbItemsDigest $Ctx @($s.Items) }
        }
    }
}

function Invoke-PumbRun {
    param($Cfg, $Ctx)
    foreach ($p in 'Token', 'TokenExpiry', 'Logins', 'Reauths', 'Cfg') { Add-Member -InputObject $Ctx -NotePropertyName $p -NotePropertyValue $null -Force }
    $Ctx.Logins = 0; $Ctx.Reauths = 0; $Ctx.Cfg = $Cfg
    $small = [int]($Cfg.SmallPageSize ?? 5); $work = [int]($Cfg.WorkPageSize ?? 100); $maxPages = [int]($Cfg.MaxPages ?? 60)
    $P = $Cfg.PeriodParsed
    $pFrom = Format-PumbDate $P.From; $pTo = Format-PumbDate $P.To.AddDays(1).AddSeconds(-1)
    $apiPath = { param($Op) "$($script:PumbApiPrefix)$Op" }

    # без входу немає нічого: решта сценаріїв потребує токена
    Invoke-Scenario $Ctx 'pumb_auth' { Invoke-PumbLogin $Ctx $Cfg }
    if (-not $Ctx.Token) { Write-Host '[увага] токен не отримано — решту сценаріїв пропущено'; if (-not $Ctx.Dry) { $Ctx.Failed = $true }; return }

    $script:pumbAcc = @{}
    $stub = '[{"accountId":1,"iban":"' + @($Cfg.Accounts)[0] + '","currency":"UAH"}]'
    Invoke-Scenario $Ctx 'pumb_account' {
        $r = Invoke-PumbApi $Ctx 'GET' $script:PumbApiHost $script:PumbApiPort (& $apiPath '/account') -DryStub $stub
        $j = ConvertFrom-BodyBytes $r.Body $r.Headers
        if ($j -isnot [array]) { Add-Note $Ctx "відповідь не масив (HTTP $($r.Status))"; return }
        $Ctx.Cur.Pages++
        Add-Count $Ctx 'рахунків у відповіді' ([string]@($j).Count)
        foreach ($a in $j) {
            if ($a -isnot [System.Collections.IDictionary]) { continue }
            $Ctx.Cur.Ops++
            Add-Count $Ctx 'currency' ([string]$a['currency'])
            if ($a['iban'] -and -not $script:pumbAcc.ContainsKey([string]$a['iban'])) { $script:pumbAcc[[string]$a['iban']] = @{ Id = [string]$a['accountId']; Currency = [string]$a['currency'] } }
        }
    }

    $n = 0
    $firstAccId = $null
    foreach ($iban in @($Cfg.Accounts)) {
        $n++
        $pre = "pumb_a$n"
        $acc = $script:pumbAcc[[string]$iban]
        if ($null -eq $acc -or -not $acc.Id) {
            Invoke-Scenario $Ctx "${pre}_missing" { Add-Note $Ctx 'рахунок із конфігурації не знайдено у відповіді /account — сценарії рахунку пропущено'; if (-not $Ctx.Dry) { $Ctx.Failed = $true } }
            continue
        }
        $accId = $acc.Id; $isUah = ($acc.Currency -ceq 'UAH')
        if ($null -eq $firstAccId) { $firstAccId = $accId }
        $workPages = $null

        if (Test-ScenarioOn $Cfg 'SearcherSmall') {
            Invoke-Scenario $Ctx "${pre}_searcher_small" { Read-PumbSearcher $Ctx $accId $pFrom $pTo 'PROCESSED' 'UAH' $small $maxPages -Cursor }
        }
        if (Test-ScenarioOn $Cfg 'SearcherWork') {
            Invoke-Scenario $Ctx "${pre}_searcher_work" { Read-PumbSearcher $Ctx $accId $pFrom $pTo 'PROCESSED' 'UAH' $work $maxPages -Cursor }
            $workPages = @($Ctx.Captured)
        }
        if (Test-ScenarioOn $Cfg 'SearcherNoPaging') {
            Invoke-Scenario $Ctx "${pre}_searcher_nopaging" { Read-PumbSearcher $Ctx $accId $pFrom $pTo 'PROCESSED' 'UAH' 0 1 }
        }
        if (Test-ScenarioOn $Cfg 'StatesAll') {
            # без фільтра станів: розподіл state і direction
            Invoke-Scenario $Ctx "${pre}_searcher_states_all" { Read-PumbSearcher $Ctx $accId $pFrom $pTo $null 'UAH' $work 1 }
        }
        if (Test-ScenarioOn $Cfg 'TypesNone') {
            Invoke-Scenario $Ctx "${pre}_searcher_types_none" { Read-PumbSearcher $Ctx $accId $pFrom $pTo 'PROCESSED' $null $work 1 }
        }
        if ((Test-ScenarioOn $Cfg 'TypesCurrency') -and -not $isUah) {
            Invoke-Scenario $Ctx "${pre}_searcher_types_cur" { Read-PumbSearcher $Ctx $accId $pFrom $pTo 'PROCESSED' 'CUR' $work 1 }
        }
        if (Test-ScenarioOn $Cfg 'PagingProbes') {
            # допустимі форми pagingRequest: перша сторінка, далі по одному запиту на форму (безпечні читальні запити)
            Invoke-Scenario $Ctx "${pre}_paging_probes" {
                $s = Send-PumbSearch $Ctx (New-PumbSearchBody $accId $pFrom $pTo 'PROCESSED' 'UAH' ([ordered]@{ pageSize = $small }))
                if ($null -eq $s.Items) { Add-Note $Ctx "відповідь не масив (HTTP $($s.R.Status))"; return }
                $items = @($s.Items); Add-PumbItemsDigest $Ctx $items
                if ($items.Count -eq 0) { Add-Note $Ctx 'порожня перша сторінка — проб немає'; return }
                $lastItem = $items[$items.Count - 1]
                $probes = [System.Collections.Generic.List[object]]::new()
                if ($lastItem -is [System.Collections.IDictionary] -and $null -ne $lastItem['id']) {
                    $probes.Add(@{ Tag = 'orderedLastId'; P = [ordered]@{ pageSize = $small; orderedLastId = [long]$lastItem['id'] } })
                    $probes.Add(@{ Tag = 'orderedLastId_sortField_id'; P = [ordered]@{ pageSize = $small; orderedLastId = [long]$lastItem['id']; sortField = 'id' } })
                    if ($lastItem['operationDate']) {
                        $probes.Add(@{ Tag = 'orderedLastId_orderedLastValue_operationDate'; P = [ordered]@{ pageSize = $small; orderedLastId = [long]$lastItem['id']; orderedLastValue = [string]$lastItem['operationDate']; sortField = 'operationDate' } })
                    }
                }
                foreach ($d in 0, 1, -1) { $probes.Add(@{ Tag = "direction_$d"; P = [ordered]@{ pageSize = $small; direction = $d } }) }
                $probes.Add(@{ Tag = 'pagingSessionId_probe'; P = [ordered]@{ pageSize = $small; pagingSessionId = 'recorder-probe-session' } })
                foreach ($pr in $probes) {
                    $s2 = Send-PumbSearch $Ctx (New-PumbSearchBody $accId $pFrom $pTo 'PROCESSED' 'UAH' $pr.P)
                    $cnt = if ($null -ne $s2.Items) { @($s2.Items).Count } else { -1 }
                    Add-Note $Ctx "проба $($pr.Tag): обмін $($Ctx.Rec.Seq), HTTP $($s2.R.Status), елементів $cnt"
                    if ($null -ne $s2.Items) { Add-PumbItemsDigest $Ctx @($s2.Items) }
                }
            }
        }
        if (Test-ScenarioOn $Cfg 'DateFormats') {
            # формат дат запиту: той, що знаємо (dd.MM.yyyy HH:mm:ss), іде в усіх сценаріях; тут — інші форми, по запиту на форму
            Invoke-Scenario $Ctx "${pre}_date_formats" {
                foreach ($f in @(@('dmy', 'dd.MM.yyyy'), @('iso', "yyyy-MM-dd'T'HH:mm:ss"), @('iso_date', 'yyyy-MM-dd'))) {
                    $s = Send-PumbSearch $Ctx (New-PumbSearchBody $accId (Format-PumbDate $P.From $f[1]) (Format-PumbDate $P.To $f[1]) 'PROCESSED' 'UAH' ([ordered]@{ pageSize = $small }))
                    Add-Note $Ctx "формат $($f[0]): обмін $($Ctx.Rec.Seq), HTTP $($s.R.Status)"
                    if ($null -ne $s.Items) { Add-PumbItemsDigest $Ctx @($s.Items) }
                }
            }
        }
        if (Test-ScenarioOn $Cfg 'PeriodTransactions') {
            # те саме, що searcher, іншою операцією — основа порівняння для Р4 (повнота, id, межі)
            Invoke-Scenario $Ctx "${pre}_period_tx_dmy" { Invoke-PumbPeriodTx $Ctx $accId $pFrom $pTo }
            Invoke-Scenario $Ctx "${pre}_period_tx_iso" { Invoke-PumbPeriodTx $Ctx $accId (Format-PumbDate $P.From "yyyy-MM-dd'T'HH:mm:ss") (Format-PumbDate $P.To.AddDays(1).AddSeconds(-1) "yyyy-MM-dd'T'HH:mm:ss") }
        }
        if ((Test-ScenarioOn $Cfg 'Saturated') -and $Cfg.SaturatedParsed) {
            $sp = $Cfg.SaturatedParsed
            Invoke-Scenario $Ctx "${pre}_searcher_saturated" {
                Read-PumbSearcher $Ctx $accId (Format-PumbDate $sp.From) (Format-PumbDate $sp.To.AddDays(1).AddSeconds(-1)) 'PROCESSED' 'UAH' $work ([int]($Cfg.MaxSaturatedPages ?? 40)) -Cursor
            }
            Invoke-Scenario $Ctx "${pre}_period_tx_saturated" { Invoke-PumbPeriodTx $Ctx $accId (Format-PumbDate $sp.From) (Format-PumbDate $sp.To.AddDays(1).AddSeconds(-1)) }
        }
        if ((Test-ScenarioOn $Cfg 'Reversal') -and $Cfg.ReversalParsed) {
            $rp = $Cfg.ReversalParsed
            Invoke-Scenario $Ctx "${pre}_searcher_reversal" {
                Read-PumbSearcher $Ctx $accId (Format-PumbDate $rp.From) (Format-PumbDate $rp.To.AddDays(1).AddSeconds(-1)) $null $null $work $maxPages -Cursor
            }
        }
        if (Test-ScenarioOn $Cfg 'BoundaryPairs' $false) {
            $pages = $workPages
            if ($null -eq $pages) {
                Invoke-Scenario $Ctx "${pre}_boundary_source" { Read-PumbSearcher $Ctx $accId $pFrom $pTo 'PROCESSED' 'UAH' $work 1 }
                $pages = @($Ctx.Captured)
            }
            Invoke-PumbBoundaryPairs $Ctx $pre $accId $pages $P.From $P.To.AddDays(1).AddSeconds(-1) $work
        }
    }

    if (Test-ScenarioOn $Cfg 'Errors') {
        $today = (ConvertFrom-UnixKyiv ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())).Date
        $eAcc = if ($firstAccId) { $firstAccId } else { $script:FakePumbAccountId }
        Invoke-Scenario $Ctx 'pumb_errors_invalid_token' {
            [void](Invoke-PumbApi $Ctx 'GET' $script:PumbApiHost $script:PumbApiPort (& $apiPath '/account') -Token $script:FakeToken -DryStub '{}' -NoReauth)
        }
        Invoke-Scenario $Ctx 'pumb_errors_invalid_credentials' { Invoke-PumbLogin $Ctx $Cfg -Fake }
        Invoke-Scenario $Ctx 'pumb_errors_from_after_to' {
            [void](Send-PumbSearch $Ctx (New-PumbSearchBody $eAcc $pTo $pFrom 'PROCESSED' 'UAH' ([ordered]@{ pageSize = $small })))
        }
        Invoke-Scenario $Ctx 'pumb_errors_future_period' {
            [void](Send-PumbSearch $Ctx (New-PumbSearchBody $eAcc (Format-PumbDate $today.AddDays(30)) (Format-PumbDate $today.AddDays(60)) 'PROCESSED' 'UAH' ([ordered]@{ pageSize = $small })))
        }
        Invoke-Scenario $Ctx 'pumb_errors_foreign_account' {
            [void](Send-PumbSearch $Ctx (New-PumbSearchBody $script:FakePumbAccountId $pFrom $pTo 'PROCESSED' 'UAH' ([ordered]@{ pageSize = $small })))
            Invoke-PumbPeriodTx $Ctx $script:FakePumbAccountId $pFrom $pTo
        }
        Invoke-Scenario $Ctx 'pumb_errors_body_not_json' {
            [void](Invoke-PumbApi $Ctx 'POST' $script:PumbApiHost $script:PumbApiPort (& $apiPath '/document/searcher') ([System.Text.Encoding]::UTF8.GetBytes('this is not json')) -DryStub '{}')
        }
    }
}

# =============================================================================================
# Зведення: для агента (лише кількості) і для власника (суми)
# =============================================================================================
function Write-AgentSummary {
    param($Ctx, [string]$Path, [string]$State)
    $L = [System.Collections.Generic.List[string]]::new()
    $L.Add("Зведення прогону для агента: лише кількості. Без сум, ідентифікаторів, IBAN, імен.")
    $L.Add("Рекордер $script:RecorderVersion, формат запису $($Ctx.Rec.MaxVersion), банк $($Ctx.BankKey), мітка прогону $($Ctx.Rec.RunLabel), стан: $State")
    $L.Add("Обмінів усього: $($Ctx.Rec.Seq)")
    foreach ($s in $Ctx.Stats.Values) {
        $L.Add('')
        $L.Add("--- $($s.Name)")
        $L.Add("обмінів: $($s.Exchanges); сторінок: $($s.Pages); операцій/елементів: $($s.Ops)")
        foreach ($g in $s.Counts.Keys) { $L.Add(("{0}: {1}" -f $g, (($s.Counts[$g].Keys | ForEach-Object { "$_=$($s.Counts[$g][$_])" }) -join ', '))) }
        foreach ($k in $s.IdSet.Keys) { $L.Add("унікальність $k`: унікальних $($s.IdSet[$k].Count) із $($s.IdTotal[$k])") }
        foreach ($n in $s.Notes) { $L.Add("примітка: $n") }
    }
    [System.IO.File]::WriteAllText($Path, ($L -join "`r`n") + "`r`n", $script:Utf8NoBom)
}

function Write-OwnerReconcile {
    param($Ctx, [string]$Path)
    $L = [System.Collections.Generic.List[string]]::new()
    $L.Add('ЗВІРКА З КАБІНЕТОМ — лише для власника. Містить суми й ідентифікатори. Не пересилати агентам.')
    $L.Add("Банк $($Ctx.BankKey), мітка прогону $($Ctx.Rec.RunLabel)")
    foreach ($s in $Ctx.Stats.Values) {
        if ($s.Sums.Count -eq 0) { continue }
        $L.Add('')
        $L.Add("--- $($s.Name): операцій $($s.Ops)")
        foreach ($k in $s.Sums.Keys) { $L.Add(("  {0}: {1:N2}" -f $k, $s.Sums[$k])) }
    }
    $L.Add('')
    $L.Add('--- рядки, що йшли в консоль під час прогону')
    foreach ($o in $Ctx.Owner) { $L.Add($o) }
    [System.IO.File]::WriteAllText($Path, ($L -join "`r`n") + "`r`n", $script:Utf8NoBom)
}

# =============================================================================================
# Перевірка наявної теки запису (і теки звірки) на значення секретів. Без мережі. Повертає код виходу: 0 чисто, 3 знайдено.
# Порожній набір секретів — виняток (Test-SecretsInFiles), а не «чисто».
function Invoke-SecretCheck {
    param([string]$RunDir, [string]$OwnerDir, $Secrets, [string]$BaseDir, [string[]]$ExtraFiles = @())
    if (-not (Test-Path -LiteralPath $RunDir -PathType Container)) { throw "Теки запису немає: $RunDir" }
    $files = @(Get-ChildItem -LiteralPath $RunDir -Recurse -File | ForEach-Object FullName)
    if ($OwnerDir -and (Test-Path -LiteralPath $OwnerDir -PathType Container)) { $files += @(Get-ChildItem -LiteralPath $OwnerDir -Recurse -File | ForEach-Object FullName) }
    # додаткові файли (перенаправлений stderr): файл, якого немає, — помилка, а не «чисто»
    foreach ($x in @($ExtraFiles | Where-Object { $_ })) {
        if (-not (Test-Path -LiteralPath $x -PathType Leaf)) { throw "Файлу для самоперевірки немає: $x" }
        $files += $x
    }
    $findings = Test-SecretsInFiles $files $Secrets $BaseDir
    if ($findings.Count -gt 0) {
        $lines = foreach ($f in $findings) { "файл: $($f.File); секрет: $($f.Secret); форма: $($f.Where), $($f.Form)" }
        Write-Host '!!!!!!!! ЗНАЙДЕНО значення токена в записаних файлах !!!!!!!!'
        $lines | ForEach-Object { Write-Host "  $_" }
        [System.IO.File]::WriteAllText((Join-Path $RunDir 'LEAK-DETECTED.txt'), "Самоперевірка знайшла значення токена у файлах (значень тут немає):`r`n" + ($lines -join "`r`n") + "`r`n", $script:Utf8NoBom)
        return 3
    }
    Write-Host ("Самоперевірка: токенів у {0} файлах не знайдено." -f $files.Count)
    0
}

# Які банки йдуть у прогін: 'all' — три банки зі старого переліку; ПУМБ (вхід у банк) — лише за явним -Bank pumb.
function Get-SelectedBanks {
    param([string[]]$Bank)
    if ($Bank -contains 'all') { return @('privat', 'monoCorp', 'monoFop') }
    @($Bank)
}

# Чи лежить $Inner усередині $Outer (або збігається з ним). Шляхи порівнюються без урахування регістру.
function Test-PathInside {
    param([string]$Inner, [string]$Outer)
    $i = [System.IO.Path]::GetFullPath($Inner).TrimEnd('\', '/')
    $o = [System.IO.Path]::GetFullPath($Outer).TrimEnd('\', '/')
    ($i -ieq $o) -or $i.StartsWith($o + '\', [StringComparison]::OrdinalIgnoreCase) -or $i.StartsWith($o + '/', [StringComparison]::OrdinalIgnoreCase)
}

# =============================================================================================
# Самотест пошуку секретів (без мережі, без справжніх токенів)
# =============================================================================================
function Invoke-SelfTestMode {
    param([string]$Dir)
    if (-not $Dir) { $Dir = Join-Path ([System.IO.Path]::GetTempPath()) ('api-recorder-selftest-' + [guid]::NewGuid().ToString('N').Substring(0, 8)) }
    $Dir = [System.IO.Path]::GetFullPath($Dir)
    New-Item -ItemType Directory -Path $Dir -Force | Out-Null
    $results = [System.Collections.Generic.List[object]]::new()
    $check = { param([string]$Name, [bool]$Ok, [string]$Detail = '') $results.Add([pscustomobject]@{ Name = $Name; Ok = $Ok; Detail = $Detail }); Write-Host ("  [{0}] {1} {2}" -f $(if ($Ok) { 'ПРОЙДЕНО' } else { 'ПРОВАЛЕНО' }), $Name, $Detail) }

    # Синтетичні помітні значення. A — ASCII зі спецсимволами (+ / =), B — кирилиця (щоб кодування різнились).
    $secrets = [ordered]@{ 'СИНТ.A' = 'SYNTH-Zq7+K2/mW4pL8vR1='; 'СИНТ.B' = 'СИНТ-ТОКЕН-Є7f3a9c1e' }
    $pos = Join-Path $Dir 'positive'; $neg = Join-Path $Dir 'clean'
    foreach ($d in $pos, $neg) { if (Test-Path $d) { Remove-Item $d -Recurse -Force }; New-Item -ItemType Directory -Path $d | Out-Null }
    Write-Host "Самотест: робоча тека $Dir"

    # --- позитивні файли: значення в кожному кодуванні, збудовані окремим кодом (не функціями пошуку) ---
    $expect = [System.Collections.Generic.List[object]]::new()   # @{File; Secret}
    $noiseL = [System.Text.Encoding]::UTF8.GetBytes('{"id":"x1","note":"prefix ')
    $noiseR = [System.Text.Encoding]::UTF8.GetBytes(' suffix","n":42}')
    $put = { param([string]$Case, [string]$Label, [byte[]]$Bytes) $f = Join-Path $pos ("$Case`__$Label.bin"); [System.IO.File]::WriteAllBytes($f, $Bytes); $expect.Add(@{ File = $f; Secret = $Label; Case = $Case }) }
    foreach ($label in $secrets.Keys) {
        $v = $secrets[$label]
        $wrap = { param([byte[]]$mid) [byte[]]($noiseL + $mid + $noiseR) }
        & $put 'utf8' $label (& $wrap ([System.Text.Encoding]::UTF8.GetBytes($v)))
        & $put 'utf16le' $label ([byte[]]([System.Text.Encoding]::Unicode.GetPreamble() + [System.Text.Encoding]::Unicode.GetBytes("note: $v end")))
        & $put 'utf16be' $label ([System.Text.Encoding]::BigEndianUnicode.GetBytes("note: $v end"))
        & $put 'cp1251' $label (& $wrap ([System.Text.Encoding]::GetEncoding(1251).GetBytes($v)))
        & $put 'cp866' $label (& $wrap ([System.Text.Encoding]::GetEncoding(866).GetBytes($v)))
        # Base64 усього тіла, значення зсунуте на 0/1/2 байти (різне вирівнювання)
        foreach ($shift in 0, 1, 2) {
            $body = [System.Text.Encoding]::UTF8.GetBytes(('x' * $shift) + $v + 'tail')
            & $put "base64_shift$shift" $label ([System.Text.Encoding]::ASCII.GetBytes([Convert]::ToBase64String($body)))
        }
        $b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes('p' + $v + 'q')).Replace('+', '-').Replace('/', '_').TrimEnd('=')
        & $put 'base64url' $label ([System.Text.Encoding]::ASCII.GetBytes($b64))
        $pctU = -join ([System.Text.Encoding]::UTF8.GetBytes($v) | ForEach-Object { '%' + $_.ToString('X2') })
        & $put 'percent_utf8_upper' $label ([System.Text.Encoding]::ASCII.GetBytes("q=$pctU&x=1"))
        & $put 'percent_utf8_lower' $label ([System.Text.Encoding]::ASCII.GetBytes('q=' + $pctU.ToLowerInvariant() + '&x=1'))
        $pctW = -join ([System.Text.Encoding]::GetEncoding(1251).GetBytes($v) | ForEach-Object { '%' + $_.ToString('X2') })
        & $put 'percent_cp1251' $label ([System.Text.Encoding]::ASCII.GetBytes("q=$pctW"))
        $escAll = -join ($v.ToCharArray() | ForEach-Object { '\u' + ([int]$_).ToString('x4') })
        & $put 'json_u_all_lower' $label ([System.Text.Encoding]::ASCII.GetBytes('{"t":"' + $escAll + '"}'))
        $escNon = -join ($v.ToCharArray() | ForEach-Object { if ([int]$_ -gt 127) { '\u' + ([int]$_).ToString('X4') } else { [string]$_ } })
        & $put 'json_u_nonascii_upper' $label ([System.Text.Encoding]::ASCII.GetBytes('{"t":"' + $escNon + '"}'))
        # \uXXXX усередині файлу в UTF-16LE
        & $put 'json_u_in_utf16' $label ([System.Text.Encoding]::Unicode.GetBytes('{"t":"' + $escNon + '"}'))
        $esc = $v.Replace('\', '\\').Replace('"', '\"').Replace('/', '\/')
        & $put 'json_escaped_slash' $label ([System.Text.Encoding]::UTF8.GetBytes('{"t":"' + $esc + '"}'))
    }

    # --- записи, зроблені справжнім записувачем: значення в тілі відповіді ---
    $recDir = Join-Path $pos 'rec'
    $rec = New-Recording $recDir 'selftest' 'x' $secrets
    $hdr = @(, @('Content-Type', 'application/json'))
    $bodies = @(
        @{ Case = 'exchange_body_utf8'; Label = 'СИНТ.A'; Body = [System.Text.Encoding]::UTF8.GetBytes('{"echo":"' + $secrets['СИНТ.A'].Replace('/', '\/') + '"}') }
        @{ Case = 'exchange_body_cp1251'; Label = 'СИНТ.B'; Body = [System.Text.Encoding]::GetEncoding(1251).GetBytes('{"echo":"' + $secrets['СИНТ.B'] + '"}') }
        @{ Case = 'exchange_body_uescaped'; Label = 'СИНТ.B'; Body = [System.Text.Encoding]::ASCII.GetBytes('{"echo":"' + (-join ($secrets['СИНТ.B'].ToCharArray() | ForEach-Object { if ([int]$_ -gt 127) { '\u' + ([int]$_).ToString('x4') } else { [string]$_ } })) + '"}') }
        @{ Case = 'exchange_body_odd_offset'; Label = 'СИНТ.A'; Body = [System.Text.Encoding]::UTF8.GetBytes('ab' + $secrets['СИНТ.A'] + 'cd') }
    )
    foreach ($b in $bodies) {
        $file = Save-Exchange $rec $b.Case 'acp.privatbank.ua' '/api/statements/settings' '' 200 $hdr $b.Body $null ([datetime]::UtcNow) 1
        $expect.Add(@{ File = (Join-Path $recDir $file); Secret = $b.Label; Case = $b.Case })
    }

    $found = Test-SecretsInFiles @(Get-ChildItem $pos -Recurse -File | ForEach-Object FullName) $secrets $pos
    foreach ($e in $expect) {
        $hit = @($found | Where-Object { $_.Secret -eq $e.Secret -and ((Join-Path $pos $_.File) -eq $e.File) })
        & $check "знайдено $($e.Secret) у «$($e.Case)»" ($hit.Count -gt 0) $(if ($hit.Count -gt 0) { '(форма: ' + $hit[0].Form + ')' } else { '— ПРОМАХ' })
    }
    # у тілі обмінів знахідка має бути саме «тіло відповіді» (перевірка розкодування Base64 тіла)
    foreach ($case in 'exchange_body_utf8', 'exchange_body_odd_offset') {
        $e = $expect | Where-Object { $_.Case -eq $case }
        $viaBody = @($found | Where-Object { $_.Secret -eq $e.Secret -and $_.Where -eq 'тіло відповіді' -and ((Join-Path $pos $_.File) -eq $e.File) })
        & $check "«$case»: знайдено через розкодоване тіло" ($viaBody.Count -gt 0)
    }

    # --- чисті файли: нуль знахідок ---
    $rng = [System.Random]::new(12345)
    $noise = [byte[]]::new(4096); $rng.NextBytes($noise)
    [System.IO.File]::WriteAllBytes((Join-Path $neg 'noise.bin'), $noise)
    [System.IO.File]::WriteAllText((Join-Path $neg 'noise-b64.txt'), [Convert]::ToBase64String($noise))
    [System.IO.File]::WriteAllText((Join-Path $neg 'bank-like.json'), '{"status":"SUCCESS","transactions":[{"SUM":"10.50","CCY":"UAH","OSND":"Оплата за товар № 5"}],"exist_next_page":false}', $script:Utf8NoBom)
    # двійники: значення з однією зміненою літерою — не збіг
    foreach ($label in $secrets.Keys) {
        $v = $secrets[$label]; $decoy = $v.Substring(0, $v.Length - 3) + 'ZZZ'
        [System.IO.File]::WriteAllText((Join-Path $neg "decoy_$label.txt"), "q=$decoy&t=$([uri]::EscapeDataString($decoy))", $script:Utf8NoBom)
    }
    # запис, у якому секрет намагається потрапити в заголовок відповіді й у текст збою: має бути відкинуто/замасковано
    $cleanRec = New-Recording (Join-Path $neg 'rec') 'selftest' 'x' $secrets
    $evil = @(@('Content-Type', 'application/json'), @('Set-Cookie', "s=$($secrets['СИНТ.A'])"), @('X-Echo-Token', $secrets['СИНТ.B']), @('X-RateLimit-Remaining', '5'), @('Retry-After', '7'))
    $f1 = Save-Exchange $cleanRec 'selftest' 'api.monobank.ua' '/personal/client-info' '' 429 $evil ([System.Text.Encoding]::UTF8.GetBytes('{"errorDescription":"Too many requests"}')) $null ([datetime]::UtcNow) 1
    $f2 = Save-Exchange $cleanRec 'selftest' 'api.monobank.ua' '/personal/client-info' '' $null @() ([byte[]]@()) ([pscustomobject]@{ Kind = 'network'; Text = "HttpRequestException: ... $($secrets['СИНТ.A']) ... $($secrets['СИНТ.B'])" }) ([datetime]::UtcNow) 1
    $txt1 = [System.IO.File]::ReadAllText((Join-Path $cleanRec.Dir $f1))
    & $check 'заголовки поза білим списком (set-cookie, x-echo-*) не потрапили в запис' (-not ($txt1 -match 'set-cookie|x-echo') -and ($txt1 -match 'retry-after') -and ($txt1 -match 'ratelimit'))
    $foundClean = Test-SecretsInFiles @(Get-ChildItem $neg -Recurse -File | ForEach-Object FullName) $secrets $neg
    & $check 'чисті файли, двійники, запис із відкинутими заголовками й замаскованим збоєм: нуль знахідок' ($foundClean.Count -eq 0) "(знахідок: $($foundClean.Count))"

    # --- контролі, що вміють впасти ---
    $wrong = [ordered]@{ 'ІНШЕ' = 'ЗОВСІМ-ІНШЕ-ЗНАЧЕННЯ-12345' }
    $foundWrong = Test-SecretsInFiles @(Get-ChildItem $pos -Recurse -File | ForEach-Object FullName) $wrong $pos
    & $check 'контроль: чужого значення в позитивних файлах немає (пошук залежить від значення)' ($foundWrong.Count -eq 0) "(знахідок: $($foundWrong.Count))"

    $thrown2 = { param([scriptblock]$B) try { & $B | Out-Null; $false } catch { $true } }
    # --- порожній набір секретів: самоперевірка мусить падати, а не проходити вакуумно ---
    & $check 'порожній набір секретів: самоперевірка падає' (& $thrown2 { Test-SecretsInFiles @((Get-ChildItem $neg -File | Select-Object -First 1).FullName) ([ordered]@{}) $neg })
    & $check 'набір із порожніх значень: самоперевірка падає' (& $thrown2 { Test-SecretsInFiles @((Get-ChildItem $neg -File | Select-Object -First 1).FullName) ([ordered]@{ A = '' }) $neg })

    # --- перевірка наявної теки (-CheckRun): знаходить підкинутий токен, на чистій — нуль ---
    $ckRun = Join-Path $Dir 'ck\rec\privat\r1'; $ckOwn = Join-Path $Dir 'ck\own\privat\r1'
    if (Test-Path (Join-Path $Dir 'ck')) { Remove-Item (Join-Path $Dir 'ck') -Recurse -Force }
    foreach ($d in $ckRun, $ckOwn) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
    [System.IO.File]::WriteAllText((Join-Path $ckRun 'a.json'), '{"x":"clean"}', $script:Utf8NoBom)
    [System.IO.File]::WriteAllText((Join-Path $ckOwn 'reconcile.txt'), 'суми 1,00', $script:Utf8NoBom)
    $code0 = Invoke-SecretCheck $ckRun $ckOwn $secrets (Join-Path $Dir 'ck')
    & $check 'перевірка наявної теки: чиста тека — код 0' ($code0 -eq 0)
    [System.IO.File]::WriteAllBytes((Join-Path $ckRun 'b.bin'), [System.Text.Encoding]::Unicode.GetBytes("x $($secrets['СИНТ.B']) y"))
    $code3 = Invoke-SecretCheck $ckRun $ckOwn $secrets (Join-Path $Dir 'ck')
    $leakTxt = if (Test-Path (Join-Path $ckRun 'LEAK-DETECTED.txt')) { [System.IO.File]::ReadAllText((Join-Path $ckRun 'LEAK-DETECTED.txt')) } else { '' }
    & $check 'перевірка наявної теки: підкинутий токен у теці запису — код 3, LEAK-DETECTED.txt без значення' (($code3 -eq 3) -and $leakTxt.Contains('b.bin') -and -not $leakTxt.Contains($secrets['СИНТ.B']))
    Remove-Item (Join-Path $ckRun 'b.bin'), (Join-Path $ckRun 'LEAK-DETECTED.txt') -Force
    [System.IO.File]::WriteAllText((Join-Path $ckOwn 'leak.txt'), "q=$($secrets['СИНТ.A'])", $script:Utf8NoBom)
    & $check 'перевірка наявної теки: токен у теці owner-only — код 3' ((Invoke-SecretCheck $ckRun $ckOwn $secrets (Join-Path $Dir 'ck')) -eq 3)
    & $check 'перевірка наявної теки: порожній набір секретів — помилка, не «чисто»' (& $thrown2 { Invoke-SecretCheck $ckRun $ckOwn ([ordered]@{}) (Join-Path $Dir 'ck') })
    & $check 'перевірка наявної теки: немає теки — помилка' (& $thrown2 { Invoke-SecretCheck (Join-Path $Dir 'ck\nope') $null $secrets $Dir })

    # --- OwnerRoot усередині OutRoot відхиляється ---
    & $check 'OwnerRoot усередині OutRoot розпізнається (вкладена тека, збіг, інший регістр)' ((Test-PathInside 'C:\x\rec\owner' 'C:\x\rec') -and (Test-PathInside 'C:\x\rec' 'C:\x\rec') -and (Test-PathInside 'c:\X\REC\a\b' 'C:\x\rec'))
    & $check 'OwnerRoot поза OutRoot не відхиляється (сусідня тека з тим самим префіксом)' (-not (Test-PathInside 'C:\x\rec-owner' 'C:\x\rec') -and -not (Test-PathInside 'C:\x\owner' 'C:\x\rec'))

    # --- білий список читання ---
    $thrown = { param([scriptblock]$B) try { & $B; $false } catch { $true } }
    & $check 'білий список: POST відхилено' (& $thrown { Assert-ReadOnlyRequest 'POST' 'acp.privatbank.ua' '/api/statements/transactions' })
    & $check 'білий список: платіжний шлях Привату відхилено' (& $thrown { Assert-ReadOnlyRequest 'GET' 'acp.privatbank.ua' '/api/proxy/payment/create' })
    & $check 'білий список: вебхук monobank відхилено' (& $thrown { Assert-ReadOnlyRequest 'GET' 'api.monobank.ua' '/personal/webhook' })
    & $check 'білий список: чужий хост відхилено' (& $thrown { Assert-ReadOnlyRequest 'GET' 'example.org' '/api/statements/settings' })
    $okPaths = @(@('acp.privatbank.ua', '/api/statements/transactions/interim'), @('corp-api.monobank.ua', '/ext/v1/statement/UA000/1/2'), @('api.monobank.ua', '/personal/statement/abc_D-1/1/2'), @('api.monobank.ua', '/personal/client-info'))
    $allOk = $true
    foreach ($p in $okPaths) { try { Assert-ReadOnlyRequest 'GET' $p[0] $p[1] } catch { $allOk = $false } }
    & $check 'білий список: дозволені шляхи читання проходять' $allOk

    # --- заглушки ---
    & $check 'заглушки розпізнаються' ((Test-Placeholder '<ВПИШІТЬ_ТОКЕН>') -and (Test-Placeholder '') -and (Test-Placeholder $null) -and -not (Test-Placeholder 'abc123'))

    # =============================================================================================
    # ПУМБ: білий список, формат v2, маскування автентифікації, ключ «вхід погоджено», самоперевірка витоку.
    # Усі значення тут ВИГАДАНІ (позначені FAKE/ВИГАДАНИЙ); мережі й справжніх токенів немає.
    # =============================================================================================
    Write-Host ''
    Write-Host 'ПУМБ (вигадані значення, без мережі):'
    $pf = '/war_veganet_api'
    $authPath = '/auth/realms/VegaNet/protocol/openid-connect/token'

    # --- білий список: дозволені операції проходять ---
    $okOps = @(
        @('POST', 'auth.fuib.com', $authPath, 443), @('GET', 'service.fuib.com', "$pf/account", 4103),
        @('POST', 'service.fuib.com', "$pf/document/searcher", 4103), @('POST', 'service.fuib.com', "$pf/document/period-transactions", 4103)
    )
    $allOk = $true
    foreach ($o in $okOps) { try { Assert-ReadOnlyRequest $o[0] $o[1] $o[2] $o[3] } catch { $allOk = $false } }
    & $check 'ПУМБ, білий список: форма на токен-ендпоінт, GET /account, searcher, period-transactions проходять' $allOk

    # --- контроль, що вміє впасти: платіжний метод ПУМБ мусить бути відхилений ---
    $payRejected = & $thrown { Assert-ReadOnlyRequest 'POST' 'service.fuib.com' "$pf/document/payment/order" 4103 }
    & $check 'ПУМБ, КОНТРОЛЬ: платіжний метод POST /document/payment/order відхилено (якщо пропущено — самотест падає)' $payRejected
    $badOps = @(
        @('POST', 'service.fuib.com', "$pf/document/currency/buy/order", 4103), @('POST', 'service.fuib.com', "$pf/document/currency/payment/order", 4103),
        @('POST', 'service.fuib.com', "$pf/document/limits/payment/order", 4103), @('POST', 'service.fuib.com', "$pf/document/payment/order/delete", 4103),
        @('PUT', 'service.fuib.com', "$pf/document/payment/order", 4103), @('GET', 'service.fuib.com', "$pf/document/payment/order/structure", 4103),
        @('POST', 'service.fuib.com', "$pf/document/payment/order/transfer-possibility", 4103), @('POST', 'auth.fuib.com', '/accounting/payment/order', 443),
        @('POST', 'service.fuib.com', "$pf/account/filtered", 4103), @('POST', 'service.fuib.com', "$pf/account/forecast/balance", 4103),
        @('GET', 'service.fuib.com', "$pf/document/body/1/2", 4103), @('GET', 'service.fuib.com', "$pf/document/searcher", 4103),
        @('POST', 'service.fuib.com', "$pf/account", 4103), @('DELETE', 'service.fuib.com', "$pf/account", 4103),
        @('POST', 'service.fuib.com', "$pf/document/searcher", 443), @('POST', 'auth.fuib.com', $authPath, 4103), @('POST', 'example.org', "$pf/document/searcher", 4103)
    )
    $badPassed = @($badOps | Where-Object { -not (& $thrown { Assert-ReadOnlyRequest $_[0] $_[1] $_[2] $_[3] }) })
    & $check 'ПУМБ, білий список: усі document/*/order, змінювальні, зайві методи, чужий порт і хост відхилено' ($badPassed.Count -eq 0) "(пропущено: $($badPassed.Count) із $($badOps.Count))"

    # --- ключ «вхід погоджено» ---
    $gateOpen = @{ LoginApproved = $true }
    & $check 'ПУМБ, ключ «вхід погоджено»: відсутній, $false, рядок «true», число 1 — відмова; лише булеве $true — дозвіл' (
        ($null -ne (Test-PumbLoginGate @{})) -and ($null -ne (Test-PumbLoginGate @{ LoginApproved = $false })) -and
        ($null -ne (Test-PumbLoginGate @{ LoginApproved = 'true' })) -and ($null -ne (Test-PumbLoginGate @{ LoginApproved = 1 })) -and ($null -eq (Test-PumbLoginGate $gateOpen)))
    & $check "'all' не включає ПУМБ (вхід у банк лише за явним -Bank pumb)" ((@(Get-SelectedBanks @('all')) -notcontains 'pumb') -and (@(Get-SelectedBanks @('pumb')) -contains 'pumb'))

    # --- запис ПУМБ у форматі v2, зроблений справжнім записувачем; значення вигадані ---
    $pSecrets = [ordered]@{ 'Pumb.ClientSecret' = 'ВИГАДАНИЙ-СЕКРЕТ-Zk3q9Lm2'; 'Pumb.Password' = 'ВИГАДАНИЙ-ПАРОЛЬ-Qw8r5Tn1' }
    $pDir = Join-Path $Dir 'pumb-sample'
    if (Test-Path $pDir) { Remove-Item $pDir -Recurse -Force }
    $pRec = New-Recording $pDir 'pumb' 'selftest' $pSecrets
    $fakeAccess = 'FAKEJWT-eyJhbGciOiJGQUtFIn0.eyJzdWIiOiJmYWtlLXVzZXIifQ.FAKE_signature-Zq7Lm'
    $fakeRefresh = 'FAKE-REFRESH-0123456789abcdefXYZ'
    $fakeSession = 'fake0000-aaaa-bbbb-cccc-111122223333'
    $authJson = '{"access_token":"' + $fakeAccess + '","expires_in":300,"refresh_expires_in":1800,"refresh_token":"' + $fakeRefresh + '","token_type":"Bearer","not-before-policy":0,"session_state":"' + $fakeSession + '","scope":"profile email"}'
    $jsonHdr = @(, @('content-type', 'application/json'))
    $prot = Protect-AuthResponse ([System.Text.Encoding]::UTF8.GetBytes($authJson)) $jsonHdr $pSecrets
    $maskedText = [System.Text.Encoding]::UTF8.GetString($prot.Body)
    $maskedObj = $maskedText | ConvertFrom-Json -AsHashtable
    $shape = { param([string]$t) [regex]::Replace($t, '[A-Za-z0-9]', 'x') }
    & $check 'ПУМБ, маскування автентифікації: видані значення відсутні в замаскованій відповіді, token_type/scope/числа лишились' (
        -not $maskedText.Contains($fakeAccess) -and -not $maskedText.Contains($fakeRefresh) -and -not $maskedText.Contains($fakeSession) -and
        ($maskedObj['token_type'] -ceq 'Bearer') -and ($maskedObj['scope'] -ceq 'profile email') -and ($maskedObj['expires_in'] -eq 300))
    & $check 'ПУМБ, маскування автентифікації: маркер тієї ж довжини й форми (крапки JWT на місці)' (
        ($maskedObj['access_token'].Length -eq $fakeAccess.Length) -and ($maskedObj['refresh_token'].Length -eq $fakeRefresh.Length) -and
        ((& $shape $maskedObj['access_token']) -ceq (& $shape $fakeAccess)) -and ($maskedObj['access_token'].Split('.').Count -eq 3))
    & $check 'ПУМБ, значення, видані банком у прогоні, додано до набору секретів (динамічно): 3 значення' (
        ($prot.Issued -eq 3) -and (@($pSecrets.Values) -contains $fakeAccess) -and (@($pSecrets.Values) -contains $fakeRefresh) -and (@($pSecrets.Values) -contains $fakeSession))
    $maskedErr = Protect-AuthResponse ([System.Text.Encoding]::UTF8.GetBytes('{"error":"invalid_grant","error_description":"Invalid user credentials"}')) $jsonHdr ([ordered]@{ A = 'не-збігається-1234' })
    & $check 'ПУМБ, маскування: форма помилки (error, error_description) лишається читабельною' ([System.Text.Encoding]::UTF8.GetString($maskedErr.Body).Contains('invalid_grant'))
    $maskedHtml = Protect-AuthResponse ([System.Text.Encoding]::UTF8.GetBytes('<html>Gateway 502 code 7713</html>')) @(, @('content-type', 'text/html')) ([ordered]@{ A = 'не-збігається-1234' })
    & $check 'ПУМБ, маскування: не-JSON відповідь автентифікації маскується цілком тієї ж довжини' ([System.Text.Encoding]::UTF8.GetString($maskedHtml.Body) -ceq '<aaaa>Aaaaaaa 999 aaaa 9999</aaaa>')

    $now = [datetime]::UtcNow
    $f1 = Save-Exchange $pRec 'pumb_auth' 'auth.fuib.com' $authPath '' 200 $jsonHdr $prot.Body $null $now 5 -Method 'POST' -Port 443 -BodyOmittedReason 'автентифікація: пароль і секрет клієнта в запис не потрапляють'
    $f2 = Save-Exchange $pRec 'pumb_account' 'service.fuib.com' "$pf/account" '' 200 $jsonHdr ([System.Text.Encoding]::UTF8.GetBytes('[{"accountId":1,"iban":"UA000000000000000000000000000","currency":"UAH"}]')) $null $now 5 -Method 'GET' -Port 4103
    $searchBody = New-PumbSearchBody '1' '01.01.2020 00:00:00' '03.01.2020 23:59:59' 'PROCESSED' 'UAH' ([ordered]@{ pageSize = 5 })
    $f3 = Save-Exchange $pRec 'pumb_a1_searcher_small' 'service.fuib.com' "$pf/document/searcher" '' 200 $jsonHdr ([System.Text.Encoding]::UTF8.GetBytes('[]')) $null $now 5 -Method 'POST' -Port 4103 -RequestBody $searchBody
    Save-Manifest $pRec 'ok'
    $j1 = Get-Content (Join-Path $pDir $f1) -Raw | ConvertFrom-Json -AsHashtable
    $j2 = Get-Content (Join-Path $pDir $f2) -Raw | ConvertFrom-Json -AsHashtable
    $j3 = Get-Content (Join-Path $pDir $f3) -Raw | ConvertFrom-Json -AsHashtable
    $jm = Get-Content (Join-Path $pDir 'recording.json') -Raw | ConvertFrom-Json -AsHashtable
    & $check 'ПУМБ, формат v2: автентифікація — метод POST, bodyOmitted + причина, порту немає (443), тіла запиту немає' (
        $j1.formatVersion -eq 2 -and $j1.request.method -ceq 'POST' -and $j1.request.bodyOmitted -eq $true -and $j1.request.bodyOmittedReason -and
        -not $j1.request.ContainsKey('port') -and -not $j1.request.ContainsKey('bodyBase64'))
    & $check 'ПУМБ, формат v2: GET /account на порту 4103 — request.port, без тіла' ($j2.formatVersion -eq 2 -and $j2.request.port -eq 4103 -and $j2.request.method -ceq 'GET' -and -not $j2.request.ContainsKey('bodyBase64'))
    $rawBody = [Convert]::FromBase64String($j3.request.bodyBase64)
    & $check 'ПУМБ, формат v2: тіло searcher — bodyBase64 + bodyLength як пішло; documentAccounts — масив' (
        $j3.formatVersion -eq 2 -and $j3.request.bodyLength -eq $rawBody.Length -and ([System.Text.Encoding]::UTF8.GetString($rawBody) -match '"documentAccounts":\["1"\]') -and ([System.Text.Encoding]::UTF8.GetString($rawBody) -match '"pageSize":5'))
    & $check 'ПУМБ, формат v2: версія маніфесту = найвища з версій обмінів (2)' ($jm.formatVersion -eq 2 -and $jm.exchanges.Count -eq 3)

    # запис лише з GET лишається версією 1, байти запиту — як у 5а
    $v1Rec = New-Recording (Join-Path $Dir 'v1-sample') 'selftest' 'x' $secrets
    $v1f = Save-Exchange $v1Rec 'selftest' 'api.monobank.ua' '/personal/client-info' '' 200 $jsonHdr ([System.Text.Encoding]::UTF8.GetBytes('{}')) $null $now 1
    Save-Manifest $v1Rec 'ok'
    $v1j = Get-Content (Join-Path $v1Rec.Dir $v1f) -Raw | ConvertFrom-Json -AsHashtable
    $v1m = Get-Content (Join-Path $v1Rec.Dir 'recording.json') -Raw | ConvertFrom-Json -AsHashtable
    & $check 'формат: запис лише з GET без тіла й порту лишається версією 1 (обмін і маніфест)' (
        $v1j.formatVersion -eq 1 -and $v1m.formatVersion -eq 1 -and -not $v1j.request.ContainsKey('port') -and -not $v1j.request.ContainsKey('bodyBase64') -and $v1j.request.method -ceq 'GET')
    & $check 'формат: POST без форми тіла запиту — відмова записувача (форма обов''язкова)' (& $thrown { Save-Exchange $v1Rec 'x' 'service.fuib.com' "$pf/document/searcher" '' 200 $jsonHdr ([byte[]]@()) $null $now 1 -Method 'POST' -Port 4103 })

    # --- самоперевірка витоку: у записі видані значення відсутні; підкладений вигаданий «токен» у консолі й stderr — код 3 ---
    $pOwn = Join-Path $Dir 'pumb-owner'
    New-Item -ItemType Directory -Path $pOwn -Force | Out-Null
    $leakFound = Test-SecretsInFiles @(Get-ChildItem $pDir -Recurse -File | ForEach-Object FullName) $pSecrets $pDir
    & $check 'ПУМБ, самоперевірка: у записі (з урахуванням виданих банком значень) знахідок немає' ($leakFound.Count -eq 0) "(знахідок: $($leakFound.Count))"
    $codeClean = Invoke-SecretCheck $pDir $pOwn $pSecrets $pDir
    & $check 'ПУМБ, самоперевірка: чиста тека — код 0' ($codeClean -eq 0)
    $consoleLog = Join-Path $pDir 'console.log'
    [System.IO.File]::WriteAllText($consoleLog, "[0002] POST $authPath -> HTTP 200`r`n  debug: access_token=$fakeAccess`r`n", $script:Utf8NoBom)
    $codeCon = Invoke-SecretCheck $pDir $pOwn $pSecrets $pDir
    & $check 'ПУМБ, КОНТРОЛЬ витоку: виданий банком токен у консольному журналі (console.log) — код 3, LEAK-DETECTED.txt без значення' (
        ($codeCon -eq 3) -and (Test-Path (Join-Path $pDir 'LEAK-DETECTED.txt')) -and -not ([System.IO.File]::ReadAllText((Join-Path $pDir 'LEAK-DETECTED.txt'))).Contains($fakeAccess))
    $configOnly = [ordered]@{ 'Pumb.ClientSecret' = $pSecrets['Pumb.ClientSecret']; 'Pumb.Password' = $pSecrets['Pumb.Password'] }
    Remove-Item (Join-Path $pDir 'LEAK-DETECTED.txt') -Force -ErrorAction SilentlyContinue
    $codeStatic = Invoke-SecretCheck $pDir $pOwn $configOnly $pDir
    & $check 'ПУМБ, КОНТРОЛЬ динамічності: без виданих значень у наборі той самий токен у консолі НЕ знаходиться (набір секретів — з прогону)' ($codeStatic -eq 0)
    Remove-Item $consoleLog -Force
    if (Test-Path (Join-Path $pDir 'LEAK-DETECTED.txt')) { Remove-Item (Join-Path $pDir 'LEAK-DETECTED.txt') -Force }
    $stderrFile = Join-Path $Dir 'pumb-stderr.log'
    [System.IO.File]::WriteAllText($stderrFile, "Error: boom $($pSecrets['Pumb.Password']) tail", $script:Utf8NoBom)
    $codeErr = Invoke-SecretCheck $pDir $pOwn $pSecrets $pDir @($stderrFile)
    & $check 'ПУМБ, КОНТРОЛЬ витоку: пароль у перенаправленому stderr — код 3' ($codeErr -eq 3)
    Remove-Item (Join-Path $pDir 'LEAK-DETECTED.txt') -Force -ErrorAction SilentlyContinue
    [System.IO.File]::WriteAllText($stderrFile, 'Error: boom, nothing secret', $script:Utf8NoBom)
    & $check 'ПУМБ, самоперевірка: чистий stderr — код 0' ((Invoke-SecretCheck $pDir $pOwn $pSecrets $pDir @($stderrFile)) -eq 0)
    & $check 'ПУМБ, самоперевірка: -StderrLog, якого немає, — помилка, не «чисто»' (& $thrown2 { Invoke-SecretCheck $pDir $pOwn $pSecrets $pDir @((Join-Path $Dir 'нема.log')) })

    # --- наскрізно через справжній скрипт (дочірній процес): без ключа — код 2 і жодного запису; dry-run без мережі; витік у stderr — код 3 ---
    $e2e = Join-Path $Dir 'e2e'
    if (Test-Path $e2e) { Remove-Item $e2e -Recurse -Force }
    New-Item -ItemType Directory -Path $e2e | Out-Null
    $fakeCfg = Join-Path $e2e 'config.psd1'
    $cfgText = @'
@{
    Pumb = @{
        Enabled = $true
        ClientId = 'SELFTEST-FAKE-CLIENT'
        ClientSecret = 'SELFTEST-FAKE-SECRET-0001'
        Login = 'selftest-fake-login'
        Password = 'SELFTEST-FAKE-PASSWORD-0002'
        Accounts = @('UA000000000000000000000000000')
        Period = @{ From = '2020-01-01'; To = '2020-01-03' }
    }
}
'@
    [System.IO.File]::WriteAllText($fakeCfg, $cfgText, $script:Utf8NoBom)
    $pwsh = (Get-Process -Id $PID).Path
    $outRoot = Join-Path $e2e 'rec'; $ownRoot = Join-Path $e2e 'own'
    # Захист від мережі: дочірні процеси йдуть через проксі на закритий локальний порт 9, тож навіть зламаний ключ «вхід погоджено»
    # не дасть запиту дійти до справжнього хоста (HttpClient у PowerShell 7 бере HTTPS_PROXY/HTTP_PROXY/ALL_PROXY, NO_PROXY порожній).
    $proxyVars = 'HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY', 'NO_PROXY', 'https_proxy', 'http_proxy', 'all_proxy', 'no_proxy'
    $savedEnv = @{}
    foreach ($v in $proxyVars) { $savedEnv[$v] = [Environment]::GetEnvironmentVariable($v) }
    foreach ($v in 'HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY', 'https_proxy', 'http_proxy', 'all_proxy') { [Environment]::SetEnvironmentVariable($v, 'http://127.0.0.1:9') }
    foreach ($v in 'NO_PROXY', 'no_proxy') { [Environment]::SetEnvironmentVariable($v, '') }
    try {
    # передумова захисту: дочірній процес із цим середовищем на недосяжному імені хоста дає відмову з'єднання з проксі (ConnectionRefused), а не помилку імені
    $guardProbe = (& $pwsh -NoProfile -Command '$h=[System.Net.Http.HttpClient]::new(); $h.Timeout=[TimeSpan]::FromSeconds(15); try { $h.GetAsync("https://selftest-guard.invalid/").GetAwaiter().GetResult()|Out-Null; "reached" } catch { $e=$_.Exception; while($e.InnerException){$e=$e.InnerException}; if ($e -is [System.Net.Sockets.SocketException]) { [string]$e.SocketErrorCode } else { $e.GetType().Name } }' 2>&1 | Out-String).Trim()
    & $check 'захист від мережі: дочірній процес іде через проксі 127.0.0.1:9 (відмова з''єднання з проксі, не помилка імені хоста)' ($guardProbe -ceq 'ConnectionRefused') "($guardProbe)"
    $o1 = & $pwsh -NoProfile -File $PSCommandPath -Bank pumb -Config $fakeCfg -OutRoot $outRoot -OwnerRoot $ownRoot -RunLabel e2e1 2>&1 | Out-String
    $c1 = $LASTEXITCODE
    & $check 'ПУМБ, без ключа «вхід погоджено» сценарій з автентифікацією — код 2, записів немає, у виводі немає значень облікових даних' (
        ($c1 -eq 2) -and $o1.Contains('Вхід у банк не погоджено') -and -not (Test-Path (Join-Path $outRoot 'pumb')) -and
        -not $o1.Contains('SELFTEST-FAKE-PASSWORD-0002') -and -not $o1.Contains('SELFTEST-FAKE-SECRET-0001')) "(код $c1)"
    $o2 = & $pwsh -NoProfile -File $PSCommandPath -Bank pumb -Config $fakeCfg -OutRoot $outRoot -OwnerRoot $ownRoot -RunLabel e2e2 -DryRun 2>&1 | Out-String
    $c2 = $LASTEXITCODE
    & $check 'ПУМБ, -DryRun: план запитів без мережі, код 0, нічого не записано, тіло автентифікації не друкується' (
        ($c2 -eq 0) -and $o2.Contains('[план] POST auth.fuib.com') -and $o2.Contains('[план] POST service.fuib.com:4103/war_veganet_api/document/searcher') -and
        -not $o2.Contains('SELFTEST-FAKE-PASSWORD-0002') -and -not $o2.Contains('grant_type') -and -not (Test-Path (Join-Path $outRoot 'pumb'))) "(код $c2)"
    $ckRunDir = Join-Path $outRoot 'pumb\e2e3'
    New-Item -ItemType Directory -Path $ckRunDir -Force | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $ckRunDir '0001.json'), '{"x":"clean"}', $script:Utf8NoBom)
    $stderrE2e = Join-Path $e2e 'stderr.log'
    [System.IO.File]::WriteAllText($stderrE2e, 'Error: SELFTEST-FAKE-PASSWORD-0002 echoed', $script:Utf8NoBom)
    $o3 = & $pwsh -NoProfile -File $PSCommandPath -CheckRun -Bank pumb -RunLabel e2e3 -Config $fakeCfg -OutRoot $outRoot -OwnerRoot $ownRoot -StderrLog $stderrE2e 2>&1 | Out-String
    $c3 = $LASTEXITCODE
    & $check 'ПУМБ, -CheckRun: підкладене значення секрету в перенаправленому stderr — код 3 (через справжній скрипт)' ($c3 -eq 3 -and -not $o3.Contains('SELFTEST-FAKE-PASSWORD-0002')) "(код $c3)"
    Remove-Item (Join-Path $ckRunDir 'LEAK-DETECTED.txt') -Force -ErrorAction SilentlyContinue
    [System.IO.File]::WriteAllText($stderrE2e, 'Error: nothing', $script:Utf8NoBom)
    $o4 = & $pwsh -NoProfile -File $PSCommandPath -CheckRun -Bank pumb -RunLabel e2e3 -Config $fakeCfg -OutRoot $outRoot -OwnerRoot $ownRoot -StderrLog $stderrE2e 2>&1 | Out-String
    $c4 = $LASTEXITCODE
    & $check 'ПУМБ, -CheckRun: чистий stderr і чиста тека — код 0' ($c4 -eq 0) "(код $c4)"
    }
    finally { foreach ($v in $proxyVars) { [Environment]::SetEnvironmentVariable($v, $savedEnv[$v]) } }

    $failed = @($results | Where-Object { -not $_.Ok }).Count
    Write-Host ''
    Write-Host ("САМОТЕСТ: перевірок {0}, успішних {1}, провалених {2}" -f $results.Count, ($results.Count - $failed), $failed)
    if ($failed -gt 0) { return 1 }
    0
}

# =============================================================================================
# Головний потік
# =============================================================================================
if ($SelfTest) { exit (Invoke-SelfTestMode $SelfTestDir) }

$bankMap = [ordered]@{
    privat   = @{ Key = 'Privat'; Dir = 'privat'; Host = 'acp.privatbank.ua'; Gap = 1.2; Run = ${function:Invoke-PrivatRun} }
    monoCorp = @{ Key = 'MonoCorp'; Dir = 'mono-corp'; Host = 'corp-api.monobank.ua'; Gap = 1.5; Run = ${function:Invoke-MonoCorpRun} }
    monoFop  = @{ Key = 'MonoFop'; Dir = 'mono-fop'; Host = 'api.monobank.ua'; Gap = 61.0; Run = ${function:Invoke-MonoFopRun} }
    pumb     = @{ Key = 'Pumb'; Dir = 'pumb'; Host = 'service.fuib.com'; Gap = 1.0; Run = ${function:Invoke-PumbRun} }
}
if (Test-PathInside $OwnerRoot $OutRoot) {
    Write-Host "ВІДМОВА: -OwnerRoot ($OwnerRoot) лежить усередині -OutRoot ($OutRoot): файли із сумами потрапили б у теку, яку читає агент."
    Write-Host 'Вкажіть -OwnerRoot поза текою записів (за замовчуванням temp/api-recorder/owner-only).'
    exit 2
}
$selected = Get-SelectedBanks $Bank

if (-not (Test-Path -LiteralPath $Config)) {
    if ($DryRun) { $fallback = Join-Path $PSScriptRoot 'config.template.psd1'; Write-Host "[dry-run] конфігурації немає ($Config); беру шаблон $fallback"; $Config = $fallback }
    else { Write-Host "Конфігурації немає: $Config"; Write-Host 'Скопіюйте config.template.psd1 у це місце й впишіть значення (див. README.md).'; exit 2 }
}
$raw = Import-PowerShellDataFile -LiteralPath $Config

# усі значення секретів із конфігурації (для самоперевірки й маскування тексту збоїв)
$allSecrets = [ordered]@{}
foreach ($pair in @(@('Privat', 'Token'), @('Privat', 'ClientId'), @('MonoCorp', 'Token'), @('MonoFop', 'Token'), @('Pumb', 'ClientId'), @('Pumb', 'ClientSecret'), @('Pumb', 'Login'), @('Pumb', 'Password'))) {
    $v = if ($raw[$pair[0]] -is [System.Collections.IDictionary]) { $raw[$pair[0]][$pair[1]] } else { $null }
    if (-not (Test-Placeholder $v)) { $allSecrets["$($pair[0]).$($pair[1])"] = [string]$v }
}

if ($CheckRun) {
    if (-not $PSBoundParameters.ContainsKey('RunLabel')) { Write-Host 'ВІДМОВА: для -CheckRun вкажіть -RunLabel <мітка прогону> (і -Bank, якщо не всі банки).'; exit 2 }
    if ($allSecrets.Count -eq 0) { Write-Host "ВІДМОВА: у конфігурації ($Config) немає жодного заповненого токена — перевіряти нічого. Порожній набір секретів не є доказом, що чисто."; exit 2 }
    $ckExit = 0; $found = 0
    foreach ($b in $selected) {
        $m = $bankMap[$b]
        $dir = Join-Path $OutRoot (Join-Path $m.Dir $RunLabel)
        if (-not (Test-Path -LiteralPath $dir -PathType Container)) { if ($Bank -notcontains 'all') { Write-Host "Теки запису немає: $dir"; $ckExit = 2 }; continue }
        $found++
        Write-Host "Перевіряю $dir"
        $c = Invoke-SecretCheck $dir (Join-Path $OwnerRoot (Join-Path $m.Dir $RunLabel)) $allSecrets $OutRoot @($StderrLog)
        if ($c -eq 3) { $ckExit = 3 } elseif ($c -ne 0 -and $ckExit -ne 3) { $ckExit = $c }
    }
    if ($found -eq 0 -and $ckExit -eq 0) { Write-Host "Жодної теки запису з міткою $RunLabel у $OutRoot не знайдено."; $ckExit = 2 }
    exit $ckExit
}

$exit = 0; $refused = $false; $leak = $false; $failedAny = $false
$totalPlanned = 0.0
foreach ($b in $selected) {
    $m = $bankMap[$b]
    $rawBank = $raw[$m.Key]
    Write-Host ''
    Write-Host "################ $($m.Key) ################"
    if ($null -eq $rawBank -or ($rawBank.ContainsKey('Enabled') -and -not $rawBank.Enabled)) { Write-Host 'Вимкнено в конфігурації (Enabled = $false) — пропускаю.'; continue }
    $res = Resolve-BankConfig $m.Key $rawBank ([bool]$DryRun)
    foreach ($n in $res.Notes) { Write-Host "[dry-run] $n" }
    if ($res.Problems.Count -gt 0) {
        Write-Host "ВІДМОВА: банк $($m.Key) не запускаю."
        foreach ($p in $res.Problems) { Write-Host "  - $p" }
        Write-Host "  Впишіть значення в $Config або вимкніть банк (Enabled = `$false)."
        $refused = $true
        continue
    }
    $cfg = $res.Cfg
    if ($m.Key -eq 'Pumb' -and -not $DryRun) {
        # ключ «вхід погоджено»: без нього жодного входу в банк (dry-run мережі не має, тож його не потребує)
        $gateMsg = Test-PumbLoginGate $cfg
        if ($gateMsg) { Write-Host "ВІДМОВА: $gateMsg"; $refused = $true; continue }
    }
    $runDir = Join-Path $OutRoot (Join-Path $m.Dir $RunLabel)
    if (-not $DryRun -and (Test-Path -LiteralPath $runDir)) { Write-Host "ВІДМОВА: тека $runDir вже існує. Задайте нову мітку прогону: -RunLabel <мітка>."; $refused = $true; continue }

    $bankSecrets = $allSecrets
    $rec = New-Recording $runDir $m.Dir $RunLabel $bankSecrets
    $ctx = New-Ctx $m.Dir $m.Host $m.Gap $rec $bankSecrets ([bool]$DryRun)
    if ($DryRun) { Write-Host "[dry-run] мережі немає, запису немає; пауза між запитами $($m.Gap) с; відповіді-заглушки порожні, тож сторінок буде менше, ніж у справжньому прогоні." }
    if ($DryRun) {
        try { & $m.Run $cfg $ctx } catch { Write-Host ('ПОМИЛКА: ' + (Remove-SecretValues ([string]$_.Exception.Message) $bankSecrets)); $failedAny = $true }
        Write-Host ("[dry-run] {0}: запитів у плані {1}, сумарні паузи ≈ {2:N1} хв" -f $m.Key, $ctx.Requests, ($ctx.PlannedSeconds / 60))
        $totalPlanned += $ctx.PlannedSeconds
        continue
    }
    # Справжній прогін: самоперевірка й позначка стану виконуються ЗАВЖДИ (finally), зокрема після Ctrl+C чи винятку.
    $state = 'interrupted'
    $transcribing = $false
    if ($m.Key -eq 'Pumb') {
        # консольний журнал прогону ПУМБ ведеться у файл теки запису (console.log): самоперевірка шукає секрети й у ньому
        try {
            New-Item -ItemType Directory -Path $runDir -Force | Out-Null
            Start-Transcript -Path (Join-Path $runDir 'console.log') -UseMinimalHeader | Out-Null
            $transcribing = $true
        }
        catch { Write-Host 'ВІДМОВА: консольний журнал вести неможливо — без нього самоперевірка неповна, до банку нічого не надіслано.'; $refused = $true; continue }
    }
    $ownerFile = Join-Path $OwnerRoot (Join-Path $m.Dir (Join-Path $RunLabel 'reconcile.txt'))
    try {
        & $m.Run $cfg $ctx
        $state = 'ok'
        if ($ctx.Failed) { $state = 'incomplete'; $failedAny = $true }
        if ($ctx.Abort) { $state = 'aborted'; Write-Host "Банк зупинено: $($ctx.Abort)" }
    }
    catch {
        $state = 'error'; $failedAny = $true
        Write-Host ('ПОМИЛКА: ' + (Remove-SecretValues ([string]$_.Exception.Message) $bankSecrets))
    }
    finally {
        if ($transcribing) { try { Stop-Transcript | Out-Null } catch { } }
        if ($state -eq 'interrupted') { $failedAny = $true; Write-Host 'Прогін перервано — виконую самоперевірку на те, що встигло записатись.' }
        try {
            New-Item -ItemType Directory -Path $runDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Split-Path $ownerFile) -Force | Out-Null
            Write-AgentSummary $ctx (Join-Path $runDir 'summary-agent.txt') $state
            Write-OwnerReconcile $ctx $ownerFile
            Save-Manifest $rec $state
            $files = @(Get-ChildItem -LiteralPath $runDir -Recurse -File | ForEach-Object FullName) + @($ownerFile) + @($StderrLog | Where-Object { $_ })
            $findings = Test-SecretsInFiles $files $bankSecrets $OutRoot
            if ($findings.Count -gt 0) {
                $leak = $true
                Write-Host ''
                Write-Host '!!!!!!!! САМОПЕРЕВІРКА ПРОВАЛЕНА: значення токена знайдено в записаних файлах !!!!!!!!'
                $lines = foreach ($f in $findings) { "файл: $($f.File); секрет: $($f.Secret); форма: $($f.Where), $($f.Form)" }
                $lines | ForEach-Object { Write-Host "  $_" }
                [System.IO.File]::WriteAllText((Join-Path $runDir 'LEAK-DETECTED.txt'), "Самоперевірка знайшла значення токена у файлах (значень тут немає):`r`n" + ($lines -join "`r`n") + "`r`n", $script:Utf8NoBom)
                Save-Manifest $rec 'leak-detected' 'самоперевірка знайшла токен у записі; теку нікому не передавати'
                Write-Host '  Теку НЕ передавайте нікому. Токен у банку краще перевипустити. Повідомте планувальника (без значення токена).'
            }
            else { Write-Host ("Самоперевірка: токенів у {0} файлах не знайдено." -f $files.Count) }
        }
        catch {
            # самоперевірку виконати не вдалося — це не «чисто»: прогін вважається проваленим
            $leak = $true
            Write-Host ('САМОПЕРЕВІРКА НЕ ВИКОНАНА: ' + (Remove-SecretValues ([string]$_.Exception.Message) $bankSecrets))
            Write-Host '  Теку НЕ передавайте нікому, доки самоперевірка не пройде.'
        }
        Write-Host "Запис: $runDir"
        Write-Host "Зведення для агента: $(Join-Path $runDir 'summary-agent.txt')"
        Write-Host "Звірка з кабінетом (лише власнику, суми й ідентифікатори; поза текою записів): $ownerFile"
    }
}

if ($DryRun) { Write-Host ''; Write-Host ("[dry-run] загалом сумарні паузи ≈ {0:N1} хв (без часу самих запитів). Нічого не записано, мережі не було." -f ($totalPlanned / 60)) }
if ($leak) { $exit = 3 } elseif ($failedAny) { $exit = 1 } elseif ($refused) { $exit = 2 }
exit $exit
