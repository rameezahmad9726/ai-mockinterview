@echo off
cd /d "%~dp0..\frontend"
echo Starting Interveux frontend on http://localhost:3000
call npm.cmd run start
pause
