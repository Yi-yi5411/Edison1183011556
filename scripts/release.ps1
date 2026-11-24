# 版本发布：改版本号 → 写 CHANGELOG → 跑自检 → 打 zip
# 用法：
#   .\scripts\release.ps1 -Version 1.0.1 -Note "P8 工程化"
#   .\scripts\release.ps1 -Version 1.0.1 -DryRun
#   .\scripts\release.ps1 -Version 1.0.1 -SkipTests -NoZip
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Note = "",
    [string]$ConfigPath = "",
    [string]$ChangelogPath = "",
    [string]$DistDir = "",
    [switch]$SkipTests,
    [switch]$NoZip,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $ConfigPath) { $ConfigPath = Join-Path $root "config\structural.toml" }
if (-not $ChangelogPath) { $ChangelogPath = Join-Path $root "CHANGELOG.md" }
if (-not $DistDir) { $DistDir = Join-Path $root "dist" }
if (-not $Note) { $Note = "版本发布" }

if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "版本号必须是 x.y.z（收到：$Version）"
}
if (-not (Test-Path -LiteralPath $ConfigPath)) { throw "找不到配置：$ConfigPath" }
if (-not (Test-Path -LiteralPath $ChangelogPath)) { throw "找不到 CHANGELOG：$ChangelogPath" }

$utf8 = New-Object System.Text.UTF8Encoding($true)
$nl = [Environment]::NewLine
$toml = [System.IO.File]::ReadAllText($ConfigPath, [System.Text.Encoding]::UTF8)
$lines = $toml -split "\r?\n"

# ── 在 [app] 段内改 version ──
$inApp = $false
$bumped = $false
for ($i = 0; $i -lt $lines.Count; $i++) {
    $text = $lines[$i].Trim()
    if ($text -eq "[app]") { $inApp = $true; continue }
    if ($inApp -and $text.StartsWith("[") -and $text.EndsWith("]")) { break }
    if ($inApp -and $text -match '^version\s*=') {
        $lines[$i] = 'version = "' + $Version + '"'
        $bumped = $true
        break
    }
}
if (-not $bumped) { throw "配置 [app] 段缺少 version 键：$ConfigPath" }
$updated = $lines -join $nl

# ── CHANGELOG 顶部插入条目（按行处理，不依赖多行正则）──
$date = Get-Date -Format "yyyy-MM-dd"
$logLines = ([System.IO.File]::ReadAllText($ChangelogPath, [System.Text.Encoding]::UTF8)) -split "\r?\n"
$titleIndex = -1
for ($i = 0; $i -lt $logLines.Count; $i++) {
    if ($logLines[$i].Trim() -eq "# 变更记录") { $titleIndex = $i; break }
}
if ($titleIndex -lt 0) { throw "CHANGELOG 缺少【# 变更记录】标题" }
$heading = "## v" + $Version + " — " + $date
$exists = @($logLines | Where-Object { $_.Trim().StartsWith("## v" + $Version + " ") })
if ($exists.Count -gt 0) { throw "CHANGELOG 已存在 v$Version，先改版本号" }
$entry = @("", $heading, "", ("- " + $Note), "")
$newLines = @()
$newLines += $logLines[0..$titleIndex]
$newLines += $entry
if ($titleIndex + 1 -lt $logLines.Count) { $newLines += $logLines[($titleIndex + 1)..($logLines.Count - 1)] }
$newLog = $newLines -join $nl

Write-Host "版本：$Version"
Write-Host "  配置：$ConfigPath"
Write-Host "  变更：$ChangelogPath"
Write-Host "  输出：$DistDir"
if ($DryRun) {
    Write-Host "（DryRun：不写文件、不跑测试、不打 zip）"
    exit 0
}

[System.IO.File]::WriteAllText($ConfigPath, $updated, $utf8)
[System.IO.File]::WriteAllText($ChangelogPath, $newLog, $utf8)
Write-Host "已更新版本号与 CHANGELOG"

if (-not $SkipTests) {
    & (Join-Path $root "scripts\check.ps1")
    if ($LASTEXITCODE -ne 0) { throw "自检失败，发布中止" }
}

if (-not $NoZip) {
    $stage = Join-Path ([System.IO.Path]::GetTempPath()) ("release_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $stage | Out-Null
    $items = @("webapp", "report_generator", "cad_agent", "integrations",
               "config", "docs", "scripts", "prompt",
               "install.ps1", "start-backend.ps1", "README.md",
               "CHANGELOG.md", "requirements.txt", "requirements-web.txt")
    foreach ($item in $items) {
        $source = Join-Path $root $item
        if (-not (Test-Path -LiteralPath $source)) { continue }
        Copy-Item -LiteralPath $source -Destination $stage -Recurse -Force
    }
    Get-ChildItem -LiteralPath $stage -Recurse -Force -Directory |
        Where-Object { $_.Name -in @("__pycache__", "node_modules", ".venv", "dist", "data") } |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
    Get-ChildItem -LiteralPath $stage -Recurse -Force -File -Include "*.pyc", "*.pyo" |
        Remove-Item -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
    $zip = Join-Path $DistDir ("structural_inspection-" + $Version + ".zip")
    if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -Force
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host ("已打开发包：" + $zip + "（" + [math]::Round((Get-Item $zip).Length / 1MB, 1) + " MB）")
}
Write-Host "发布完成：v$Version"
