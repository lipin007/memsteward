@echo off
REM MemSteward 本地版 Win64 打包 (双轨产物)
REM 轨1 src: 源码包 (开发/集成用)
REM 轨2 portable: 便携包 (run.bat 一键 venv+依赖, 开箱即用)
REM 用法: 在 C-本地版 目录下运行 pack_win64.bat
setlocal
set VER=2026.11.19
set STAGE=diststage
set OUT1=distmemsteward-local-win64-%VER%-src.zip
set OUT2=distmemsteward-local-win64-%VER%-portable.zip
if exist dist rmdir /s /q dist
mkdir %STAGE%memsteward-local

robocopy src %STAGE%memsteward-localsrc /E /XF *.bak* *.pyc /XD __pycache__ .pytest_cache >nul
robocopy kernel %STAGE%memsteward-localkernel /E /XF *.bak* *.pyc /XD __pycache__ .pytest_cache >nul
robocopy sdk %STAGE%memsteward-localsdk /E /XF *.bak* *.pyc /XD __pycache__ .pytest_cache >nul
robocopy examples %STAGE%memsteward-localexamples /E /XF *.bak* *.pyc /XD __pycache__ >nul
copy MANIFEST.md %STAGE%memsteward-local >nul
copy README.md %STAGE%memsteward-local >nul
copy CAPABILITY_INDEX.md %STAGE%memsteward-local >nul
copy config_llm_connection.env.example %STAGE%memsteward-local >nul

REM ---- 轨1: 源码包 (先打, 不含运行引导) ----
powershell -Command "Compress-Archive -Path '%STAGE%memsteward-local' -DestinationPath '%OUT1%' -Force"

REM ---- 轨2: 便携包 (补 run.bat + requirements 后再打) ----
copy /Y deployun.bat %STAGE%memsteward-localun.bat >nul
copy /Y sdkequirements.txt %STAGE%memsteward-localequirements.txt >nul
powershell -Command "Compress-Archive -Path '%STAGE%memsteward-local' -DestinationPath '%OUT2%' -Force"

echo.
echo 双轨产物完成:
echo   %OUT1%  (源码包)
echo   %OUT2%  (便携包: run.bat 一键环境)
dir dist*.zip
endlocal
