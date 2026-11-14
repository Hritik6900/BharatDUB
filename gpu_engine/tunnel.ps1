# Open the SSH tunnel from this PC to the Live voice engines on the GPU machine (ports 9001-9003).
# Keep this window open while Live runs. Without it the backend falls back to the Gnani voices by itself.
#   .\gpu_engine\tunnel.ps1 -Key C:\path\to\key -Target user@gpu-host
param(
    [Parameter(Mandatory = $true)][string]$Key,
    [Parameter(Mandatory = $true)][string]$Target
)
ssh -i $Key -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=20 -o ServerAliveCountMax=3 `
    -L 127.0.0.1:9001:127.0.0.1:9001 -L 127.0.0.1:9002:127.0.0.1:9002 -L 127.0.0.1:9003:127.0.0.1:9003 $Target
