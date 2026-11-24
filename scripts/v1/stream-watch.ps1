# Watches every live session on v0 (8010) and v1 (8110), all the time. Read-only: it never posts to a backend.
#
#   powershell -File scripts\v1\stream-watch.ps1            # in this window (Ctrl+C stops it)
#   powershell -File scripts\v1\stream-watch.ps1 -Window    # in a window of its own, which stays open
#
# Logs: data-v1\streamwatch\events.log (what happened), <version>_<session>.csv (a row every 20 s),
#       <version>_<session>.summary.txt (per-language numbers when a stream ends).
param(
    [string]$V0 = "http://127.0.0.1:8010",
    [string]$V1 = "http://127.0.0.1:8110",
    [string]$V0Store = "$env:USERPROFILE\Desktop\BharatDUB\backend\data\local_db.json",
    [switch]$Window
)
$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
$script = Join-Path $PSScriptRoot "stream-watch.py"
$out = Join-Path $root "data-v1\streamwatch"
$v1Store = Join-Path $root "data-v1\local_db.json"
if (-not (Test-Path $python)) { throw "Python env not found: $python" }

if ($Window) {
    Start-Process powershell -ArgumentList @("-NoExit", "-File", "`"$PSCommandPath`"", "-V0", $V0, "-V1", $V1, "-V0Store", "`"$V0Store`"")
    "Watcher started in its own window. Events: $out\events.log"
    return
}

$already = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*stream-watch.py*" }
if ($already) { throw "A watcher is already running (PID $($already.ProcessId -join ', ')). Two would write the same files." }

$host.UI.RawUI.WindowTitle = "Bharat Dub stream watch (v0 + v1)"
& $python -u $script --out $out "v0=$V0=$V0Store" "v1=$V1=$v1Store" --health "$V1/api/v1/health"
