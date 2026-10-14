# Собирает тестовые внешние обработки-читатели платформой 1С и кладет .epf двоичными макетами
# в обработку СМП_ТестыМакеты тестового расширения. Запускать после правки исходников здесь.
# Платформа - ветка 8.3.27.x; временная файловая база создается и удаляется скриптом.
param(
    [string]$Platform = 'C:\Program Files\1cv8\8.3.27.1644\bin\1cv8.exe'
)
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$templates = Join-Path $here '..\src\DataProcessors\СМП_ТестыМакеты\Templates'
$work = Join-Path ([IO.Path]::GetTempPath()) ('smp_epf_' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
try {
    $ib = Join-Path $work 'ib'
    $p = Start-Process -Wait -PassThru -FilePath $Platform -ArgumentList 'CREATEINFOBASE', "File=$ib", '/Out', (Join-Path $work 'ci.log')
    if ($p.ExitCode -ne 0) { throw "CREATEINFOBASE: код $($p.ExitCode)" }
    foreach ($name in 'СМП_ТестЧитательВнешний', 'СМП_ТестЧитательСтарый') {
        $epf = Join-Path $work "$name.epf"
        $log = Join-Path $work "$name.log"
        $p = Start-Process -Wait -PassThru -FilePath $Platform -ArgumentList 'DESIGNER', '/F', $ib,
            '/DisableStartupDialogs', '/DisableStartupMessages',
            '/LoadExternalDataProcessorOrReportFromFiles', (Join-Path $here "$name.xml"), $epf, '/Out', $log
        if ($p.ExitCode -ne 0 -or -not (Test-Path $epf)) { throw "Сборка ${name}: код $($p.ExitCode); $(Get-Content -Raw $log)" }
        Copy-Item -LiteralPath $epf -Destination (Join-Path $templates "$name\Ext\Template.bin") -Force
        "$name -> макет, $((Get-Item $epf).Length) байт"
    }
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
