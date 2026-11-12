<#!
Capture a short, silent webcam clip or extract frames from an existing optical video.
Run from PowerShell. Requires ffmpeg and ffprobe on PATH.
Examples:
  .\scripts\Collect-Samples.ps1 -Label WORK -Scene editor
  .\scripts\Collect-Samples.ps1 -Label VIDEO -Scene windowed-player
  .\scripts\Collect-Samples.ps1 -Label NEUTRAL -Scene desktop
  .\scripts\Collect-Samples.ps1 -Label WORK -Scene new-document -Split test
  .\scripts\Collect-Samples.ps1 -Label WORK -Scene editor -SourceVideo C:\clips\editor.mp4
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('WORK','VIDEO','NEUTRAL')][string]$Label,
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Scene,
    [string]$DeviceName = 'Razer Kiyo V2',
    [string]$SourceVideo,
    [ValidateSet('train','test')][string]$Split = 'train',
    [ValidateRange(1,120)][int]$DurationSeconds = 8,
    [ValidateRange(1,10)][int]$SamplesPerSecond = 5,
    [ValidateRange(0,30)][int]$CountdownSeconds = 5,
    [ValidateRange(0,36000)][double]$StartSeconds = 0,
    [ValidatePattern('^$|^\d+:\d+:\d+:\d+$')][string]$Crop = '',
    [string]$DataRoot
)
$ErrorActionPreference = 'Stop'
$ffmpegPath = (Get-Command ffmpeg -ErrorAction Stop).Source
$ffprobePath = (Get-Command ffprobe -ErrorAction Stop).Source
if (-not $DataRoot) { $DataRoot = Join-Path (Split-Path $PSScriptRoot -Parent) 'data' }
$DataRoot = [IO.Path]::GetFullPath($DataRoot)
$session = '{0}-{1}-{2}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $Scene, ([guid]::NewGuid().ToString('N').Substring(0,6))
$rawDir = Join-Path $DataRoot "raw/$Split/$Label/$session"
$outputDir = Join-Path $DataRoot "processed/$Split/$Label/$session"
$null = New-Item -ItemType Directory -Path $rawDir,$outputDir -Force
$receiptPath = Join-Path $rawDir 'capture.json'
$receipt = [ordered]@{
    status = 'started'; label = $Label; scene = $Scene; split = $Split
    session = $session; started_utc = [DateTime]::UtcNow.ToString('o')
    source_kind = 'optical_webcam'; device = $DeviceName
    source_video = $null; source_sha256 = $null
    start_seconds = $StartSeconds; requested_seconds = $DurationSeconds
    samples_per_second = $SamplesPerSecond; frame_count = 0
    crop_w_h_x_y = $Crop; preprocessing = 'crop if set; aspect-fit to 224x224; black padding'
    output_directory = $outputDir
    note = 'Adjacent frames are correlated. Use a separate capture session and unseen content for testing.'
}
function Write-Receipt { $receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $receiptPath -Encoding UTF8 }
Write-Receipt
try {
    if ($SourceVideo) {
        $videoPath = (Resolve-Path -LiteralPath $SourceVideo -ErrorAction Stop).Path
        $receipt.source_kind = 'provided_video_verify_optical_origin'
        $receipt.device = $null
    } else {
        if ($StartSeconds -ne 0) { throw 'StartSeconds is only supported with SourceVideo.' }
        $videoPath = Join-Path $rawDir 'capture.mkv'
        for ($remaining = $CountdownSeconds; $remaining -gt 0; $remaining--) {
            Write-Host "Recording starts in $remaining seconds. Display the intended scene; minimize this terminal if it covers the monitor."
            Start-Sleep -Seconds 1
        }
        Write-Host "Capturing $DurationSeconds seconds of $Label / $Scene. Keep this class visible; no audio is recorded."
        & $ffmpegPath -hide_banner -loglevel warning -nostdin -n -f dshow -rtbufsize 256M -i "video=$DeviceName" -an -t $DurationSeconds -c:v libx264 -preset ultrafast -crf 20 $videoPath
        if ($LASTEXITCODE -ne 0) { throw "Webcam capture failed (ffmpeg exit $LASTEXITCODE). Close other camera apps and check the device name." }
    }
    $receipt.source_video = $videoPath
    $receipt.source_sha256 = (Get-FileHash -LiteralPath $videoPath -Algorithm SHA256).Hash
    $probeText = & $ffprobePath -v error -select_streams v:0 -show_entries stream=width,height -of json $videoPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the source video.' }
    $probe = ($probeText -join "`n") | ConvertFrom-Json
    if (-not $probe.streams -or -not $probe.streams[0].width) { throw 'No video stream found.' }
    $receipt.source_width = $probe.streams[0].width
    $receipt.source_height = $probe.streams[0].height
    $filters = @("fps=$SamplesPerSecond")
    if ($Crop) {
        $cropValues = @($Crop.Split(':') | ForEach-Object { [int]$_ })
        if ($cropValues[0] -le 0 -or $cropValues[1] -le 0 -or
            ($cropValues[0]+$cropValues[2]) -gt $receipt.source_width -or
            ($cropValues[1]+$cropValues[3]) -gt $receipt.source_height) { throw 'Crop falls outside the source image.' }
        $filters += "crop=$Crop"
    }
    $filters += 'scale=224:224:force_original_aspect_ratio=decrease','pad=224:224:(ow-iw)/2:(oh-ih)/2:color=black','setsar=1'
    $filter = $filters -join ','
    $receipt.ffmpeg_filter = $filter
    & $ffmpegPath -hide_banner -loglevel error -nostdin -n -ss $StartSeconds -i $videoPath -t $DurationSeconds -an -vf $filter -frames:v ($DurationSeconds*$SamplesPerSecond) -q:v 2 (Join-Path $outputDir 'frame-%04d.jpg')
    if ($LASTEXITCODE -ne 0) { throw "Frame extraction failed (ffmpeg exit $LASTEXITCODE)." }
    $count = @(Get-ChildItem -LiteralPath $outputDir -Filter 'frame-*.jpg' -File).Count
    if ($count -eq 0) { throw 'No frames extracted; check start time and video duration.' }
    $receipt.frame_count = $count
    $receipt.status = 'complete'
    $receipt.finished_utc = [DateTime]::UtcNow.ToString('o')
    Write-Receipt
    $receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $outputDir 'capture.json') -Encoding UTF8
    Write-Host "Saved $count images: $outputDir"
    Write-Host 'Upload the JPG files to the matching Teachable Machine class. Do not upload test captures as training samples.'
} catch {
    $receipt.status = 'failed'
    $receipt.error = $_.Exception.Message
    Write-Receipt
    throw
}
