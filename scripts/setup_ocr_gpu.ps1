# 安装 PaddleOCR 3.x + CUDA 12.9 的独立 GPU 环境（Python 3.12）。
# 主程序仍用 Python 3.8；GPU 识别由 scripts/ocr_gpu_service.py 提供。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\setup_ocr_gpu.ps1
#   powershell ... -PaddleWheel C:\path\paddlepaddle_gpu-3.3.1-cp312-cp312-win_amd64.whl
#   powershell ... -PaddleWheel ... -Wheelhouse C:\path\wheelhouse  # 离线/加速安装依赖
param(
    [string]$PythonExe = "",
    [string]$PaddleWheel = "",
    [string]$Wheelhouse = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv-ocr-gpu"
$venvPy = Join-Path $venv "Scripts\python.exe"

# 本机 Windows 注册表里配置了一个未运行的代理，pip 直连需要绕过它。
$env:NO_PROXY = "*"
$env:no_proxy = "*"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"

if (-not $PythonExe) {
    $candidates = @(
        "C:\Users\Administrator\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe",
        "D:\python\python.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            $v = & $c -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($v -eq "3.12") { $PythonExe = $c; break }
        }
    }
    if (-not $PythonExe) {
        $v = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0) { $PythonExe = $v.Trim() }
    }
}
if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    throw "未找到 Python 3.12。请安装 Python 3.12，或传 -PythonExe <python.exe>。"
}

Write-Host "Python: $PythonExe"
if (-not (Test-Path $venvPy)) {
    & $PythonExe -m venv $venv
}
if (-not (Test-Path $venvPy)) { throw "创建虚拟环境失败：$venv" }

& $venvPy -m pip install --upgrade pip
$pipArgs = @("--no-cache-dir")
if ($Wheelhouse) {
    if (-not (Test-Path $Wheelhouse)) { throw "wheelhouse 不存在：$Wheelhouse" }
    $pipArgs += @("--find-links", $Wheelhouse)
}
if ($PaddleWheel -and (Test-Path $PaddleWheel)) {
    Write-Host "从本地 wheel 安装 PaddlePaddle GPU：$PaddleWheel"
    & $venvPy -m pip install @pipArgs $PaddleWheel
} else {
    Write-Host "从 Paddle 官方 cu129 源安装 paddlepaddle-gpu==3.3.1 ..."
    & $venvPy -m pip install @pipArgs paddlepaddle-gpu==3.3.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
}
if ($LASTEXITCODE -ne 0) { throw "PaddlePaddle GPU 安装失败" }

Write-Host "安装 PaddleOCR 3.x ..."
# 国内网络优先用清华镜像；失败再走官方 PyPI。
& $venvPy -m pip install @pipArgs paddleocr==3.7.0 -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) {
    & $venvPy -m pip install @pipArgs paddleocr==3.7.0
}
if ($LASTEXITCODE -ne 0) { throw "PaddleOCR 安装失败" }

Write-Host "校验 GPU ..."
& $venvPy -c "import paddle; print('paddle', paddle.__version__); print('compiled_with_cuda', paddle.device.is_compiled_with_cuda()); print('gpu_count', paddle.device.cuda.device_count())"
if ($LASTEXITCODE -ne 0) { throw "Paddle GPU 校验失败" }

Write-Host ""
Write-Host "安装完成。启动 GPU OCR 服务："
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\start_ocr_gpu.ps1"
Write-Host "首次识别会下载 PP-OCRv5 mobile 模型到 data\models\paddlex。"
