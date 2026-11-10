@echo off
rem ==========================================================================
rem  packets\lokal ni YANGILASH (internet bor kompyuterda, local\uv.lock
rem  o'zgargandan keyin). Loyihaning o'ziga tegmaydi: faqat shu papkaga yozadi.
rem
rem    1. local\uv.lock dan requirements.txt ni qayta chiqaradi;
rem    2. wheels\ ni tozalab, barcha .whl larni uv.lock dagi aniq havolalardan
rem       yuklaydi va sha256 ni tekshiradi (Windows x64, Python 3.12);
rem    3. build uchun hatchling va editables ni qo'shadi;
rem    4. Chromium'ni shu kompyuterdagi %LOCALAPPDATA%\ms-playwright dan oladi.
rem
rem  Ollama modellari, OllamaSetup.exe, uv va Python bu skript bilan
rem  yangilanmaydi: ular README.md dagi "Qo'lda yangilash" bo'limida.
rem ==========================================================================
setlocal EnableExtensions
chcp 65001 >nul
set "PK=%~dp0"
set "PK=%PK:~0,-1%"
set "APP=%PK%\..\..\local"
for %%i in ("%APP%") do set "APP=%%~fi"
set "UV=%PK%\uv\uv.exe"

echo [1/4] requirements.txt
pushd "%APP%"
"%UV%" export --frozen --all-groups --no-emit-workspace --no-hashes --no-header -o "%PK%\requirements.txt" || (popd & goto :fail)
popd

echo [2/4] wheels\*.whl
if exist "%PK%\wheels" rmdir /s /q "%PK%\wheels"
mkdir "%PK%\wheels"
py -3.12 "%PK%\tools\fetch_wheels.py" "%APP%\uv.lock" "%PK%\requirements.txt" "%PK%\wheels" || goto :fail

echo [3/4] hatchling, editables (build uchun)
py -3.12 -m pip download --disable-pip-version-check --only-binary=:all: --timeout 60 hatchling "editables>=0.3,<1" -d "%PK%\wheels" || goto :fail

echo [4/4] Chromium (Playwright)
"%APP%\.venv\Scripts\playwright.exe" install chromium || goto :fail
robocopy "%LOCALAPPDATA%\ms-playwright" "%PK%\playwright\ms-playwright" /MIR /R:1 /W:1 /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto :fail

echo.
echo Tayyor. packets papkasini fleshkaga ko'chirishingiz mumkin.
pause
exit /b 0

:fail
echo.
echo Yangilash to'xtadi. Yuqoridagi xabarni o'qing.
pause
exit /b 1
