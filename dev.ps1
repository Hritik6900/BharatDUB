# Start backend + frontend for local development (Windows PowerShell).
#   .\dev.ps1          real providers (needs backend\.env)
#   .\dev.ps1 -Mock    simulated providers, separate data folder (backend\data-mock), no keys needed
param([switch]$Mock)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")

$backendEnv = ""
if ($Mock) {
    $backendEnv = "`$env:MOCK_PROVIDERS='true'; `$env:DATA_DIR='$root\backend\data-mock'; `$env:STUDIO_SEPARATE='false';"
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "$backendEnv cd '$root\backend'; .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\web'; npm run dev"
Write-Host "Backend: http://localhost:8000/health   Frontend: http://localhost:3000"
