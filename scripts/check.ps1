# 一键回归：单元/集成测试 + manifest 校验 + 工具面计数 + 目录卫生
# 用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
#   .\scripts\check.ps1 -SkipVenv          # 只跑系统 Python 3.8
param(
    [switch]$SkipVenv
)
$ErrorActionPreference = "Continue"
# 统一 UTF-8：Python 3.8 在 cp936 控制台输出中文/㎡ 会 UnicodeEncodeError
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$python = $env:STRUCTURAL_PYTHON
if (-not $python) {
    foreach ($c in @("C:\Program Files\python\python.exe", "python")) {
        if ($c -eq "python" -or (Test-Path -LiteralPath $c)) { $python = $c; break }
    }
}
if (-not $python) { throw "未找到 Python，请设置 STRUCTURAL_PYTHON" }
$venv = Join-Path $root ".venv\Scripts\python.exe"
$hasVenv = (-not $SkipVenv) -and (Test-Path -LiteralPath $venv)

$tests = @(
    "tests/test_cad_agent.py", "tests/test_yjk_integration.py", "tests/test_human_loop.py",
    "tests/test_request_log.py", "tests/test_memory.py", "tests/test_report_facts.py", "tests/test_config_smoke.py",
    "tests/test_projects_smoke.py",
    "tests/test_record_reuse.py", "tests/test_equipment_match.py", "tests/test_template_match.py",
    "tests/test_norm_retrieval.py", "tests/test_manifest_smoke.py", "tests/test_manifests_all.py",
    "tests/test_manifest_params.py", "tests/test_mcp_tool_surface.py",
    "tests/test_scan_jobs_smoke.py", "tests/test_ingest_smoke.py",
    "tests/test_mcp_upload.py", "tests/test_excel_import_smoke.py",
    "tests/test_assessment_smoke.py", "tests/test_record_assessment.py", "tests/test_report_smoke.py", "tests/test_report_item_names.py",
    "tests/test_report_preflight.py", "tests/test_template_library_smoke.py"
)

$failures = @()
function Invoke-Suite($exe, $label, $test) {
    Write-Host ("[" + $label + "] " + $test) -NoNewline
    $output = & $exe -u $test 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  FAIL" -ForegroundColor Red
        ($output -split "\r?\n") | Where-Object { $_ -match "^FAIL " } |
            Select-Object -First 5 | ForEach-Object { Write-Host ("    " + $_) }
        return $false
    }
    Write-Host "  ok"
    return $true
}

$started = Get-Date
foreach ($test in $tests) {
    if (-not (Invoke-Suite $python "3.8" $test)) { $failures += ($test + " (3.8)") }
    if ($hasVenv) {
        if (-not (Invoke-Suite $venv "3.14" $test)) { $failures += ($test + " (3.14)") }
    }
}

Write-Host ""
Write-Host "── manifest / 工具面 ──────────────────────────"
Push-Location (Join-Path $root "report_generator")
& $python -m structural_items validate *> $null
if ($LASTEXITCODE -ne 0) { $failures += "structural_items validate" }
& $python -m tools.build_manifests --check *> $null
if ($LASTEXITCODE -ne 0) { $failures += "build_manifests --check" }
Pop-Location

$toolsOut = & $python -u (Join-Path $root "webapp\mcp_server.py") --list-tools 2>&1 | Out-String
$toolCount = ([regex]::Matches($toolsOut, '"name"')).Count
Write-Host ("MCP 工具数：" + $toolCount)

$strays = @(Get-ChildItem -LiteralPath $root -Directory |
    Where-Object { $_.Name -match "^(assessment_report_|report_smoke_)" })
if ($strays.Count -gt 0) {
    $failures += ("目录卫生：残留 " + $strays.Count + " 个测试目录")
    $strays | Select-Object -First 5 | ForEach-Object { Write-Host ("  残留：" + $_.Name) }
}

$elapsed = [int]((Get-Date) - $started).TotalSeconds
Write-Host ""
Write-Host ("套件：" + $tests.Count + "，耗时 " + $elapsed + " 秒")
if ($failures.Count -gt 0) {
    Write-Host ("失败 " + $failures.Count + " 项：") -ForegroundColor Red
    $failures | ForEach-Object { Write-Host ("  - " + $_) -ForegroundColor Red }
    exit 1
}
Write-Host "全部通过" -ForegroundColor Green
exit 0
