@echo off
setlocal
cd /d "%~dp0"

if not exist "%~dp0runtime\pythonw.exe" goto incomplete
if not exist "%~dp0app\portable_start.pyw" goto incomplete
if not exist "%~dp0app\garden_jihan\launcher.py" goto incomplete

set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "GOJ_DISTRIBUTION=portable-browser"
start "" /d "%~dp0" "%~dp0runtime\pythonw.exe" "%~dp0app\portable_start.pyw"
exit /b 0

:incomplete
echo.
echo Garden of Jihan could not start because this folder is incomplete.
echo.
echo Extract the entire ZIP to a normal folder, then double-click this file again.
echo Opening START-HERE.txt for help...
start "" "%SystemRoot%\System32\notepad.exe" "%~dp0START-HERE.txt"
pause
exit /b 1
