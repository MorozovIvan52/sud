@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
python run_parserpro_site.py
if errorlevel 1 (
  echo.
  echo Если "python" не найден, попробуйте: py run_parserpro_site.py
  pause
)
