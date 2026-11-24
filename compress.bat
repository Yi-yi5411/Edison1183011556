@echo off
rem ============================================
rem  将 dist 下的成品压缩成 .7z
rem  优先使用系统 7-Zip，否则使用项目内置 tools\7z\7zr.exe
rem ============================================
cd /d "%~dp0"

set SRC=dist
set OUT=工程检测harness.7z
set "SEVENZIP=C:\Program Files\7-Zip\7z.exe"
if not exist "%SEVENZIP%" set "SEVENZIP=%~dp0tools\7z\7zr.exe"

if not exist "%SEVENZIP%" (
    echo 未找到 7-Zip，也缺少内置工具 tools\7z\7zr.exe。
    pause
    exit /b 1
)

if not exist "%SRC%" (
    echo 未找到 %SRC%，请先执行 build.bat。
    pause
    exit /b 1
)

echo 正在压缩 %SRC% 为 %OUT% ...
"%SEVENZIP%" a -t7z -mx=9 -mmt=on "%OUT%" "%SRC%"

echo.
echo 压缩完成: %OUT%
pause
