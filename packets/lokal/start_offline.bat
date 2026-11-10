@echo off
rem ==========================================================================
rem  Yo'riqnoma - lokal dasturni INTERNETSIZ ishga tushirish.
rem  Avval bir marta install_offline.bat ni ishga tushiring.
rem
rem  local\startup.bat ni internetsiz rejimda chaqiradi: uv hech narsani
rem  internetdan yuklamaydi, faqat o'rnatilganini tekshiradi.
rem  Parametrlar startup.bat ga uzatiladi, masalan: start_offline.bat --dev
rem ==========================================================================
setlocal EnableExtensions
set "UV_OFFLINE=1"
set "UV_NO_PROGRESS=1"
set "PATH=%USERPROFILE%\.local\bin;%~dp0uv;%PATH%"
call "%~dp0..\..\local\startup.bat" %*
