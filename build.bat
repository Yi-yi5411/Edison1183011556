@echo off
rem ============================================
rem  快速打包 EXE（使用现有的 report_generator.spec）
rem  产物: dist\主体结构检测数据管理录入系统V1.0\
rem  说明: 只清理本产物目录，不影响 dist 下其他旧版本
rem ============================================
cd /d "%~dp0"

set UPX_DIR=tools\upx\upx-5.0.2-win64
if not exist "%UPX_DIR%\upx.exe" set UPX_DIR=

echo [1/2] 清理旧产物目录...
if exist "dist\主体结构检测数据管理录入系统V1.0" rmdir /s /q "dist\主体结构检测数据管理录入系统V1.0"
if exist "build\report_generator" rmdir /s /q "build\report_generator"

echo [2/2] 开始打包 EXE（.venv PyInstaller 6.22.2 + UPX 体积优化）...
"%~dp0.venv\Scripts\python.exe" -m PyInstaller --noconfirm --upx-dir "%UPX_DIR%" report_generator.spec

if errorlevel 1 (
    echo 打包失败，请检查上方错误信息。
    pause
    exit /b 1
)

echo.
echo 打包成功！产物位于: dist\主体结构检测数据管理录入系统V1.0\
echo 运行方式: 直接双击 主体结构检测数据管理录入系统V1.0.exe
pause
