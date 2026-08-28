#Requires -Version 7
Set-StrictMode -Version Latest

Import-Module "$PSScriptRoot/V8.psm1" -Force

$script:LabelMap = @{
    'Версия:'              = 'Version'
    'Пользователь:'        = 'User'
    'Дата создания:'       = 'Date'
    'Время создания:'      = 'Time'
    'Версия конфигурации:' = 'ConfigVersion'
    'Комментарий:'         = 'Comment'
}

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

    , $cells.ToArray()
}

function Read-StorageReport {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)

    $cells = Get-MxlStringCells -Lines (ConvertFrom-MxlText -Path $Path)
    $result = [System.Collections.Generic.List[object]]::new()
    $current = $null
    $pending = $null

    foreach ($cell in $cells) {
        if ($script:LabelMap.ContainsKey($cell)) {
            if ($cell -eq 'Версия:') {
                if ($current) { $result.Add($current) }
                $current = [ordered]@{
                    Version = 0; User = ''; Date = ''; Time = ''
                    ConfigVersion = ''; Comment = ''
                }
            }
            $pending = $script:LabelMap[$cell]
            continue
        }

        if ($pending -and $current) {
            if ($pending -eq 'Version') {
                $current['Version'] = [int]$cell
            } else {
                $current[$pending] = $cell
            }
            $pending = $null
        }
    }
    if ($current) { $result.Add($current) }

    , @($result |
        ForEach-Object {
            $stamp = [datetime]::MinValue
            if ($_.Date -and $_.Time) {
                $stamp = [datetime]::ParseExact(
                    "$($_.Date) $($_.Time)", 'dd.MM.yyyy HH:mm:ss',
                    [cultureinfo]::InvariantCulture)
            }
            [pscustomobject]@{
                Version       = $_.Version
                User          = $_.User
                Date          = $_.Date
                Time          = $_.Time
                ConfigVersion = $_.ConfigVersion
                Comment       = $_.Comment
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

    $result = Invoke-V8Designer -IbSwitch $IbSwitch -Arguments @(
        '/ConfigurationRepositoryF "{0}"' -f $StoragePath
        '/ConfigurationRepositoryN "{0}"' -f $StorageUser
        '/ConfigurationRepositoryP ""'
        '/ConfigurationRepositoryReport "{0}" -NBegin 1 -Extension {1}' -f $reportPath, $ExtensionName
    )

    if ($result.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $reportPath)) {
        throw "Не вдалося побудувати звіт сховища $StoragePath : $($result.Output)"
    }

    Read-StorageReport -Path $reportPath
}

Export-ModuleMember -Function ConvertFrom-MxlText, Get-MxlStringCells, Read-StorageReport, Get-StorageVersions
