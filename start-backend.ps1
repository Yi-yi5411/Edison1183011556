# 启动 FastAPI 后端（默认 127.0.0.1:8765）
param(
    [string]$Python = $env:STRUCTURAL_PYTHON,
    [int]$Port = 0,
    [switch]$Detach
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "webapp\backend"

if (-not $Python) {
    foreach ($c in @("C:\Program Files\python\python.exe", "python")) {
        if ($c -eq "python" -or (Test-Path -LiteralPath $c)) { $Python = $c; break }
    }
}
if (-not $Python) { throw "未找到 Python，请用 -Python 指定或用 STRUCTURAL_PYTHON 环境变量" }

if ($Port -le 0) {
    $config = Join-Path $root "config\structural.toml"
    $Port = 8765
    if (Test-Path -LiteralPath $config) {
        $match = Select-String -LiteralPath $config -Pattern '^\s*port\s*=\s*(\d+)' | Select-Object -First 1
        if ($match) { $Port = [int]$match.Matches[0].Groups[1].Value }
    }
}

if ($Detach) {
    $logDir = Join-Path $root "data\logs"
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $outLog = Join-Path $logDir "backend.out.log"
    $errLog = Join-Path $logDir "backend.err.log"
    $proc = Start-Process -FilePath $Python -ArgumentList @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", $Port) -WorkingDirectory $backend -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    Write-Host ("后端已在后台启动：PID=" + $proc.Id)
    Write-Host ("日志： " + $outLog)
    exit 0
}

Write-Host ("启动后端： http://127.0.0.1:" + $Port + "/  （Ctrl+C 停止）")
Push-Location $backend
try {
    & $Python -m uvicorn main:app --host 127.0.0.1 --port $Port
} finally {
    Pop-Location
}
