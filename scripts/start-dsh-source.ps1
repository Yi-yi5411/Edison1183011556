<#
.SYNOPSIS
    启动带「结构检测」dock 的 DSH 源码版（Web GUI）。

.DESCRIPTION
    deepseek-harness 仓库需要先构建客户端插件：
        pnpm --filter @deepseek-ai/dsh-client-ui-structural bundle
    本脚本只负责启动并打印带 token 的地址；插件未构建时 DSH 仍可启动，
    但看不到 dock。

.PARAMETER Port
    Web GUI 端口，默认 3654（避免与已安装 DSH 的 3642 冲突）。

.PARAMETER Repo
    deepseek-harness 仓库路径，默认取本项目的同级目录。

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-dsh-source.ps1
#>
param(
    [int]$Port = 3654,
    [string]$Repo = ""
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

if (-not $Repo) {
    $Repo = Join-Path (Split-Path $PSScriptRoot -Parent) "deepseek-harness"
}
if (-not (Test-Path -LiteralPath (Join-Path $Repo "apps\cli\lib\bin.js"))) {
    Write-Host "找不到 DSH 源码：$Repo" -ForegroundColor Red
    Write-Host "请用 -Repo 指定 deepseek-harness 仓库路径。" -ForegroundColor Yellow
    exit 1
}

$node = $null
if ($env:DSH_HOME) {
    $candidate = Join-Path $env:DSH_HOME "dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
    if (Test-Path -LiteralPath $candidate) { $node = $candidate }
}
if (-not $node) {
    $command = Get-Command node -ErrorAction SilentlyContinue
    if ($command) { $node = $command.Source }
}
if (-not $node) {
    Write-Host "找不到 node；请安装 Node 或设置 DSH_HOME。" -ForegroundColor Red
    exit 1
}

$plugin = Join-Path $Repo "packages\client\ui-structural\lib\client.js"
if (-not (Test-Path -LiteralPath $plugin)) {
    Write-Host "提示：结构检测 dock 尚未构建，先运行：" -ForegroundColor Yellow
    Write-Host "  pnpm --filter @deepseek-ai/dsh-client-ui-structural bundle" -ForegroundColor Yellow
}

Write-Host "启动 DSH 源码版：$Repo（端口 $Port）" -ForegroundColor Cyan
Write-Host "浏览器打开终端打印的 ?token= 地址；Ctrl+C 停止。" -ForegroundColor DarkGray
& $node (Join-Path $Repo "apps\cli\lib\bin.js") --profile web --port $Port
exit $LASTEXITCODE
