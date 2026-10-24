# 设备端 kiosk 启动：全屏、无地址栏
# 用法：
#   powershell -ExecutionPolicy Bypass -File tools/start-kiosk.ps1
#   powershell -ExecutionPolicy Bypass -File tools/start-kiosk.ps1 -Url http://127.0.0.1:5176
#   powershell -ExecutionPolicy Bypass -File tools/start-kiosk.ps1 -Browser edge

param(
    [string]$Url = "http://127.0.0.1:5176",
    [ValidateSet("auto", "chrome", "edge")]
    [string]$Browser = "auto",
    [string]$ProfileDir = (Join-Path $env:TEMP "medpal-kiosk"),
    [string]$WindowSize = "480,800"
)

$ErrorActionPreference = "Stop"

# kiosk=1 会隐藏模拟器的联调工具条，只保留设备画面
if ($Url -match "kiosk=1") {
    $kioskUrl = $Url
} elseif ($Url.Contains("?")) {
    $kioskUrl = "$Url&kiosk=1"
} else {
    $kioskUrl = "$Url?kiosk=1"
}

$candidates = @(
    @{ Name = "chrome"; Path = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" },
    @{ Name = "chrome"; Path = "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe" },
    @{ Name = "chrome"; Path = "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe" },
    @{ Name = "edge"; Path = "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe" },
    @{ Name = "edge"; Path = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe" },
    @{ Name = "edge"; Path = "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe" }
)

$exe = $candidates |
    Where-Object { $Browser -eq "auto" -or $_.Name -eq $Browser } |
    Where-Object { Test-Path $_.Path } |
    Select-Object -First 1 -ExpandProperty Path

if (-not $exe) {
    throw "没有找到 Chrome 或 Edge。请先安装，或用 -Browser 指定。"
}

New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null

$browserArgs = @(
    "--kiosk",
    "--app=$kioskUrl",
    "--user-data-dir=`"$ProfileDir`"",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-pinch",
    "--overscroll-history-navigation=0",
    "--window-size=$WindowSize"
)

Write-Host ""
Write-Host "设备端 kiosk" -ForegroundColor Cyan
Write-Host "  URL     : $kioskUrl"
Write-Host "  Browser : $exe"
Write-Host "  Profile : $ProfileDir"
Write-Host "  退出    : Alt + F4" -ForegroundColor Yellow
Write-Host ""

Start-Process -FilePath $exe -ArgumentList $browserArgs
