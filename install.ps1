# 工程检测harness —— 环境检查与配置初始化
# 用法： .\install.ps1            （检查依赖、补齐 config/structural.toml、打印 MCP 片段）
#        .\install.ps1 -Force     （覆盖已存在的 config/structural.toml）
param(
    [switch]$Force
)
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "项目根目录：$root"

# ── Python ──────────────────────────────────────────────
$python = $env:STRUCTURAL_PYTHON
if (-not $python) {
    $candidates = @("C:\Program Files\python\python.exe", "python")
    foreach ($c in $candidates) {
        if ($c -eq "python" -or (Test-Path -LiteralPath $c)) { $python = $c; break }
    }
}
if (-not $python) { Write-Warning "未找到 Python，请设置 STRUCTURAL_PYTHON"; exit 1 }
Write-Host ("Python：" + $python)
& $python -c "import sys; print(sys.version.split()[0])"

# openpyxl 等库随项目放在 report_generator/libs，检查时把它加入 sys.path
$probe = "import sys; sys.path.insert(0, r'$root\report_generator\libs'); import {0}"
$missing = @()
foreach ($mod in @("fastapi", "uvicorn", "requests", "docx", "openpyxl")) {
    & $python -c ($probe -f $mod) 2>$null
    if ($LASTEXITCODE -ne 0) { $missing += $mod }
}
if ($missing.Count -gt 0) {
    Write-Warning ("缺少依赖：" + ($missing -join ", "))
    Write-Host ("  安装： " + $python + " -m pip install " + ($missing -join " "))
} else {
    Write-Host "依赖检查通过（fastapi/uvicorn/requests/docx/openpyxl）"
}

# ── 配置 ────────────────────────────────────────────────
$configDir = Join-Path $root "config"
$configPath = Join-Path $configDir "structural.toml"
if (-not (Test-Path -LiteralPath $configDir)) { New-Item -ItemType Directory -Path $configDir | Out-Null }
if (-not (Test-Path -LiteralPath $configPath) -or $Force) {
    $template = @'
# 工程检测harness —— 运行配置（install.ps1 生成）
[server]
host = "127.0.0.1"
port = 8765
api_base = "http://127.0.0.1:8765/api"

[dsh]
gui_url = "http://127.0.0.1:6567"
mcp_server_name = "structural_inspection"

[paths]
data_dir = "data"
exports_dir = "report_generator/exports"
templates_dir = "data/templates"
'@
    Set-Content -LiteralPath $configPath -Value $template -Encoding UTF8
    Write-Host "已写入配置：$configPath"
} else {
    Write-Host "配置已存在：$configPath（-Force 可覆盖）"
}

# ── 数据目录 ────────────────────────────────────────────
foreach ($rel in @("data\projects", "data\projects\sessions", "data\templates",
                   "data\equipment", "data\personnel", "data\records",
                   "data\wiki", "data\tmp", "report_generator\exports")) {
    $p = Join-Path $root $rel
    if (-not (Test-Path -LiteralPath $p)) { New-Item -ItemType Directory -Path $p | Out-Null }
}
Write-Host "数据目录已就绪"

# ── CAD / 盈建科环境检查 ─────────────────────────────────
function Get-TomlValue($section, $key, $default = "") {
    if (-not (Test-Path -LiteralPath $configPath)) { return $default }
    $current = ""
    foreach ($line in Get-Content -LiteralPath $configPath) {
        $text = $line.Trim()
        if ($text -match '^\[(.+)\]$') { $current = $Matches[1]; continue }
        if ($current -ne $section) { continue }
        if ($text -match ('^' + [regex]::Escape($key) + '\s*=\s*"?(.*?)"?\s*$')) {
            return ($Matches[1] -replace '\\\\', '\')
        }
    }
    return $default
}

$cadExe = Get-TomlValue "cad" "acad_exe"
$tsdpDir = Get-TomlValue "cad" "tsdp_dir"
Write-Host ""
Write-Host "CAD 检查："
if ($cadExe -and (Test-Path -LiteralPath $cadExe)) { Write-Host "  AutoCAD: $cadExe" }
else { Write-Warning "  未找到 AutoCAD：$cadExe（可改 config/structural.toml 的 [cad].acad_exe）" }
if ($tsdpDir -and (Test-Path -LiteralPath $tsdpDir)) { Write-Host "  探索者   : $tsdpDir" }
else { Write-Warning "  未找到探索者：$tsdpDir（离线模式仍可写 DXF）" }
& $python -c "import win32com.client" 2>$null
if ($LASTEXITCODE -eq 0) { Write-Host "  pywin32  : 已安装（在线绘图可用）" }
else { Write-Warning "  pywin32  : 未安装（只能离线 DXF；需要时 pip install pywin32）" }

$yjkPython = Get-TomlValue "yjk" "python"
$yjkDir = Get-TomlValue "yjk" "install_dir"
Write-Host "盈建科检查："
if ($yjkPython -and (Test-Path -LiteralPath $yjkPython)) {
    Write-Host "  Python   : $yjkPython"
    & $yjkPython -c "import YJKAPI" 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Host "  YJKAPI   : 可导入" }
    else { Write-Warning "  YJKAPI   : 无法导入（请确认已按官方说明替换 SDK）" }
} else {
    Write-Warning "  未找到盈建科 Python：$yjkPython（可改 [yjk].python）"
}
if ($yjkDir -and (Test-Path -LiteralPath $yjkDir)) { Write-Host "  安装目录 : $yjkDir" }

# ── MCP 片段 ────────────────────────────────────────────
$mcp = Join-Path $root "webapp\mcp_server.py"
Write-Host ""
Write-Host "把下面这段并入 DSH profile 的 cordis.patch.yml（顶层数组追加）："
Write-Host ""
Write-Host @"
- insert:
    - id: structural-inspection-mcp
      name: "@deepseek-ai/dsh-mcp-client"
      config:
        serverName: structural_inspection
        transport: stdio
        command: '$python'
        args: ['-u', '$mcp']
        cwd: '$root'
        env:
          PYTHONIOENCODING: utf-8
          PYTHONUTF8: '1'
        toolCallTimeoutMs: 600000
        failOnStartupError: false
"@
Write-Host ""
Write-Host "可选：CAD / 盈建科两个独立 MCP 服务（片段见对应目录的 dsh-patch.yml）"
Write-Host "  - AutoCAD: $root\cad_agent\dsh-patch.yml"
Write-Host "  - YJK    : $root\integrations\yjk\dsh-patch.yml"
Write-Host ""
Write-Host "启动后端： .\start-backend.ps1"
