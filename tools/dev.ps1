# W1 本地开发环境：起两个 mock 服务
# 用法：
#   powershell -ExecutionPolicy Bypass -File tools/dev.ps1
#   powershell -ExecutionPolicy Bypass -File tools/dev.ps1 -BindHost 0.0.0.0

param(
    [string]$BindHost = "127.0.0.1"
)

Write-Host "启动 mock 接口 (8000) 与 mock 会话 (8090)..." -ForegroundColor Cyan
$api = Start-Process python -ArgumentList "tools/mock_api.py", "--host", $BindHost -PassThru -WindowStyle Minimized
$ws = Start-Process python -ArgumentList "tools/mock_ws.py", "--host", $BindHost -PassThru -WindowStyle Minimized

Write-Host ""
Write-Host "  接口  http://${BindHost}:8000/api/v1/health" -ForegroundColor Green
Write-Host "  会话  ws://${BindHost}:8090" -ForegroundColor Green
Write-Host ""
Write-Host "按回车结束这两个进程。"
Read-Host | Out-Null

Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
Stop-Process -Id $ws.Id -Force -ErrorAction SilentlyContinue
Write-Host "已停止。"
