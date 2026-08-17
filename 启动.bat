@echo off
chcp 65001 >nul
title App Store 评论智能分析工具
cd /d "%~dp0"

echo ========================================
echo   App Store 评论智能分析工具
echo ========================================
echo.

REM 激活 conda 环境
call conda activate review_analyzer
if errorlevel 1 (
    echo [错误] 无法激活 review_analyzer 环境
    echo 请确认 conda 已安装且环境名正确
    pause
    exit /b 1
)

echo [信息] 环境已激活，正在启动...
echo.

REM 启动 Streamlit
streamlit run app.py

if errorlevel 1 (
    echo.
    echo [错误] 启动失败，请检查 app.py 是否存在
    pause
)
