# Спільні функції рекордера: білі списки, запис обмінів, пошук секретів. Підключається з Invoke-ApiRecorder.ps1.
# Принцип: рекордер НІКОЛИ не отримує заголовків запиту в функції запису — токен у запис потрапити не може структурно.

$script:RecorderVersion = '1.0'
$script:FormatVersion = 1
$script:Cp1251 = [System.Text.Encoding]::GetEncoding(1251)
$script:Cp866 = [System.Text.Encoding]::GetEncoding(866)
$script:Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$script:Utf8Strict = [System.Text.UTF8Encoding]::new($false, $true)
$script:Latin1 = [System.Text.Encoding]::Latin1

# --- білі списки: лише читання -----------------------------------------------------------------
# Метод лише GET: жоден із трьох API не вимагає POST для читання виписок (документація банків).
$script:AllowedHosts = @('acp.privatbank.ua', 'corp-api.monobank.ua', 'api.monobank.ua')
$script:AllowedReadPaths = @(
    # ПриватБанк, «Автоклієнт»: розділ «Отримання балансів і транзакцій за рахунками»
    '^acp\.privatbank\.ua GET /api/statements/settings$'
    '^acp\.privatbank\.ua GET /api/statements/(balance|transactions)(/interim|/final)?$'
    # monobank юросіб, corp-api: специфікація v1.0.2
    '^corp-api\.monobank\.ua GET /ext/v1/accounts$'
    '^corp-api\.monobank\.ua GET /ext/v1/accounts/[A-Za-z0-9]+/balances$'
    '^corp-api\.monobank\.ua GET /ext/v1/statement/[A-Za-z0-9]+/-?\d+/-?\d+$'
    # monobank ФОП, персональне API v250818
    '^api\.monobank\.ua GET /personal/client-info$'
    '^api\.monobank\.ua GET /personal/statement/[A-Za-z0-9_-]+/-?\d+/-?\d+$'
)

function Assert-ReadOnlyRequest {
    param([string]$Method, [string]$HostName, [string]$Path)
    if ($Method -cne 'GET') { throw "Рекордер лише читає: метод $Method заборонено." }
    $key = "$HostName $Method $Path"
    foreach ($re in $script:AllowedReadPaths) { if ($key -cmatch $re) { return } }
    throw "Шлях не входить до білого списку читання: $HostName $Path"
}

# Заголовки відповіді, які потрапляють у запис (білий список). Решта відкидається.
function Select-AllowedHeaders {
    param($Pairs)
    $out = [System.Collections.Generic.List[object]]::new()
    foreach ($p in $Pairs) {
        $n = ([string]$p[0]).ToLowerInvariant()
        if ($n -in @('content-type', 'retry-after', 'date') -or $n -match '^(x-)?rate-?limit' -or $n -match '^x-rate-limit') {
            $out.Add(@($n, [string]$p[1]))
        }
    }
    $out.ToArray()
}

# --- допоміжне ----------------------------------------------------------------------------------
function Test-Placeholder {
    param($Value)
    if ($null -eq $Value) { return $true }
    $s = [string]$Value
    if ([string]::IsNullOrWhiteSpace($s)) { return $true }
    return ($s.Trim() -match '^<.*>$')
}

function Remove-SecretValues {
    param([string]$Text, $Secrets)
    if ($null -eq $Text) { return $Text }
    foreach ($k in $Secrets.Keys) {
        $v = [string]$Secrets[$k]
        if ($v.Length -ge 4) { $Text = $Text.Replace($v, "<$k>") }
    }
    $Text
}

function Format-Mask {
    param([string]$Text)
    $t = [regex]::Replace($Text, 'UA\d{23}(\d{4})', 'UA…$1')
    $t = [regex]::Replace($t, '(acc=)\d{10}(\d{4})', '$1…$2')
    $t = [regex]::Replace($t, '(acc=)[^&]{10,}(\w{4})(&|$)', '$1…$2$3')
    $t
}

