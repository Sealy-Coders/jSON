@echo off
REM Odwołania2json — one-command start (Windows).
REM   run.bat            web UI on http://127.0.0.1:8000
REM   run.bat batch      input\**\*.pdf -> output\**\*.json
REM   run.bat case DIR   case report for one folder
REM   run.bat demo       built-in fictional case (no PDFs, no OCR)
REM   run.bat doctor     environment check
REM   run.bat test       pytest
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
set "PY=%VENV%\Scripts\python.exe"
set "PYTHONPATH=%ROOT%src;%PYTHONPATH%"
if "%PORT%"=="" set "PORT=8000"

set "CMD=%~1"
if "%CMD%"=="" set "CMD=web"

if exist "%PY%" goto deps
echo ^> Tworze srodowisko .venv
set "BASEPY="
for %%P in (py python python3) do (
  if not defined BASEPY (
    %%P -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "BASEPY=%%P"
  )
)
if not defined BASEPY (
  echo [BLAD] Nie znaleziono Pythona 3.11+. Pobierz z https://www.python.org/downloads/ ^(zaznacz "Add to PATH"^).
  exit /b 1
)
%BASEPY% -m venv "%VENV%" || (echo [BLAD] Nie udalo sie utworzyc venv. & exit /b 1)

:deps
set "REQ=requirements.txt"
if /i "%CMD%"=="test" set "REQ=requirements-dev.txt"
set "STAMP=%VENV%\.deps-%REQ%"
if exist "%STAMP%" goto run
echo ^> Instaluje zaleznosci (%REQ%) - tylko za pierwszym razem
"%PY%" -m pip install --quiet --upgrade pip >nul 2>&1
"%PY%" -m pip install --quiet -r "%REQ%" || (
  echo [BLAD] Instalacja pakietow nie powiodla sie. Sprawdz internet i uruchom ponownie run.bat
  exit /b 1
)
echo ok> "%STAMP%"

:run
if /i "%CMD%"=="web" (
  "%PY%" -m odwolania2json doctor || (echo Napraw bledy powyzej. & exit /b 1)
  echo ^> Interfejs: http://127.0.0.1:%PORT%   ^(Ctrl+C konczy^)
  start "" "http://127.0.0.1:%PORT%"
  "%PY%" -m uvicorn app.api:app --host 127.0.0.1 --port %PORT%
  exit /b %ERRORLEVEL%
)
if /i "%CMD%"=="batch" (
  if not exist input mkdir input
  "%PY%" -m odwolania2json process-input --input "%ROOT%input" --output "%ROOT%output"
  exit /b %ERRORLEVEL%
)
if /i "%CMD%"=="case"   ( "%PY%" -m odwolania2json process-case %2 %3 %4 %5 %6 %7 %8 %9 & exit /b %ERRORLEVEL% )
if /i "%CMD%"=="demo"   ( "%PY%" -m odwolania2json demo %2 %3 %4 & exit /b %ERRORLEVEL% )
if /i "%CMD%"=="doctor" ( "%PY%" -m odwolania2json doctor & exit /b %ERRORLEVEL% )
if /i "%CMD%"=="test"   ( "%PY%" -m pytest -q & exit /b %ERRORLEVEL% )
echo Nieznane polecenie: %CMD%. Dostepne: web ^| batch ^| case ^| demo ^| doctor ^| test
exit /b 2
