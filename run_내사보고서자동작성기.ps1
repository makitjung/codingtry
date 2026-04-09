$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $projectRoot ".uv-cache"
$hostAddr = "127.0.0.1"
$port = 8765
$url = "http://$hostAddr`:$port/web/index.html"

function Get-ListenerOnPort {
    param([int]$TargetPort)
    $line = netstat -ano | Select-String ":$TargetPort" | Select-String "LISTENING" | Select-Object -First 1
    if (-not $line) { return $null }
    $parts = ($line -replace "\s+", " ").Trim().Split(" ")
    if ($parts.Length -lt 5) { return $null }
    return [int]$parts[-1]
}

$existingPid = Get-ListenerOnPort -TargetPort $port
if ($existingPid) {
    Stop-Process -Id $existingPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
}

Start-Process -FilePath "uv" `
    -ArgumentList "run --python 3.12 python report.py --host $hostAddr --port $port --no-browser" `
    -WorkingDirectory $projectRoot `
    -WindowStyle Hidden

Start-Sleep -Seconds 1
$existingPid = Get-ListenerOnPort -TargetPort $port
if (-not $existingPid) {
    Write-Error "웹 서버를 시작하지 못했습니다. 터미널에서 'uv run --python 3.12 python report.py'로 직접 확인해주세요."
}

Start-Process $url
Write-Output "내사보고서 웹앱을 열었습니다: $url"
