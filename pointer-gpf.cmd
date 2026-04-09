@echo off
setlocal
if exist "%~dp0pointer_gpf\install\pointer-gpf.ps1" (
  powershell -ExecutionPolicy Bypass -File "%~dp0pointer_gpf\install\pointer-gpf.ps1" %*
) else (
  powershell -ExecutionPolicy Bypass -File "%~dp0install\pointer-gpf.ps1" %*
)
exit /b %ERRORLEVEL%
