# 启动独立 GPU OCR 服务（PaddleOCR 3.x + CUDA 12.9，Python 3.12）。
# 默认后台运行；-Foreground 时在当前窗口前台运行。
param(
    [int]$Port = 8770,
    [int]$WaitSeconds = 300,
    [switch]$Foreground
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv-ocr-gpu\Scripts\python.exe"
$script = Join-Path $root "scripts\ocr_gpu_service.py"
if (-not (Test-Path $python)) {
    throw "未找到 $python，请先运行 scripts\setup_ocr_gpu.ps1"
}
if (-not (Test-Path $script)) { throw "未找到 $script" }

if ($Foreground) {
    & $python $script --host 127.0.0.1 --port $Port
    exit $LASTEXITCODE
}

$logDir = Join-Path $root "data\logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$outLog = Join-Path $logDir "ocr_gpu_service.out.log"
$errLog = Join-Path $logDir "ocr_gpu_service.err.log"
$pidFile = Join-Path $logDir "ocr_gpu_service.pid"

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "端口 $Port 已在监听，先运行 scripts\stop_ocr_gpu.ps1 再启动。"
    exit 1
}

$proc = Start-Process -FilePath $python -ArgumentList @($script, "--host", "127.0.0.1", "--port", "$Port") -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
Set-Content -Path $pidFile -Value $proc.Id -Encoding ASCII
Write-Host "GPU OCR 服务已启动，PID=$($proc.Id)，端口=$Port，日志=$errLog"

$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    if ($proc.HasExited) {
        Write-Host "服务进程已退出，错误日志末尾："
        if (Test-Path $errLog) { Get-Content $errLog -Tail 30 }
        exit 1
    }
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
        if ($h.ready) {
            Write-Host "GPU OCR 就绪：device=$($h.device)，paddle=$($h.paddle)，paddleocr=$($h.paddleocr)"
            exit 0
        }
    } catch {
        # 首次运行正在下载 PP-OCRv5 模型，继续等。
    }
}
Write-Host "服务已启动但 $WaitSeconds 秒内未就绪；首次运行可能仍在下载模型。"
Write-Host "查看日志：Get-Content '$errLog' -Tail 40"
exit 2
