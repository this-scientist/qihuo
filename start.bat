@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem ===== 商品期货/期权研究系统 启动脚本（后端API + 前端页面同一服务）=====
set PORT=8799
set PY=.venv\Scripts\python.exe
set URL=http://127.0.0.1:%PORT%/index.html

if not exist "%PY%" (
    echo [错误] 未找到虚拟环境 .venv\Scripts\python.exe
    echo 请先执行: python -m venv .venv
    echo 然后安装依赖: .venv\Scripts\python.exe -m pip install pandas akshare
    pause
    exit /b 1
)

rem 端口已监听则视为服务已在运行，直接打开页面
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo [提示] 端口 %PORT% 已在监听，服务可能已启动，直接打开页面。
    start "" %URL%
    timeout /t 2 /nobreak >nul
    exit /b 0
)

echo [启动] Dashboard 服务端口 %PORT% ...
start "期货Dashboard" /D "%CD%" "%PY%" "期货\dashboard_server.py" --port %PORT%

rem 等待服务就绪后打开浏览器
timeout /t 4 /nobreak >nul
start "" %URL%
echo.
echo 服务已启动: %URL%
echo 期权扫描页: http://127.0.0.1:%PORT%/scanner.html
echo 停止服务: 关闭标题为"期货Dashboard"的窗口，或运行 stop.bat
pause
