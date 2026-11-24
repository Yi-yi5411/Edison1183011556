<#
.SYNOPSIS
    启动 DSH Web GUI（提取版运行时，端口 3660，带结构检测 dock / MCP / 技能）。

.DESCRIPTION
    deepseek-harness 源码仓库缺少 apps/cli 入口，无法从源码启动；
    本脚本改用从桌面版安装目录提取的完整 DSH 运行时
    （data\dsh_runtime\app，版本 0.2.2-rc.3，与桌面版 app.asar 一致）。

    启动后终端会打印带 token 的地址（形如 http://127.0.0.1:3660/?token=...），
    首次使用请先用浏览器打开该地址完成信任登录，之后 /harness 页的
    iframe（config/structural.toml [dsh].gui_url = http://127.0.0.1:3660）
    才能正常嵌入。

    dsh-worktable@0.5.1 的版本兼容豁免已通过
    `dsh plugin --profile web allow-version dsh-worktable@0.5.1
     --dsh-version 0.2.2-rc.3 --accept-risk` 授权。

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-dsh-web.ps1
#>
param(
    [int]$Port = 3660
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$env:TERM = "dumb"

$root = Split-Path $PSScriptRoot -Parent
$cli = Join-Path $root "data\dsh_runtime\app\dsh\node_modules\@deepseek-ai\dsh-desktop-host\lib\cli.js"
if (-not (Test-Path -LiteralPath $cli)) {
    Write-Host "找不到提取版 DSH：$cli" -ForegroundColor Red
    Write-Host "请先从桌面版 app.asar 提取（asar extract），见 docs/HARNESS_AGENT_ARCHITECTURE.md。" -ForegroundColor Yellow
    exit 1
}

$node = $null
# 优先用桌面版自带的 node（v24.21.0，与 DSH 要求一致）
$candidates = @(
    "D:\新建文件夹\resources\runtime\primary-runtime\dependencies\node\bin\node.exe",
    (Join-Path $env:DSH_HOME "dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe")
)
foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) { $node = $candidate; break }
}
if (-not $node) {
    $command = Get-Command node -ErrorAction SilentlyContinue
    if ($command) { $node = $command.Source }
}
if (-not $node) {
    Write-Host "找不到 node；请安装 Node 或确认桌面版 DSH 安装目录存在。" -ForegroundColor Red
    exit 1
}

Write-Host "启动 DSH Web GUI（提取版，端口 $Port）…" -ForegroundColor Cyan
Write-Host "启动完成后请用浏览器打开下方打印的 ?token= 地址完成信任登录。" -ForegroundColor DarkGray
& $node $cli --profile web --port $Port --no-open
exit $LASTEXITCODE
