@echo off
rem Web 版一键启动：后端 8765 + 已构建前端 dist
rem 访问地址：http://127.0.0.1:8765/
chcp 65001 >nul
set PY="C:\Program Files\python\python.exe"
set "ROOT=%~dp0"

if not exist "%ROOT%frontend\dist\index.html" (
  echo [错误] 未找到 frontend\dist\index.html
  echo 请先在 webapp\frontend 执行 pnpm build 构建前端。
  pause
  exit /b 1
)

start "Web后端(8765)" cmd /k "cd /d %ROOT%backend && %PY% -m uvicorn main:app --host 127.0.0.1 --port 8765"
timeout /t 3 >nul
start "" "http://127.0.0.1:8765/"
echo.
echo 已启动：http://127.0.0.1:8765/
echo 关闭方法：关闭“Web后端(8765)”命令行窗口
pause
