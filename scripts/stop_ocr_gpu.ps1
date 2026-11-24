# 停止 scripts/start_ocr_gpu.ps1 启动的 GPU OCR 服务。
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $root "data\logs\ocr_gpu_service.pid"
if (-not (Test-Path $pidFile)) {
    Write-Host "没有 PID 文件，服务可能未由脚本启动。"
    exit 0
}
$procId = [int](Get-Content $pidFile -Raw).Trim()
$p = Get-Process -Id $procId -ErrorAction SilentlyContinue
if ($p) {
    Stop-Process -Id $procId -Force
    Write-Host "已停止 GPU OCR 服务 PID=$procId"
} else {
    Write-Host "进程 $procId 已不存在"
}
Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
