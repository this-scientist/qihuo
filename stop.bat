@echo off
chcp 65001 >nul
rem ===== 停止 Dashboard 服务（端口 8799）=====
set PORT=8799
set FOUND=0

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo [停止] 结束进程 PID %%a
    taskkill /F /PID %%a >nul 2>&1
    set FOUND=1
)

if %FOUND%==0 echo [提示] 端口 %PORT% 没有正在监听的服务。
timeout /t 2 /nobreak >nul
