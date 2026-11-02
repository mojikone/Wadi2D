@echo off
rem Wadi2D installer, double-click this. SPDX-License-Identifier: GPL-3.0-or-later
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_wadi2d.ps1" %*
set WADI2D_EXIT=%ERRORLEVEL%
echo.
pause
exit /b %WADI2D_EXIT%
