@echo off
rem ==========================================================================
rem  Yo'riqnoma - lokal dastur. Ikki marta bosing: hammasini o'zi qiladi.
rem
rem  1. uv ni topadi (PATH'da bo'lmasa ham); umuman yo'q bo'lsa, rozilik
rem     so'rab o'rnatadi. PATH o'zgartirilmaydi.
rem  2. Kutubxonalarni o'rnatadi yoki yangilaydi (uv sync). Python 3.12 ni
rem     ham uv o'zi yuklaydi.
rem  3. Saytni o'rganish uchun Chromium brauzerini o'rnatadi (bir marta).
rem  4. Ollama ishlamayotgan bo'lsa, uni ishga tushiradi.
rem  5. Dasturni 127.0.0.1:8765 da ochadi va brauzerni ochadi.
rem     Dastur allaqachon ishlayotgan bo'lsa, faqat brauzerni ochadi.
rem
rem  To'xtatish: shu oynada Ctrl+C bosing yoki oynani yoping.
rem  Qo'shimcha parametrlar dasturga uzatiladi, masalan: startup.bat --dev
rem ==========================================================================
setlocal EnableExtensions
cd /d "%~dp0"
title Yo'riqnoma - lokal dastur
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
set "APP_URL=http://127.0.0.1:8765/"
if defined YORIQNOMA_LOCAL_PORT set "APP_URL=http://127.0.0.1:%YORIQNOMA_LOCAL_PORT%/"
rem Ollama listens where OLLAMA_HOST says (default 127.0.0.1:11434).
set "OLLAMA_URL=http://127.0.0.1:11434"
if defined OLLAMA_HOST set "OLLAMA_URL=http://%OLLAMA_HOST%"
set "OLLAMA_URL=%OLLAMA_URL:http://http://=http://%"
set "OLLAMA_URL=%OLLAMA_URL:http://https://=https://%"
set "OPEN_BROWSER=1"
for %%a in (%*) do if /i "%%~a"=="--no-browser" set "OPEN_BROWSER=0"

rem --- 0. Already running? Then just open it. -------------------------------
call :url_ok "%APP_URL%"
if not errorlevel 1 (
    echo Dastur allaqachon ishlayapti: %APP_URL%
    if "%OPEN_BROWSER%"=="1" start "" "%APP_URL%"
    exit /b 0
)

rem --- 1. uv -------------------------------------------------------------------
call :find_uv
if not defined UV call :install_uv
if not defined UV goto :no_uv

rem --- 2. Libraries ------------------------------------------------------------
echo [1/4] Kutubxonalar tekshirilmoqda...
"%UV%" sync --quiet
if errorlevel 1 goto :sync_failed

rem --- 3. Chromium for Playwright (downloads only the first time) ------------
echo [2/4] Brauzer (Chromium) tekshirilmoqda...
"%UV%" run --quiet playwright install chromium
if errorlevel 1 goto :chromium_failed

rem --- 4. Ollama -------------------------------------------------------------
echo [3/4] Ollama tekshirilmoqda...
call :ensure_ollama

rem --- 5. The app --------------------------------------------------------------
echo [4/4] Dastur ishga tushmoqda: %APP_URL%
echo       Brauzer o'zi ochiladi. To'xtatish: shu oynada Ctrl+C bosing yoki oynani yoping.
echo.
"%UV%" run yoriqnoma-local %*
if errorlevel 1 goto :run_failed
exit /b 0


rem ==========================================================================
rem  Helpers
rem ==========================================================================

rem uv may be installed without being on PATH (for example with "pip install uv"),
rem so look in the usual install folders before giving up.
:find_uv
set "UV="
for /f "delims=" %%i in ('where uv 2^>nul') do if not defined UV set "UV=%%i"
if defined UV exit /b 0
for %%p in (
    "%USERPROFILE%\.local\bin\uv.exe"
    "%APPDATA%\Python\Python313\Scripts\uv.exe"
    "%APPDATA%\Python\Python312\Scripts\uv.exe"
    "%APPDATA%\Python\Python311\Scripts\uv.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\Scripts\uv.exe"
    "%USERPROFILE%\.cargo\bin\uv.exe"
    "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe"
) do if not defined UV if exist "%%~p" set "UV=%%~p"
if defined UV exit /b 0
for %%c in ("py -3.12" "py -3" "python") do if not defined UV (
    for /f "delims=" %%i in ('%%~c -c "import uv; print(uv.find_uv_bin())" 2^>nul') do set "UV=%%i"
)
exit /b 0

rem Official installer from astral.sh, into %USERPROFILE%\.local\bin, PATH untouched.
:install_uv
echo.
echo uv topilmadi. uv - dastur kutubxonalarini o'rnatadigan vosita (https://docs.astral.sh/uv/).
choice /c 12 /n /m "Hozir o'rnatilsinmi? Internet kerak. [1 - ha, 2 - yo'q]: "
if errorlevel 2 exit /b 0
powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:UV_NO_MODIFY_PATH='1'; irm https://astral.sh/uv/install.ps1 | iex"
call :find_uv
exit /b 0

rem errorlevel 0 when the URL answers, 1 otherwise.
:url_ok
powershell -NoProfile -Command "try { $null = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri '%~1'; exit 0 } catch { if ($_.Exception.Response) { exit 0 } else { exit 1 } }" >nul 2>&1
exit /b %errorlevel%

:ensure_ollama
call :url_ok "%OLLAMA_URL%/api/version"
if not errorlevel 1 (
    echo       Ollama ishlayapti.
    exit /b 0
)
set "OLLAMA_EXE="
for /f "delims=" %%i in ('where ollama 2^>nul') do if not defined OLLAMA_EXE set "OLLAMA_EXE=%%i"
if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA_EXE if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_EXE=%ProgramFiles%\Ollama\ollama.exe"
if not defined OLLAMA_EXE (
    echo       Ollama topilmadi. Yo'riqnoma matnini yozish uchun u kerak:
    echo       https://ollama.com/download dan o'rnating, keyin: ollama pull gemma4:26b
    echo       Blueprint va bundle natijalari Ollama'siz ham ishlaydi.
    exit /b 0
)
echo       Ollama ishga tushirilmoqda...
start "Ollama" /min "%OLLAMA_EXE%" serve
for /l %%n in (1,1,20) do (
    call :url_ok "%OLLAMA_URL%/api/version"
    if not errorlevel 1 (
        echo       Ollama ishlayapti.
        exit /b 0
    )
    ping -n 2 127.0.0.1 >nul
)
echo       Ollama 20 soniyada javob bermadi. Dastur sozlamalar sahifasida holatini ko'rsatadi.
exit /b 0


rem ==========================================================================
rem  Errors
rem ==========================================================================

:no_uv
echo.
echo uv topilmadi va o'rnatilmadi.
echo O'rnatish: https://docs.astral.sh/uv/  yoki terminalda:  py -3.12 -m pip install uv
echo Keyin shu faylni qayta ishga tushiring.
pause
exit /b 1

:sync_failed
echo.
echo Kutubxonalarni o'rnatib bo'lmadi. Yuqoridagi xabarni o'qing,
echo internet ulanishini tekshiring va qayta urinib ko'ring.
pause
exit /b 1

:chromium_failed
echo.
echo Chromium brauzerini o'rnatib bo'lmadi. Internet ulanishini tekshiring.
echo Qo'lda: shu papkada  uv run playwright install chromium
pause
exit /b 1

:run_failed
echo.
echo Dastur xato bilan to'xtadi. Yuqoridagi xabarni o'qing.
pause
exit /b 1
