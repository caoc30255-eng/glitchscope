@echo off
chcp 65001 >nul
set PYTHONDONTWRITEBYTECODE=1
python -B "%~dp0..\..\..\board\start_preview.py"
pause
