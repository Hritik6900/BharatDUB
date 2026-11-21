# Keep SSH tunnels open from this PC to the engines on the GPU machine. They reconnect by themselves when the network
# drops (measured 14 Nov 2026: all tunnels fell in the middle of a run). Keep this window open while Live runs.
# While a tunnel is down the backend uses the hosted services and comes back by itself.
#   .\gpu_engine\tunnel.ps1 -Key C:\path\to\key -Target user@gpu-host
#
# One SSH connection per kind of traffic, not one for everything. Seen 21 Nov 2026 on a real 55-minute stream in
# all-GPU mode: with every engine in one connection, a single stalled packet held speech-to-text, translation and
# voice up together (lines after 5-17 s while the machine itself answered in 2 ms and ping was fine).
#   voice 9001-9003 | Studio separation 9010 | translation 9020 | speech-to-text 9030
param(
    [Parameter(Mandatory = $true)][string]$Key,
    [Parameter(Mandatory = $true)][string]$Target
)
$groups = [ordered]@{
    "voice"          = @(9001, 9002, 9003)
    "voice-mio"      = @(9040)
    "separation"     = @(9010)
    "translation"    = @(9020)
    "speech-to-text" = @(9030)
}
$running = @{}
while ($true) {
    foreach ($name in $groups.Keys) {
        $p = $running[$name]
        if ($p -and -not $p.HasExited) { continue }
        if ($p) { Write-Host "$(Get-Date -Format HH:mm:ss) $name tunnel closed (exit $($p.ExitCode)), reconnecting" }
        $sshArgs = @("-i", $Key, "-N", "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
                     "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2", "-o", "ConnectTimeout=8")
        foreach ($port in $groups[$name]) { $sshArgs += @("-L", "127.0.0.1:${port}:127.0.0.1:${port}") }
        $sshArgs += $Target
        Write-Host "$(Get-Date -Format HH:mm:ss) connecting: $name ($($groups[$name] -join ', '))"
        $running[$name] = Start-Process -FilePath "ssh" -ArgumentList $sshArgs -NoNewWindow -PassThru
    }
    Start-Sleep -Seconds 2
}
