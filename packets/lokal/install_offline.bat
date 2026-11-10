@echo off
rem ==========================================================================
rem  Yo'riqnoma - lokal dasturni INTERNETSIZ o'rnatish (yangi kompyuterda bir marta).
rem
rem  Shu papkadagi tayyor fayllardan o'rnatadi:
rem    1. uv           - uv\uv.exe
rem    2. Python 3.12  - python\  (uv o'zi o'rnatadi, internet kerak emas)
rem    3. VC++ runtime - vcredist\vc_redist.x64.exe (faqat yo'q bo'lsa)
rem    4. Kutubxonalar - wheels\*.whl  ->  local\.venv
rem    5. Chromium     - playwright\ms-playwright  ->  %LOCALAPPDATA%\ms-playwright
rem    6. Ollama       - ollama\OllamaSetup.exe (yo'q bo'lsa) va ollama\models (gemma4:26b)
rem
rem  Keyin dasturni start_offline.bat bilan ishga tushiring.
rem  Qayta ishga tushirish xavfsiz: bori o'tkazib yuboriladi.
rem
rem  Parametrlar:  --no-models  modelni ko'chirmaslik (gemma4:26b, 17 GB)
rem                --no-ollama  Ollama'ni o'rnatmaslik va modellarni ko'chirmaslik
rem ==========================================================================
setlocal EnableExtensions
chcp 65001 >nul
title Yo'riqnoma - internetsiz o'rnatish
set "PK=%~dp0"
set "PK=%PK:~0,-1%"
if defined YORIQNOMA_APP_DIR (set "APP=%YORIQNOMA_APP_DIR%") else (set "APP=%PK%\..\..\local")
for %%i in ("%APP%") do set "APP=%%~fi"
set "UV=%PK%\uv\uv.exe"
set "UV_OFFLINE=1"
set "UV_NO_PROGRESS=1"
set "PYTHONUTF8=1"
set "DO_OLLAMA=1"
set "DO_MODELS=1"
for %%a in (%*) do (
    if /i "%%~a"=="--no-models" set "DO_MODELS=0"
    if /i "%%~a"=="--no-ollama" set "DO_OLLAMA=0"& set "DO_MODELS=0"
)

if not exist "%APP%\pyproject.toml" (
    echo Lokal dastur papkasi topilmadi: %APP%
    echo packets papkasi loyiha ildizida, local papkasi bilan yonma-yon turishi kerak.
    goto :fail
)
if not exist "%UV%" (
    echo uv topilmadi: %UV%
    goto :fail
)
echo Lokal dastur: %APP%
echo.

rem --- 1. uv ------------------------------------------------------------------
rem startup.bat uv ni PATH'dan yoki %USERPROFILE%\.local\bin dan qidiradi.
echo [1/6] uv
set "HAVE_UV="
for /f "delims=" %%i in ('where uv 2^>nul') do if not defined HAVE_UV set "HAVE_UV=%%i"
if not defined HAVE_UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "HAVE_UV=%USERPROFILE%\.local\bin\uv.exe"
if defined HAVE_UV (
    echo       Bor: %HAVE_UV%
) else (
    if not exist "%USERPROFILE%\.local\bin" mkdir "%USERPROFILE%\.local\bin"
    copy /y "%PK%\uv\uv.exe" "%USERPROFILE%\.local\bin\" >nul || goto :fail
    copy /y "%PK%\uv\uvx.exe" "%USERPROFILE%\.local\bin\" >nul
    copy /y "%PK%\uv\uvw.exe" "%USERPROFILE%\.local\bin\" >nul
    echo       O'rnatildi: %USERPROFILE%\.local\bin\uv.exe
)

