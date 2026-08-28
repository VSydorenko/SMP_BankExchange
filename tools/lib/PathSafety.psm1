#Requires -Version 7
Set-StrictMode -Version Latest

function Assert-SafeWorkPath {
    <#
    .SYNOPSIS
        Зупиняє видалення/створення за шляхом, який не є свідомо звуженою підтекою.
    .DESCRIPTION
        Спільний запобіжник перед кожним рекурсивним видаленням у tools/: storage.json
        пишеться вручну при підключенні продукту, і його поле sourcePath доходить до
        Join-Path і далі до Remove-Item -Recurse -Force без жодної перевірки. Порожній
        sourcePath ("") робить Join-Path $productPath "" рівним самому $productPath —
        і -Apply стирає увесь каталог продукту разом із негітованим v8project.local.yaml,
        який неможливо відновити з git. Та сама форма ризику — у New-V8FileInfobase
        (wipes any $Path без перевірки, що це взагалі інфобаза) і в dump-config.ps1.

        Приймає вже складений (Join-Path чи інакше) шлях, який ось-ось підуть видаляти
        чи створювати заново, і межу, під якою він мусить лежати. Кидає виняток, якщо:
        - $Path порожній або складається лише з пробілів;
        - $Path містить сегмент ".." (перевіряється на сирому рядку, до нормалізації —
          GetFullPath згорнув би ".." непомітно, а сама наявність такого сегмента в
          закомодженому storage.json чи в аргументі скрипта підозріла незалежно від
          того, чи виводить він за межу після згортання);
        - нормалізований $Path не є ВЛАСНЕ підтекою $MustBeUnder (рівність з межею —
          саме той порожній-sourcePath випадок — теж відхиляється, не тільки вихід за неї).
    .EXAMPLE
        Assert-SafeWorkPath -Path $sourceDir -MustBeUnder $productPath -Description "sourceDir продукту $Product"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][AllowEmptyString()][string]$Path,
        [Parameter(Mandatory)][string]$MustBeUnder,
        [Parameter(Mandatory)][string]$Description
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "$Description порожній або складається лише з пробілів — відмовляюсь видаляти чи створювати за таким шляхом."
    }

    $segments = $Path -split '[\\/]+'
    if ($segments -contains '..') {
        throw "$Description містить сегмент '..' ('$Path') — відмовляюсь видаляти чи створювати за таким шляхом."
    }

    $boundary = [System.IO.Path]::GetFullPath($MustBeUnder).TrimEnd('\', '/')
    $full     = [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    $prefix   = $boundary + [System.IO.Path]::DirectorySeparatorChar

    if (($full -eq $boundary) -or (-not $full.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase))) {
        throw "$Description ('$Path') не є підтекою '$MustBeUnder' — відмовляюсь видаляти чи створювати за таким шляхом."
    }
}

Export-ModuleMember -Function Assert-SafeWorkPath
