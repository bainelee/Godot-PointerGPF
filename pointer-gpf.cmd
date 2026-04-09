@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0install\pointer-gpf.ps1" %*
exit /b %ERRORLEVEL%