rem --- 2. Python 3.12 ---------------------------------------------------------
echo [2/6] Python 3.12
"%UV%" python find 3.12 >nul 2>&1
if not errorlevel 1 (
    echo       Bor.
) else (
    rem uv Python arxivini internetdan emas, shu papkadan oladi (file:/// manzil).
    for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "([uri]$env:PK).AbsoluteUri + '/python'"`) do set "UV_PYTHON_INSTALL_MIRROR=%%i"
    "%UV%" python install 3.12 --no-bin || goto :fail
)

rem --- 3. Microsoft Visual C++ runtime (onnxruntime va opencv uchun) ---------
echo [3/6] Microsoft Visual C++ runtime
if exist "%SystemRoot%\System32\msvcp140.dll" (
    echo       Bor.
) else (
    echo       O'rnatilmoqda. Windows administrator ruxsatini so'rashi mumkin...
    start "" /wait "%PK%\vcredist\vc_redist.x64.exe" /install /passive /norestart
)

rem --- 4. Kutubxonalar (.whl) ------------------------------------------------
echo [4/6] Kutubxonalar (%PK%\wheels)
pushd "%APP%"
set "VENV_OK=0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>&1 && set "VENV_OK=1"
)
if "%VENV_OK%"=="0" (
    rem Boshqa kompyuterdan ko'chirilgan yoki buzilgan .venv qayta yaratiladi.
    "%UV%" venv --clear --python 3.12 .venv || (popd & goto :fail)
)
"%UV%" pip install --no-index --find-links "%PK%\wheels" -r "%PK%\requirements.txt" -e packages/schemas -e packages/scanner -e packages/core -e fixtures/demo_shop -e . || (popd & goto :fail)
rem startup.bat har safar "uv sync" qiladi: u internetsiz o'tishini tekshiramiz.
"%UV%" sync --quiet || (popd & goto :sync_failed)
popd
echo       Tayyor.

rem --- 5. Chromium (Playwright) ----------------------------------------------
echo [5/6] Chromium brauzeri
set "PW_DIR=%LOCALAPPDATA%\ms-playwright"
if defined PLAYWRIGHT_BROWSERS_PATH set "PW_DIR=%PLAYWRIGHT_BROWSERS_PATH%"
robocopy "%PK%\playwright\ms-playwright" "%PW_DIR%" /E /XO /R:1 /W:1 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail
echo       Tayyor: %PW_DIR%

rem --- 6. Ollama va modellar -------------------------------------------------
echo [6/6] Ollama
if "%DO_OLLAMA%"=="0" (
    echo       O'tkazib yuborildi ^(--no-ollama^).
    goto :done
)
call :find_ollama
if defined OLLAMA_EXE (
    echo       Bor: %OLLAMA_EXE%
) else (
    echo       O'rnatilmoqda ^(1-2 daqiqa^)...
    start "" /wait "%PK%\ollama\OllamaSetup.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
    call :find_ollama
    if not defined OLLAMA_EXE echo       Ollama o'rnatilmadi. Qo'lda: %PK%\ollama\OllamaSetup.exe
)
if "%DO_MODELS%"=="0" (
    echo       Modellar o'tkazib yuborildi ^(--no-models^).
    goto :done
)
set "MODELS_DIR=%USERPROFILE%\.ollama\models"
if defined OLLAMA_MODELS set "MODELS_DIR=%OLLAMA_MODELS%"
echo       Model ko'chirilmoqda: gemma4:26b (17 GB, fleshkadan 5-15 daqiqa)...
echo       Manzil: %MODELS_DIR%
robocopy "%PK%\ollama\models" "%MODELS_DIR%" /E /XO /R:1 /W:1 /NFL /NDL /NJH /NJS
if errorlevel 8 goto :fail
echo       Tayyor. Ollama allaqachon ishlayotgan bo'lsa, uni qayta ishga tushiring.

:done
echo.
echo ==========================================================================
echo  O'rnatish tugadi. Dasturni ishga tushirish: start_offline.bat
echo ==========================================================================
pause
exit /b 0

:find_ollama
set "OLLAMA_EXE="
for /f "delims=" %%i in ('where ollama 2^>nul') do if not defined OLLAMA_EXE set "OLLAMA_EXE=%%i"
if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA_EXE if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_EXE=%ProgramFiles%\Ollama\ollama.exe"
exit /b 0

:sync_failed
echo.
echo "uv sync" internetsiz o'tmadi. Ehtimol local\uv.lock yangilangan, packets esa eski.
echo Internet bor kompyuterda packets\lokal\tayyorlash.bat ni qayta ishga tushiring.
:fail
echo.
echo O'rnatish to'xtadi. Yuqoridagi xabarni o'qing.
pause
exit /b 1
