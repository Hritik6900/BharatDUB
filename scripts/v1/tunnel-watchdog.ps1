# Tunnel watchdog: looks at the tunnel ports every 10 s, says exactly what is wrong when they stop answering, and
# restarts ONLY the tunnel when that is safe. Run it in its own window next to v0's gpu_engine\tunnel.ps1:
#
#   powershell -File scripts\v1\tunnel-watchdog.ps1                                   # watch and report only
#   powershell -File scripts\v1\tunnel-watchdog.ps1 -Key C:\path\key -Target user@host   # ... and take over when no tunnel window runs
#   ... -RestartStuck                                                                 # ... and end an ssh that is stuck
#
# What "restart only the tunnel" means here, and why.
# v0's tunnel.ps1 already reconnects by itself: each ssh has ServerAliveInterval=5 / ServerAliveCountMax=2, so it exits
# about 10 s after the link dies, and tunnel.ps1 starts it again within 2 s. A second script that also started ssh
# for the same ports would fight it (ExitOnForwardFailure makes the loser exit, and v0's loop would then dial the GPU
# machine every 2 s for nothing). So this watchdog never starts a tunnel while a tunnel.ps1 window is running, and it
# never ends a process it did not start, unless -RestartStuck is given. It looks at each port and tells four cases apart:
#
#   answers   something on the GPU machine replied. Nothing to do.
#   refused   nothing listens on the port: there is no ssh for it.
#               tunnel.ps1 is running  -> it is reconnecting; this script only notes how long it takes.
#               tunnel.ps1 is not      -> after -Grace seconds this script starts the ssh itself (needs -Key and
#                                         -Target), with the same options as tunnel.ps1, one ssh per group of ports.
#   closed    ssh listens and the connection is closed at once: the tunnel is fine, the SERVICE on the GPU machine
#             is down. Restarting the tunnel would not help and is not done.
#   hang      ssh listens, takes the connection, and nothing ever comes back: the link under ssh is dead and ssh has
#             not noticed (it should have, within 10 s). After -StuckAfter seconds:
#               an ssh this script started -> ended and started again.
#               someone else's ssh         -> named in the log (PID, since when). Ended only with -RestartStuck, and
#                                             only that one ssh.exe, after checking that it is the process that
#                                             listens on that very port and that its command line forwards it.
#                                             tunnel.ps1 then reconnects it. Never a PowerShell window, never another ssh.
#
# It also says when this PC was asleep (a gap between two looks): a sleeping laptop is the longest stall there is, and
# no script can tunnel through it. See docs\v1\NEEDS_APPROVAL.md for the powercfg lines that stop it sleeping on AC power.
#
# Log: data-v1\tunnel-watchdog.log (and this window). Ctrl+C ends the watchdog; an ssh it started ends with it.
param(
    [string]$Key = "",
    [string]$Target = "",
    [int]$Every = 10,          # seconds between looks
    [int]$Grace = 20,          # a refused port is left to tunnel.ps1 (or to chance) this long before this script dials
    [int]$StuckAfter = 30,     # a hanging port is called stuck after this long
    [int]$Cooldown = 60,       # at least this long between two restarts of the same group
    [switch]$RestartStuck,     # allow ending a stuck ssh that this script did not start
    [string]$Log = ""
)
$ErrorActionPreference = "Continue"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (-not $Log) {
    $dir = Join-Path $root "data-v1"
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
    $Log = Join-Path $dir "tunnel-watchdog.log"
}
# The same groups as v0's gpu_engine\tunnel.ps1: one ssh per kind of traffic.
$groups = [ordered]@{
    "voice"          = @(9001, 9002, 9003)
    "voice-mio"      = @(9040)
    "separation"     = @(9010)
    "translation"    = @(9020)
    "speech-to-text" = @(9030)
}

function Write-Line([string]$Text) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Text"
    Write-Host $line
    Add-Content -Path $Log -Value $line -Encoding utf8
}