# --- київська доба -----------------------------------------------------------------------------
$script:Tz = try { [TimeZoneInfo]::FindSystemTimeZoneById('FLE Standard Time') } catch { [TimeZoneInfo]::FindSystemTimeZoneById('Europe/Kyiv') }
$script:Epoch = [datetime]::new(1970, 1, 1, 0, 0, 0, [DateTimeKind]::Utc)
function ConvertTo-UnixKyiv {
    param([datetime]$Local)
    $utc = [TimeZoneInfo]::ConvertTimeToUtc([datetime]::SpecifyKind($Local, [DateTimeKind]::Unspecified), $script:Tz)
    [long]($utc - $script:Epoch).TotalSeconds
}
function ConvertFrom-UnixKyiv {
    param($Seconds)
    [TimeZoneInfo]::ConvertTimeFromUtc($script:Epoch.AddSeconds([long]$Seconds), $script:Tz)
}

# --- розбір тіла (лише для зведень; у запис іде як байти) ---------------------------------------
function ConvertFrom-BodyBytes {
    param([byte[]]$Bytes, $Headers)
    if ($null -eq $Bytes -or $Bytes.Length -eq 0) { return $null }
    $charset = ''
    foreach ($h in $Headers) { if ($h[0] -eq 'content-type' -and $h[1] -match 'charset=([\w-]+)') { $charset = $Matches[1].ToLowerInvariant() } }
    $text = $null
    if ($charset -in @('cp1251', 'windows-1251')) { $text = $script:Cp1251.GetString($Bytes) }
    else {
        try { $text = $script:Utf8Strict.GetString($Bytes) } catch { $text = $script:Cp1251.GetString($Bytes) }
    }
    $text = $text.TrimStart([char]0xFEFF)
    try { $parsed = $text | ConvertFrom-Json -AsHashtable -NoEnumerate -DateKind String; return , $parsed } catch { return $null }
}

# --- запис обмінів -----------------------------------------------------------------------------
function New-Recording {
    param([string]$Dir, [string]$Bank, [string]$RunLabel, $Secrets)
    [pscustomobject]@{
        Dir = $Dir; Bank = $Bank; RunLabel = $RunLabel; Seq = 0; Secrets = $Secrets
        StartedUtc = [datetime]::UtcNow; Index = [System.Collections.Generic.List[object]]::new()
    }
}

# Заголовків запиту тут немає взагалі — параметра для них не існує.
function Save-Exchange {
    param(
        $Rec, [string]$Scenario, [string]$HostName, [string]$Path, [string]$Query,
        $Status, $ResponseHeaders, [byte[]]$Body, $Failure, [datetime]$StartedUtc, [int]$DurationMs
    )
    $Rec.Seq++
    $file = '{0:D4}.json' -f $Rec.Seq
    $failObj = $null
    if ($null -ne $Failure) {
        $failObj = [ordered]@{ kind = [string]$Failure.Kind; text = (Remove-SecretValues ([string]$Failure.Text) $Rec.Secrets) }
    }
    $respObj = $null
    if ($null -eq $Failure) {
        $respObj = [ordered]@{
            status     = [int]$Status
            headers    = @(Select-AllowedHeaders $ResponseHeaders | ForEach-Object { , @($_[0], $_[1]) })
            bodyLength = $Body.Length
            bodyBase64 = [Convert]::ToBase64String($Body)
        }
    }
    $doc = [ordered]@{
        format = 'smp-api-exchange'; formatVersion = $script:FormatVersion
        seq = $Rec.Seq; scenario = $Scenario
        startedUtc = $StartedUtc.ToString('yyyy-MM-ddTHH:mm:ss.fffZ'); durationMs = $DurationMs
        request = [ordered]@{ method = 'GET'; host = $HostName; path = $Path; query = $Query }
        response = $respObj
        failure = $failObj
    }
    New-Item -ItemType Directory -Path $Rec.Dir -Force | Out-Null
    $json = $doc | ConvertTo-Json -Depth 6
    [System.IO.File]::WriteAllText((Join-Path $Rec.Dir $file), $json, $script:Utf8NoBom)
    $Rec.Index.Add([ordered]@{
            seq = $Rec.Seq; file = $file; scenario = $Scenario
            status = $(if ($null -eq $Failure) { [int]$Status } else { $null })
            failure = $(if ($null -eq $Failure) { $null } else { [string]$Failure.Kind })
        })
    $file
}

