# Keep an SSH tunnel open from this PC to the Live voice engines on the GPU machine (voice: ports 9001-9003, Studio separation: 9010).
# It reconnects by itself when the network drops (measured 14 Nov 2026: all tunnels fell in the middle of a run).
# Keep this window open while Live runs. While it is down the backend uses the Gnani voices and comes back by itself.
#   .\gpu_engine\tunnel.ps1 -Key C:\path\to\key -Target user@gpu-host
param(
    [Parameter(Mandatory = $true)][string]$Key,
    [Parameter(Mandatory = $true)][string]$Target
)
while ($true) {
    Write-Host "$(Get-Date -Format HH:mm:ss) connecting to the voice engines..."
    ssh -i $Key -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=5 -o ServerAliveCountMax=2 `
        -o ConnectTimeout=8 `
        -L 127.0.0.1:9001:127.0.0.1:9001 -L 127.0.0.1:9002:127.0.0.1:9002 -L 127.0.0.1:9003:127.0.0.1:9003 -L 127.0.0.1:9010:127.0.0.1:9010 $Target
    Write-Host "$(Get-Date -Format HH:mm:ss) tunnel closed (exit $LASTEXITCODE), retrying in 2 s"
    Start-Sleep -Seconds 2
}