# One look at a local port: "answers", "refused", "closed" or "hang" (see the top of this file).
function Test-Port([int]$Port, [int]$TimeoutMs = 3000) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $pending = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne(2500)) { return "refused" }
        try { $client.EndConnect($pending) } catch { return "refused" }
        $client.ReceiveTimeout = $TimeoutMs
        $client.SendTimeout = $TimeoutMs
        $stream = $client.GetStream()
        $request = [Text.Encoding]::ASCII.GetBytes("GET /health HTTP/1.0`r`nHost: 127.0.0.1`r`n`r`n")
        $stream.Write($request, 0, $request.Length)
        $buffer = New-Object byte[] 64
        $n = $stream.Read($buffer, 0, 64)
        if ($n -gt 0) { return "answers" }     # any reply at all, a 404 too: the far end is there
        return "closed"
    } catch {
        $e = $_.Exception
        while ($e -and -not ($e -is [System.Net.Sockets.SocketException])) { $e = $e.InnerException }
        if ($e -and $e.SocketErrorCode -eq [System.Net.Sockets.SocketError]::TimedOut) { return "hang" }
        return "closed"
    } finally {
        $client.Close()
    }
}

# The process that listens on a local port, or $null.
function Get-PortOwner([int]$Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) { return $null }
    return Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)" -ErrorAction SilentlyContinue
}

# Is a tunnel.ps1 window (v0's reconnecting loop) running?
function Test-TunnelScript {
    $found = Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'tunnel\.ps1' -and $_.CommandLine -notmatch 'tunnel-watchdog' }
    return [bool]$found
}

function Start-GroupTunnel([string]$Name) {
    # The same ssh options as v0's gpu_engine\tunnel.ps1.
    $sshArgs = @("-i", $Key, "-N", "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
                 "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2", "-o", "ConnectTimeout=8")
    foreach ($port in $groups[$Name]) { $sshArgs += @("-L", "127.0.0.1:${port}:127.0.0.1:${port}") }
    $sshArgs += $Target
    return Start-Process -FilePath "ssh" -ArgumentList $sshArgs -NoNewWindow -PassThru
}

$canDial = [bool]($Key -and $Target)
$state = @{}
foreach ($name in $groups.Keys) {
    $state[$name] = @{ BadSince = $null; RefusedSince = $null; HangSince = $null; Said = ""; Ours = $null; LastRestart = [datetime]::MinValue }
}
$mode = "report only"
if ($canDial) { $mode = "takes over when no tunnel.ps1 window runs" }
if ($RestartStuck) { $mode += ", may end a stuck ssh" }
Write-Line "WATCHDOG started ($mode); looking every $Every s at $(($groups.Values | ForEach-Object { $_ }) -join ', ')"
$last = Get-Date

