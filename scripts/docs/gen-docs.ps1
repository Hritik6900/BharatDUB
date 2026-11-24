<#
.SYNOPSIS
  Regenerate the generated blocks of the handbook (wrapper around scripts/docs/gen_docs.py).
.EXAMPLE
  powershell -File scripts\docs\gen-docs.ps1
  powershell -File scripts\docs\gen-docs.ps1 -Check
#>
param(
    [switch]$Check,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Resolve-Path (Join-Path $here '..\..')
$script = Join-Path $here 'gen_docs.py'

$exe = $null
$preArgs = @()
$venv = Join-Path $repo 'backend\.venv\Scripts\python.exe'
if (Test-Path $venv) {
    $exe = $venv
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $exe = 'py'
    $preArgs = @('-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $exe = 'python'
} else {
    Write-Error 'gen-docs: no Python found (backend\.venv, py -3 or python)'
    exit 2
}

$argList = @()
$argList += $preArgs
$argList += $script
if ($Check) { $argList += '--check' }
if ($Rest) { $argList += $Rest }

& $exe @argList
exit $LASTEXITCODE
