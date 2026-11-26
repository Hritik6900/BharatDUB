# A second v1 backend for a comparison: its own port and data folder. Keys come from backend\.env as usual.
# Never 8010 (v0); 8110 is the main v1 backend.
#
#   -Mode manual (the default)   every v1 feature off except the ones given in -Flags (as before v1.2), the trace on:
#       powershell -File scripts\v1\ab-server.ps1 -Port 8121 -Name budget -Flags "V1_LIVE_BUDGET=true"
#   -Mode auto                   auto mode (what v1 runs with). -Flags may carry settings (not switches: those are
#                                ignored in auto mode); -Overrides switches single behaviours off for this backend:
#       powershell -File scripts\v1\ab-server.ps1 -Port 8120 -Name auto -Mode auto
#       powershell -File scripts\v1\ab-server.ps1 -Port 8122 -Name auto-learned -Mode auto -Overrides "live_stock_default=off"
#
# An auto backend never reads backend\config\overrides.yaml: it gets a file of its own in its data folder, holding
# exactly what -Overrides says (nothing, when it is left out), so a comparison does not depend on that file.
param([Parameter(Mandatory)][int]$Port, [Parameter(Mandatory)][string]$Name, [string]$Flags = "",
      [ValidateSet("manual", "auto")][string]$Mode = "manual", [string]$Overrides = "")
if ($Port -in 3000, 3100, 8010, 8110 -or ($Port -ge 9001 -and $Port -le 9045)) { throw "port $Port is taken by v0, v1 or a model server" }
if ($Mode -eq "manual" -and $Overrides) { throw "-Overrides is for -Mode auto (manual mode does not read overrides)" }
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$data = Join-Path $root "data-v1\ab\$Name"
New-Item -ItemType Directory -Force $data | Out-Null
$env:V1_MODE = $Mode
if ($Mode -eq "manual") {
  foreach ($f in "V1_ROUTER", "V1_TTS_SERVER", "V1_TTS_MAYA", "V1_LIVE_STOCK_DEFAULT",
                 "V1_LIVE_LATE_SHORTEN", "V1_LIVE_BACKCHECK", "V1_STUDIO_HQ", "V1_FIT_115",
                 "V1_BREAKER", "V1_LIVE_DEGRADE", "V1_API_LOG", "V1_LIVE_BUDGET", "V1_EN_SINGLE_VOICE",
                 "V1_HQ_JUDGE", "V1_HQ_CALIBRATE", "V1_HQ_ADAPTIVE", "V1_HQ_NORMALISE", "V1_HQ_AUTO_GLOSSARY", "V1_HQ_REVIEW",
                 "V1_LIVE_RECORD", "V1_LISTEN_TEST") {
    Set-Item "env:$f" "false"
  }
  $env:V1_TRACE = "true"
  $env:V1_OVERRIDES_FILE = ""
} else {
  $file = Join-Path $data "overrides.yaml"
  $lines = @("# written by scripts\v1\ab-server.ps1 for the comparison backend '$Name'")
  foreach ($pair in ($Overrides -split "," | Where-Object { $_ })) { $k, $v = $pair.Trim() -split "=", 2; $lines += "${k}: $v" }
  Set-Content -Path $file -Value $lines -Encoding utf8
  $env:V1_OVERRIDES_FILE = $file
}
foreach ($pair in ($Flags -split "," | Where-Object { $_ })) { $k, $v = $pair.Trim() -split "=", 2; Set-Item "env:$k" $v }
$env:DATA_DIR = $data
$env:PUBLIC_API_BASE = "http://localhost:$Port"
Set-Location (Join-Path $root "backend")
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $Port