while ($true) {
    $now = Get-Date
    $gap = ($now - $last).TotalSeconds
    if ($gap -gt ($Every * 3 + 30)) {
        Write-Line "SLEPT this PC did nothing for $([math]::Round($gap / 60, 1)) min (asleep, or frozen): every stream stalled for that long"
    }
    $last = $now
    $loopRuns = Test-TunnelScript
    foreach ($name in $groups.Keys) {
        $st = $state[$name]
        $ports = $groups[$name]
        $seen = @{}
        foreach ($port in $ports) { $seen[$port] = Test-Port $port }
        $bad = @($ports | Where-Object { $seen[$_] -ne "answers" })
        if ($bad.Count -eq 0) {
            if ($st.BadSince) {
                Write-Line "BACK $name answers again after $([math]::Round(((Get-Date) - $st.BadSince).TotalSeconds)) s"
            }
            $st.BadSince = $null; $st.RefusedSince = $null; $st.HangSince = $null; $st.Said = ""
            continue
        }
        if (-not $st.BadSince) { $st.BadSince = Get-Date }
        $what = ($bad | ForEach-Object { "${_}:$($seen[$_])" }) -join " "
        $hang = @($bad | Where-Object { $seen[$_] -eq "hang" })
        $refused = @($bad | Where-Object { $seen[$_] -eq "refused" })
        $ours = $st.Ours -and -not $st.Ours.HasExited

        if ($hang.Count -gt 0) {
            if (-not $st.HangSince) { $st.HangSince = Get-Date }
            $for = [math]::Round(((Get-Date) - $st.HangSince).TotalSeconds)
            if ($for -lt $StuckAfter) {
                if ($st.Said -ne "hang") { Write-Line "DOWN $name ($what): the tunnel takes connections and nothing comes back"; $st.Said = "hang" }
                continue
            }
            if (((Get-Date) - $st.LastRestart).TotalSeconds -lt $Cooldown) { continue }
            $owner = Get-PortOwner $hang[0]
            $isTunnel = $owner -and $owner.Name -eq "ssh.exe" -and $owner.CommandLine -match "-L\s+127\.0\.0\.1:$($hang[0]):"
            if ($ours -and $owner -and $owner.ProcessId -eq $st.Ours.Id) {
                Write-Line "RESTART $name stuck for $for s: ending the ssh this watchdog started (PID $($st.Ours.Id)) and dialling again"
                Stop-Process -Id $st.Ours.Id -Force -ErrorAction SilentlyContinue
                $st.Ours = Start-GroupTunnel $name
                $st.LastRestart = Get-Date; $st.HangSince = $null
            } elseif ($isTunnel -and $RestartStuck) {
                Write-Line "RESTART $name stuck for $for s: ending ssh PID $($owner.ProcessId), the one that listens on $($hang[0]) (tunnel.ps1 running: $loopRuns)"
                Stop-Process -Id $owner.ProcessId -Force -ErrorAction SilentlyContinue
                $st.LastRestart = Get-Date; $st.HangSince = $null; $st.RefusedSince = $null
            } elseif ($isTunnel) {
                if ($st.Said -ne "stuck") {
                    Write-Line "STUCK $name for $for s ($what): ssh PID $($owner.ProcessId) holds the port and has not noticed the dead link. Not touched: it is not this script's process. End that one ssh (tunnel.ps1 reconnects it), or run this script with -RestartStuck"
                    $st.Said = "stuck"
                }
            } elseif ($st.Said -ne "foreign") {
                $who = "nobody"
                if ($owner) { $who = "$($owner.Name) PID $($owner.ProcessId)" }
                Write-Line "STUCK $name for $for s ($what): the port is held by $who, which is not a tunnel this script knows. Left alone"
                $st.Said = "foreign"
            }
            continue
        }
        $st.HangSince = $null

        if ($refused.Count -gt 0) {
            if (-not $st.RefusedSince) { $st.RefusedSince = Get-Date }
            $for = [math]::Round(((Get-Date) - $st.RefusedSince).TotalSeconds)
            if ($loopRuns) {
                if ($st.Said -ne "loop") { Write-Line "DOWN $name ($what): no ssh on the port; the tunnel.ps1 window is reconnecting it"; $st.Said = "loop" }
            } elseif ($ours) {
                if ($st.Said -ne "dialling") { Write-Line "DOWN $name ($what): this watchdog's ssh (PID $($st.Ours.Id)) is connecting"; $st.Said = "dialling" }
            } elseif ($for -ge $Grace -and $canDial) {
                Write-Line "START $name ($what): no ssh for $for s and no tunnel.ps1 window: dialling with tunnel.ps1's options"
                $st.Ours = Start-GroupTunnel $name
                $st.LastRestart = Get-Date; $st.Said = "dialling"
            } elseif ($for -ge $Grace -and $st.Said -ne "nobody") {
                Write-Line "DOWN $name ($what): no ssh for $for s and nothing is reconnecting it. Start gpu_engine\tunnel.ps1, or run this script with -Key and -Target"
                $st.Said = "nobody"
            }
            continue
        }
        $st.RefusedSince = $null

        if ($st.Said -ne "service") {
            Write-Line "SERVICE $name ($what): the tunnel is up; the server on the GPU machine does not answer. Restarting the tunnel would not help"
            $st.Said = "service"
        }
    }
    Start-Sleep -Seconds $Every
}
