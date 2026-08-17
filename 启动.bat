@echo off
chcp 65001 >nul
title App Store 评论智能分析工具
cd /d "%~dp0"

echo ========================================
echo   App Store 评论智能分析工具
echo ========================================
echo.

REM 检查 conda 是否可用
where conda >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 conda，请先安装 Anaconda/Miniconda
    echo 下载地址: https://docs.conda.io/en/latest/miniconda.html
    pause
    exit /b 1
)

REM 检查环境是否存在，不存在则创建
conda env list | findstr "review_analyzer" >nul
if errorlevel 1 (
    echo [信息] 首次运行，正在创建虚拟环境...
    call conda create -n review_analyzer python=3.12 -y
    call conda activate review_analyzer
    echo [信息] 正在安装依赖...
    pip install -r requirements.txt
) else (
    call conda activate review_analyzer
)

REM 检查 .env 是否存在
if not exist ".env" (
    echo [警告] 未找到 .env 文件，正在从 .env.example 复制...
    copy .env.example .env
    echo [提示] 请编辑 .env 文件，填入你的 DASHSCOPE_API_KEY
    echo [提示] 获取地址: https://dashscope.console.aliyun.com/
    notepad .env
)

echo [信息] 启动中...
streamlit run app.py

if errorlevel 1 (
    echo.
    echo [错误] 启动失败，请检查上方错误信息
    pause
)
