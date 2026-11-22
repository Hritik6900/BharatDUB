# A second v1 backend for an on/off comparison: its own port and data folder, every v1 flag off except the ones
# given. Keys come from backend\.env as usual. Never 8010 (v0); 8110 is the main v1 backend.
#   powershell -File scripts\v1\ab-server.ps1 -Port 8112 -Name dynamic -Flags "V1_PHRASE_DYNAMIC=true"
param([Parameter(Mandatory)][int]$Port, [Parameter(Mandatory)][string]$Name, [string]$Flags = "")
if ($Port -in 3000, 8010, 8110 -or ($Port -ge 9001 -and $Port -le 9045)) { throw "port $Port is taken by v0, v1 or a model server" }
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
foreach ($f in "V1_ROUTER", "V1_PHRASE_DYNAMIC", "V1_SPEC_TRANSLATE", "V1_TTS_SERVER", "V1_TTS_MAYA", "V1_LIVE_STOCK_DEFAULT",
               "V1_LIVE_LATE_SHORTEN", "V1_LIVE_BACKCHECK", "V1_LLM_PREFIX_CACHE", "V1_STUDIO_HQ", "V1_FIT_115") {
  Set-Item "env:$f" "false"
}
$env:V1_TRACE = "true"
foreach ($pair in ($Flags -split "," | Where-Object { $_ })) { $k, $v = $pair.Trim() -split "=", 2; Set-Item "env:$k" $v }
$data = Join-Path $root "data-v1\ab\$Name"
New-Item -ItemType Directory -Force $data | Out-Null
$env:DATA_DIR = $data
$env:PUBLIC_API_BASE = "http://localhost:$Port"
Set-Location (Join-Path $root "backend")
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $Port
