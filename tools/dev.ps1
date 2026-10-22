# W1 本地开发环境：起两个 mock 服务
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File tools/dev.ps1             # 起服务，按回车停止
#   powershell -ExecutionPolicy Bypass -File tools/dev.ps1 -Detached   # 起服务后立即返回，打印 PID
#   powershell -ExecutionPolicy Bypass -File tools/dev.ps1 -CheckOnly  # 只体检解释器与依赖，不占端口
#
# 解释器优先级：仓库内 .venv > venv > PATH 上的 python
# Windows 上 PATH 里的 python.exe 常是 Microsoft Store 的占位符：有命令、无解释器，
# 传任何参数都直接失败，所以这里显式跳过它，别让它冒充 Python。

param(
    [switch]$Detached,
    [switch]$CheckOnly,
    [int]$ApiPort = 8000,
    [int]$WsPort = 8090
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Resolve-RepoPython {
    $candidates = @(
        (Join-Path $RepoRoot '.venv\Scripts\python.exe'),
        (Join-Path $RepoRoot 'venv\Scripts\python.exe')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    $onPath = Get-Command python -ErrorAction SilentlyContinue
    if ($onPath -and $onPath.Source -notlike '*\WindowsApps\*') { return $onPath.Source }
    return $null
}

function Get-PythonVersion([string]$Exe) {
    $out = & $Exe -c "import sys; print(sys.version.split()[0])" 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    $text = ([string]$out).Trim()
    if (-not $text) { return $null }
    return $text
}

function Test-PythonModule([string]$Exe, [string]$Name) {
    & $Exe -c "import $Name" 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Test-PortInUse([int]$Port) {
    try {
        $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop
        return ($null -ne $conn)
    } catch {
        return $false
    }
}

function Wait-HttpReady([string]$Url, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 1 | Out-Null
            return $true
        } catch {
            Start-Sleep -Milliseconds 200
        }
    }
    return $false
}

function Wait-PortOpen([int]$Port, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $client.Connect('127.0.0.1', $Port)
            $client.Close()
            return $true
        } catch {
            Start-Sleep -Milliseconds 200
        }
    }
    return $false
}

# --- 1. 挑解释器 ---
$python = Resolve-RepoPython
if (-not $python) {
    Write-Host "找不到可用的 Python 解释器。" -ForegroundColor Red
    Write-Host "  PATH 上的 python 可能是 Microsoft Store 占位符（有命令、无解释器）。" -ForegroundColor DarkGray
    Write-Host "  先建虚拟环境，再用真解释器装依赖：" -ForegroundColor DarkGray
    Write-Host "    <真 Python 的路径> -m venv .venv" -ForegroundColor DarkGray
    Write-Host "    .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt" -ForegroundColor DarkGray
    exit 1
}

$version = Get-PythonVersion $python
if (-not $version) {
    Write-Host "解释器无法运行：$python" -ForegroundColor Red
    Write-Host "  这是 Microsoft Store 占位符的典型症状，换一个真 Python 再试。" -ForegroundColor DarkGray
    exit 1
}

# --- 2. 查依赖 ---
$missing = @()
if (-not (Test-PythonModule $python 'websockets')) { $missing += 'websockets' }

Write-Host "解释器 $python (Python $version)" -ForegroundColor Cyan
if ($missing.Count -gt 0) {
    Write-Host "缺依赖：$($missing -join ', ')" -ForegroundColor Red
    Write-Host "  装一下： .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt" -ForegroundColor DarkGray
    exit 1
}
Write-Host "依赖齐全（websockets）" -ForegroundColor Green

if ($CheckOnly) {
    Write-Host "检查通过，未占用任何端口。" -ForegroundColor Green
    exit 0
}

# --- 3. 起服务 ---
Write-Host ""
Write-Host "启动 mock 接口 ($ApiPort) 与 mock 会话 ($WsPort)..." -ForegroundColor Cyan

$started = @()

if (Test-PortInUse $ApiPort) {
    Write-Host "  跳过接口服务：$ApiPort 已在监听（可能已经在跑）" -ForegroundColor Yellow
} else {
    $api = Start-Process -FilePath $python `
        -ArgumentList @('tools/mock_api.py', '--port', "$ApiPort") `
        -PassThru -WindowStyle Minimized
    $started += @{ Label = '接口'; Port = $ApiPort; Process = $api }
}

if (Test-PortInUse $WsPort) {
    Write-Host "  跳过会话服务：$WsPort 已在监听（可能已经在跑）" -ForegroundColor Yellow
} else {
    $ws = Start-Process -FilePath $python `
        -ArgumentList @('tools/mock_ws.py', '--port', "$WsPort") `
        -PassThru -WindowStyle Minimized
    $started += @{ Label = '会话'; Port = $WsPort; Process = $ws }
}

# --- 4. 等就绪，不靠固定 sleep 猜 ---
$apiOk = Wait-HttpReady "http://127.0.0.1:$ApiPort/api/v1/health" 8
$wsOk = Wait-PortOpen $WsPort 8

Write-Host ""
if ($apiOk) {
    Write-Host "  接口  http://127.0.0.1:$ApiPort/api/v1/health" -ForegroundColor Green
} else {
    Write-Host "  接口  $ApiPort 没起来，看那个最小化窗口里的报错" -ForegroundColor Red
}
if ($wsOk) {
    Write-Host "  会话  ws://127.0.0.1:$WsPort" -ForegroundColor Green
} else {
    Write-Host "  会话  $WsPort 没起来，看那个最小化窗口里的报错" -ForegroundColor Red
}
Write-Host ""

if ($started.Count -gt 0) {
    $ids = ($started | ForEach-Object { $_.Process.Id }) -join ', '
    Write-Host "本次启动的进程 PID：$ids" -ForegroundColor DarkGray
}

if ($Detached) {
    Write-Host "已后台运行，本脚本退出。停止用：" -ForegroundColor Cyan
    foreach ($item in $started) {
        Write-Host "  Stop-Process -Id $($item.Process.Id) -Force   # $($item.Label)" -ForegroundColor DarkGray
    }
    exit 0
}

Write-Host "按回车结束这两个进程。"
Read-Host | Out-Null

foreach ($item in $started) {
    Stop-Process -Id $item.Process.Id -Force -ErrorAction SilentlyContinue
}
Write-Host "已停止。"
