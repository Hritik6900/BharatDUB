# Start v1 on a Windows machine without containers: backend 8110, website 3100. v0 (8010, 3000) is not touched.
#   powershell -File scripts\v1\run-local.ps1 [-Build]
param([switch]$Build, [int]$BackendPort = 8110, [int]$WebPort = 3100)
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if ($BackendPort -in 3000, 8010 -or $WebPort -in 3000, 8010) { throw "ports 3000 and 8010 belong to v0" }
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "backend\.venv is missing: python -m venv backend\.venv, then pip install -r backend\requirements.txt" }
Start-Process -FilePath $py -WorkingDirectory (Join-Path $root "backend") -WindowStyle Minimized `
  -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort"
$env:NEXT_PUBLIC_API_BASE = "http://localhost:$BackendPort"
$env:NEXT_PUBLIC_WS_BASE = "ws://localhost:$BackendPort"
Set-Location (Join-Path $root "web")
if ($Build -or -not (Test-Path ".next")) { npm run build }
npx next start -p $WebPort
