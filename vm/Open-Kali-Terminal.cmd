@echo off
setlocal
call "%~dp0KaliVM.cmd" terminal
set "kali_exit_code=%ERRORLEVEL%"
if not "%kali_exit_code%"=="0" pause
exit /b %kali_exit_code%
