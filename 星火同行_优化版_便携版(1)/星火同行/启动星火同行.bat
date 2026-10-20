@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if exist "%~dp0星火同行.exe" (
  start "" "%~dp0星火同行.exe"
  exit /b 0
)
echo 请打开发布文件夹中的星火同行.exe。
pause