function Save-Manifest {
    param($Rec, [string]$State, [string]$Note = '')
    $doc = [ordered]@{
        format = 'smp-api-recording'; formatVersion = $script:FormatVersion
        recorderVersion = $script:RecorderVersion
        bank = $Rec.Bank; runLabel = $Rec.RunLabel
        startedUtc = $Rec.StartedUtc.ToString('yyyy-MM-ddTHH:mm:ssZ')
        finishedUtc = [datetime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
        state = $State; note = $Note
        exchanges = @($Rec.Index)
    }
    New-Item -ItemType Directory -Path $Rec.Dir -Force | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $Rec.Dir 'recording.json'), ($doc | ConvertTo-Json -Depth 6), $script:Utf8NoBom)
}

# --- пошук секретів у всіх кодуваннях ----------------------------------------------------------
function Get-Base64Needles {
    param([byte[]]$Bytes)
    $res = [System.Collections.Generic.List[string]]::new()
    for ($s = 0; $s -le 2; $s++) {
        $padded = [byte[]]::new($s + $Bytes.Length)
        [Array]::Copy($Bytes, 0, $padded, $s, $Bytes.Length)
        $enc = [Convert]::ToBase64String($padded).TrimEnd('=')
        $start = if (($s * 8) % 6 -eq 0) { [int]($s * 8 / 6) } else { [int][math]::Floor($s * 8 / 6) + 1 }
        $rem = ($s + $Bytes.Length) % 3
        $drop = switch ($rem) { 1 { 2 } 2 { 1 } default { 0 } }
        $len = $enc.Length - $start - $drop
        if ($len -ge 4) {
            $n = $enc.Substring($start, $len)
            $res.Add($n)
            $res.Add($n.Replace('+', '-').Replace('/', '_'))
        }
    }
    $res
}

function ConvertTo-PercentBytes {
    param([byte[]]$Bytes, [bool]$Upper)
    $sb = [System.Text.StringBuilder]::new()
    foreach ($b in $Bytes) {
        $c = [char]$b
        if (($c -ge 'a' -and $c -le 'z') -or ($c -ge 'A' -and $c -le 'Z') -or ($c -ge '0' -and $c -le '9') -or $c -in '-', '.', '_', '~') { [void]$sb.Append($c) }
        else { [void]$sb.Append('%').Append($(if ($Upper) { $b.ToString('X2') } else { $b.ToString('x2') })) }
    }
    $sb.ToString()
}

