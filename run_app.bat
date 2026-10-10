@echo off
rem 用系统 Python 3.8 启动（该环境已装 paddlepaddle/paddleocr/requests，扫描识别可用）
rem 注意：.venv 是 Python 3.14，paddlepaddle 官方无对应 wheel，请勿用它跑扫描识别
"C:\Program Files\python\python.exe" "%~dp0run.py" %*
