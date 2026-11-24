# Side-by-side pitch video from a recorded Live session: the original (left) beside the same video with the
# session's dub (right), the dub's captions burned in, the language, and that recording's own numbers
# (first audio, on time). ffmpeg does the picture; backend\app\v1\pitch.py lays the dub on the video's clock.
#
#   powershell -File scripts\v1\render-pitch.ps1 -Recording data-v1\recordings\<session> -Video C:\path\video.mp4
#   ... -Lang ta-IN -Stereo split|dub|mix -Out data-v1\pitch\demo.mp4
#
# -Recording  a folder written by a session that was made with "keep a recording" while V1_LIVE_RECORD was on
# -Video      the video that session was fed from
# -Stereo     split = original sound left, dub right (default); dub = the dub alone; mix = the dub over the
#             original at 18%, as the viewer page plays it
# -LeadS, -Loops, -GapMs   only for a recording made by the replay harness (backend\eval\live_replay.py --record):
#             its --lead-s, --loops and --gap-ms, so the picture is built the way the sound was fed
# -OffsetMs   only for a recording without the video's clock (a microphone session): session time of the video's start
# The output goes into the recording's folder unless -Out says otherwise. Keep it in the data folder: it is the
# speaker's voice and video, and it does not belong in the repository.
param(
  [Parameter(Mandatory)][string]$Recording,
  [Parameter(Mandatory)][string]$Video,
  [string]$Lang = "",
  [ValidateSet("split", "dub", "mix")][string]$Stereo = "split",
  [string]$Out = "",
  [double]$LeadS = 0,
  [int]$Loops = 1,
  [int]$GapMs = 0,
  [int]$OffsetMs = 0,
  [int]$Height = 720,
  [int]$Fps = 30
)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$rec = (Resolve-Path $Recording).Path
$vid = (Resolve-Path $Video).Path
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "no Python at $py" }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -and -not $env:FFMPEG_BIN) { throw "ffmpeg is not on the PATH (or set FFMPEG_BIN and FFPROBE_BIN)" }
$a = @("-m", "app.v1.pitch", $rec, $vid, "--stereo", $Stereo, "--lead-s", $LeadS.ToString([cultureinfo]::InvariantCulture), "--loops", $Loops, "--gap-ms", $GapMs,
       "--offset-ms", $OffsetMs, "--height", $Height, "--fps", $Fps)
if ($Lang) { $a += @("--lang", $Lang) }
if ($Out) {
  $dir = Split-Path -Parent $Out
  if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
  if (-not [System.IO.Path]::IsPathRooted($Out)) { $Out = Join-Path (Get-Location).Path $Out }
  $a += @("--out", $Out)
}
$env:PYTHONIOENCODING = "utf-8"
Push-Location (Join-Path $root "backend")
try {
  & $py @a
  if ($LASTEXITCODE -ne 0) { throw "render failed (exit $LASTEXITCODE)" }
} finally { Pop-Location }