function Get-SecretNeedles {
    param([string]$Value)
    $list = [System.Collections.Generic.List[object]]::new()
    $seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $add = {
        param([string]$Form, [string]$Text)
        if ($Text.Length -ge 4 -and $seen.Add($Text)) { $list.Add([pscustomobject]@{ Form = $Form; Text = $Text }) }
    }
    $encs = [ordered]@{
        'UTF-8' = $script:Utf8NoBom; 'UTF-16LE' = [System.Text.UnicodeEncoding]::new($false, $false)
        'UTF-16BE' = [System.Text.UnicodeEncoding]::new($true, $false); 'cp1251' = $script:Cp1251; 'cp866' = $script:Cp866
    }
    foreach ($name in $encs.Keys) {
        $e = $encs[$name]
        $bytes = $e.GetBytes($Value)
        if ($e.GetString($bytes) -cne $Value) { continue }   # символи, яких кодування не вміє, — форми немає
        & $add $name $script:Latin1.GetString($bytes)
        foreach ($b64 in (Get-Base64Needles $bytes)) { & $add "Base64($name)" $b64 }
        if ($name -in 'UTF-8', 'cp1251') {
            & $add "URL($name)" (ConvertTo-PercentBytes $bytes $true)
            & $add "URL($name,нижній регістр)" (ConvertTo-PercentBytes $bytes $false)
        }
    }
    # \uXXXX: лише не-ASCII та всі символи; обидва регістри hex
    foreach ($case in 'x4', 'X4') {
        $nonAscii = -join ($Value.ToCharArray() | ForEach-Object { if ([int]$_ -gt 127) { '\u' + ([int]$_).ToString($case) } else { [string]$_ } })
        $all = -join ($Value.ToCharArray() | ForEach-Object { '\u' + ([int]$_).ToString($case) })
        & $add '\uXXXX(лише не-ASCII)' $nonAscii
        & $add '\uXXXX(усі символи)' $all
    }
    & $add 'JSON-екранування' ($Value.Replace('\', '\\').Replace('"', '\"').Replace('/', '\/'))
    , $list.ToArray()
}

function Find-SecretForms {
    # Повертає назви форм, у яких значення знайдено в байтах. Саме значення не повертається.
    param([byte[]]$Bytes, [string]$Value, $Needles)
    $hits = [System.Collections.Generic.List[string]]::new()
    if ($Bytes.Length -eq 0) { return , @() }
    $latin = $script:Latin1.GetString($Bytes)
    foreach ($n in $Needles) { if ($latin.IndexOf($n.Text, [StringComparison]::Ordinal) -ge 0) { $hits.Add($n.Form) } }
    # відсоткове кодування, розкодоване в байти (UTF-8 і cp1251 однаково): шукаємо всі форми в розкодованому
    if ($latin.Contains('%')) {
        $dec = [regex]::Replace($latin, '%([0-9a-fA-F]{2})', { param($m) [string][char][Convert]::ToInt32($m.Groups[1].Value, 16) })
        foreach ($n in $Needles) { if ($dec.IndexOf($n.Text, [StringComparison]::Ordinal) -ge 0) { $hits.Add("URL розкодований у байти ($($n.Form))") } }
    }
    # розкодований текст: \uXXXX і сире значення в чотирьох кодуваннях
    $views = [ordered]@{ 'UTF-8' = $script:Utf8NoBom; 'cp1251' = $script:Cp1251; 'UTF-16LE' = [System.Text.Encoding]::Unicode; 'UTF-16BE' = [System.Text.Encoding]::BigEndianUnicode }
    foreach ($vn in $views.Keys) {
        $t = $views[$vn].GetString($Bytes)
        if ($t.Contains('\u') -or $t.Contains('\U')) {
            $u = [regex]::Replace($t, '\\[uU]([0-9a-fA-F]{4})', { param($m) [string][char][Convert]::ToInt32($m.Groups[1].Value, 16) })
            if ($u.IndexOf($Value, [StringComparison]::Ordinal) -ge 0) { $hits.Add("\uXXXX розкодований (через $vn)") }
        }
        if ($t.IndexOf($Value, [StringComparison]::Ordinal) -ge 0) { $hits.Add("текст ($vn)") }
        if ($t.Contains('%')) {
            try {
                $d = [uri]::UnescapeDataString($t)
                if ($d.IndexOf($Value, [StringComparison]::Ordinal) -ge 0) { $hits.Add("URL розкодований (через $vn)") }
            } catch { }
        }
    }
    , $hits.ToArray()
}

# Скануємо кожен файл теки: сирі байти та (для обмінів) розкодоване тіло. Повертає знахідки: файл, мітка секрету, форма, де.
function Test-SecretsInFiles {
    param([string[]]$Files, $Secrets, [string]$BaseDir)
    $findings = [System.Collections.Generic.List[object]]::new()
    $needleSets = @{}
    foreach ($k in $Secrets.Keys) { if (-not [string]::IsNullOrEmpty([string]$Secrets[$k])) { $needleSets[$k] = Get-SecretNeedles ([string]$Secrets[$k]) } }
    foreach ($f in $Files) {
        $bytes = [System.IO.File]::ReadAllBytes($f)
        $rel = if ($BaseDir -and $f.StartsWith($BaseDir)) { $f.Substring($BaseDir.Length).TrimStart('\', '/') } else { $f }
        $targets = [System.Collections.Generic.List[object]]::new()
        $targets.Add(@{ Where = 'файл'; Bytes = $bytes })
        if ($f -like '*.json') {
            $txt = $script:Latin1.GetString($bytes)
            foreach ($m in [regex]::Matches($txt, '"bodyBase64"\s*:\s*"([A-Za-z0-9+/=]*)"')) {
                try { $targets.Add(@{ Where = 'тіло відповіді'; Bytes = [Convert]::FromBase64String($m.Groups[1].Value) }) } catch { }
            }
        }
        foreach ($k in $needleSets.Keys) {
            foreach ($t in $targets) {
                foreach ($form in (Find-SecretForms $t.Bytes ([string]$Secrets[$k]) $needleSets[$k])) {
                    $findings.Add([pscustomobject]@{ File = $rel; Secret = $k; Form = $form; Where = $t.Where })
                }
            }
        }
    }
    , $findings.ToArray()
}
