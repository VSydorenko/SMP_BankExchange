#Requires -Version 7.5
<#
.SYNOPSIS
  Рекордер відповідей API ПриватБанку («Автоклієнт»), monobank юросіб (corp-api) і monobank ФОП (персональне API).
.DESCRIPTION
  Лише читання в банку: тільки GET, шляхи — з білого списку (ApiRecorder.Lib.ps1). Відповіді зберігаються як
  упорядкована послідовність обмінів (FORMAT.md): тіло — байтами, заголовка запиту з токеном у записі немає.
  Після прогону рекордер сам шукає значення кожного токена в кожному записаному файлі в усіх кодуваннях.
  Режими: звичайний; -DryRun (план запитів без мережі); -SelfTest (перевірка самого пошуку секретів, без мережі).
  Запускає власник. Див. README.md.
#>
[CmdletBinding()]
param(
    # Справжня конфігурація — лише в temp основного дерева (гітігнорована), поза git.
    [string]$Config = 'R:/github/SMP_BankExchange/temp/api-recorder/config.psd1',
    [ValidateSet('all', 'privat', 'monoCorp', 'monoFop')][string[]]$Bank = 'all',
    # Мітка прогону = назва теки запису. Другий прогін — та сама команда з новою міткою.
    [string]$RunLabel = (Get-Date -Format 'yyyyMMdd-HHmmss'),
    [string]$OutRoot = 'R:/github/SMP_BankExchange/temp/api-recordings',
    # Файли звірки із сумами — ПОЗА текою записів (її читає агент), поруч із конфігурацією.
    [string]$OwnerRoot = 'R:/github/SMP_BankExchange/temp/api-recorder/owner-only',
    [switch]$DryRun,
    [switch]$SelfTest,
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
# HTTP (лише GET, тіло байтами, без автоперенаправлень)
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

function Invoke-HttpGet {
    param([string]$Uri, [hashtable]$Headers, [string]$ContentType)
    $client = Get-HttpClient
    $req = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Get, $Uri)
    foreach ($k in $Headers.Keys) { [void]$req.Headers.TryAddWithoutValidation($k, [string]$Headers[$k]) }
    if ($ContentType) {
        $req.Content = [System.Net.Http.ByteArrayContent]::new([byte[]]@())
        [void]$req.Content.Headers.TryAddWithoutValidation('Content-Type', $ContentType)
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
    $label = @{ Privat = 'Privat'; MonoCorp = 'MonoCorp'; MonoFop = 'MonoFop' }[$Key]

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
    if ($Key -eq 'MonoFop') { $c.SaturatedParsed = & $parsePeriod 'SaturatedPeriod' $Raw.SaturatedPeriod $false '' '' }
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
        if ($Key -eq 'transactions') { Add-PrivatTxDigest $Ctx $j $Key }
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
        if (Test-ScenarioOn $Cfg 'TxWorkLimit') {
            Invoke-Scenario $Ctx "privat_${tag}_tx_work_limit" { Read-PrivatPages $Ctx $tx @("acc=$acc14", "startDate=$from", "endDate=$to", "limit=$work") 'transactions' $maxPages }
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
# monobank юросіб (corp-api)
# =============================================================================================
function Read-MonoCorpStatement {
    param($Ctx, [string]$Iban, [long]$FromUnix, [long]$ToUnix, [int]$Limit, [int]$MaxPages, [string]$Extra = '')
    $upper = $ToUnix
    while ($true) {
        $r = Invoke-Api $Ctx "/ext/v1/statement/$Iban/$FromUnix/$upper" (Join-Query @("limit=$Limit", $Extra)) -DryStub '[]'
        if ($null -ne $r.Failure -or $r.Status -ne 200) { Add-Note $Ctx 'сторінка не отримана (збій або не 200) — читання зупинено'; return }
        $j = ConvertFrom-BodyBytes $r.Body $r.Headers
        if ($j -isnot [array]) { Add-Note $Ctx 'тіло не JSON-масив — читання зупинено'; return }
        $page = @($j)
        Add-MonoTxDigest $Ctx $page $false
        if ($page.Count -lt $Limit) { return }
        $earliest = ($page | ForEach-Object { [long]$_['time'] } | Measure-Object -Minimum).Minimum
        if ($earliest -le $FromUnix) { Add-Note $Ctx 'повна сторінка дійшла до початку періоду'; return }
        if ($earliest -ge $upper) { Add-Note $Ctx 'верхня межа не зменшилась (багато операцій в одну секунду) — читання зупинено'; return }
        if ($Ctx.Cur.Pages -ge $MaxPages) { Add-Note $Ctx "досягнуто ліміту сторінок рекордера ($MaxPages)"; return }
        $upper = $earliest
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
        if (Test-ScenarioOn $Cfg 'StatementLimit500') {
            Invoke-Scenario $Ctx "corp_${tag}_statement_limit500" { Read-MonoCorpStatement $Ctx $iban $fromU $toU 500 $maxPages }
        }
        if (Test-ScenarioOn $Cfg 'StatementSmallLimit') {
            Invoke-Scenario $Ctx "corp_${tag}_statement_small_limit" { Read-MonoCorpStatement $Ctx $iban $fromU $toU $small $maxSmall }
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
function Read-FopSegment {
    param($Ctx, [string]$AccId, [long]$FromUnix, [long]$ToUnix, [bool]$UntilEmpty, [int]$ContinueAtLeast, [int]$MaxPages)
    $upper = $ToUnix; $pages = 0
    while ($true) {
        $r = Invoke-Api $Ctx "/personal/statement/$AccId/$FromUnix/$upper" '' -DryStub '[]'
        $pages++
        if ($null -ne $r.Failure -or $r.Status -ne 200) { Add-Note $Ctx 'сторінка не отримана (збій або не 200) — відрізок зупинено'; return }
        $j = ConvertFrom-BodyBytes $r.Body $r.Headers
        if ($j -isnot [array]) { Add-Note $Ctx 'тіло не JSON-масив — відрізок зупинено'; return }
        $page = @($j)
        Add-MonoTxDigest $Ctx $page $true
        if ($page.Count -eq 0) { return }
        if (-not $UntilEmpty -and $page.Count -lt $ContinueAtLeast) { return }
        $earliest = ($page | ForEach-Object { [long]$_['time'] } | Measure-Object -Minimum).Minimum
        if ($earliest -le $FromUnix) { return }
        if ($earliest -ge $upper) { Add-Note $Ctx 'верхня межа не зменшилась — відрізок зупинено'; return }
        if ($pages -ge $MaxPages) { Add-Note $Ctx "досягнуто ліміту сторінок на відрізок ($MaxPages)"; return }
        $upper = $earliest
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
    if (-not $accId -and ((Test-ScenarioOn $Cfg 'StatementSegments') -or (Test-ScenarioOn $Cfg 'Saturated') -or ((Test-ScenarioOn $Cfg 'Reversal') -and $Cfg.ReversalParsed))) {
        if (-not $accId) {
            Invoke-Scenario $Ctx 'fop_client_info' {
                $r = Invoke-Api $Ctx '/personal/client-info' '' -DryStub $stubInfo
                $script:fopAcc = Get-FopAccountId $Ctx $Cfg $r
            }
            $accId = $script:fopAcc
        }
    }
    if (-not $accId) { Write-Host '[увага] ідентифікатор рахунку ФОП не отримано — сценарії виписок пропущено'; if (-not $Ctx.Dry) { $Ctx.Failed = $true }; return }

    if (Test-ScenarioOn $Cfg 'StatementSegments') {
        $segs = Get-FopSegments $P.From $P.To
        $n = 0
        foreach ($sg in $segs) {
            $n++
            Invoke-Scenario $Ctx ("fop_statement_segment_{0:D2}" -f $n) { Read-FopSegment $Ctx $accId $sg.From $sg.To $false $cont $maxPages }
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
# Зведення: для агента (лише кількості) і для власника (суми)
# =============================================================================================
function Write-AgentSummary {
    param($Ctx, [string]$Path, [string]$State)
    $L = [System.Collections.Generic.List[string]]::new()
    $L.Add("Зведення прогону для агента: лише кількості. Без сум, ідентифікаторів, IBAN, імен.")
    $L.Add("Рекордер $script:RecorderVersion, формат запису $script:FormatVersion, банк $($Ctx.BankKey), мітка прогону $($Ctx.Rec.RunLabel), стан: $State")
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
}
$selected = if ($Bank -contains 'all') { @($bankMap.Keys) } else { @($Bank) }

if (-not (Test-Path -LiteralPath $Config)) {
    if ($DryRun) { $fallback = Join-Path $PSScriptRoot 'config.template.psd1'; Write-Host "[dry-run] конфігурації немає ($Config); беру шаблон $fallback"; $Config = $fallback }
    else { Write-Host "Конфігурації немає: $Config"; Write-Host 'Скопіюйте config.template.psd1 у це місце й впишіть значення (див. README.md).'; exit 2 }
}
$raw = Import-PowerShellDataFile -LiteralPath $Config

# усі значення секретів із конфігурації (для самоперевірки й маскування тексту збоїв)
$allSecrets = [ordered]@{}
foreach ($pair in @(@('Privat', 'Token'), @('Privat', 'ClientId'), @('MonoCorp', 'Token'), @('MonoFop', 'Token'))) {
    $v = $raw[$pair[0]][$pair[1]]
    if (-not (Test-Placeholder $v)) { $allSecrets["$($pair[0]).$($pair[1])"] = [string]$v }
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
        if ($state -eq 'interrupted') { $failedAny = $true; Write-Host 'Прогін перервано — виконую самоперевірку на те, що встигло записатись.' }
        try {
            New-Item -ItemType Directory -Path $runDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Split-Path $ownerFile) -Force | Out-Null
            Write-AgentSummary $ctx (Join-Path $runDir 'summary-agent.txt') $state
            Write-OwnerReconcile $ctx $ownerFile
            Save-Manifest $rec $state
            $files = @(Get-ChildItem -LiteralPath $runDir -Recurse -File | ForEach-Object FullName) + @($ownerFile)
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
