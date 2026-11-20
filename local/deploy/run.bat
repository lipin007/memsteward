@echo off
REM 便携启动: 首次运行自动建 venv 装依赖, 之后直接启动
setlocal
cd /d "%~dp0"
if not exist .venv (
  echo [setup] 创建 Python 虚拟环境...
  python -m venv .venv
  .venvScriptspip install -r requirements.txt
)
set LLM_ARM_HOST=http://localhost:8082
.venvScriptspython srcmemsteward_local.py %*
endlocal
