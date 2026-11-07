@echo off
rem Double-click to start the local app on Windows.
rem Finds uv, installs or updates dependencies, then runs yoriqnoma-local on 127.0.0.1:8765.
rem Extra arguments are passed through to the launcher, e.g.:  startup.bat --dev
setlocal
cd /d "%~dp0"
title Yo'riqnoma - lokal dastur

call :find_uv
if not defined UV goto :no_uv

echo [1/2] Kutubxonalar tekshirilmoqda...
"%UV%" sync --quiet
if errorlevel 1 goto :sync_failed

echo [2/2] Dastur ishga tushmoqda: http://127.0.0.1:8765
echo       Brauzer o'zi ochiladi. To'xtatish: shu oynada Ctrl+C bosing yoki oynani yoping.
echo.
"%UV%" run yoriqnoma-local %*
if errorlevel 1 goto :run_failed
exit /b 0


rem uv may be installed without being on PATH (for example with "pip install uv"),
rem so look in the usual install folders before giving up.
:find_uv
set "UV="
for /f "delims=" %%i in ('where uv 2^>nul') do if not defined UV set "UV=%%i"
if defined UV exit /b 0
for %%p in (
    "%APPDATA%\Python\Python312\Scripts\uv.exe"
    "%USERPROFILE%\.local\bin\uv.exe"
    "%USERPROFILE%\.cargo\bin\uv.exe"
    "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe"
) do if not defined UV if exist "%%~p" set "UV=%%~p"
if defined UV exit /b 0
for %%c in ("py -3.12" "python") do if not defined UV (
    for /f "delims=" %%i in ('%%~c -c "import uv; print(uv.find_uv_bin())" 2^>nul') do set "UV=%%i"
)
exit /b 0


:no_uv
echo uv topilmadi.
echo O'rnating: https://docs.astral.sh/uv/  yoki terminalda:  py -3.12 -m pip install uv
echo Keyin shu faylni qayta ishga tushiring.
pause
exit /b 1

:sync_failed
echo.
echo Kutubxonalarni o'rnatib bo'lmadi. Yuqoridagi xabarni o'qing,
echo internet ulanishini tekshiring va qayta urinib ko'ring.
pause
exit /b 1

:run_failed
echo.
echo Dastur xato bilan to'xtadi. Yuqoridagi xabarni o'qing.
pause
exit /b 1
