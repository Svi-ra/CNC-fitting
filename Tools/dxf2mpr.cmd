@echo off
rem ---------------------------------------------------------------------
rem Drag one or more DXF files (or a folder) onto this file.
rem The MPR programs are written to an "MPR" folder next to the first
rem file that was dropped, together with convert-log.csv.
rem ---------------------------------------------------------------------
setlocal

if "%~1"=="" (
    echo Drag DXF files - or a folder full of them - onto this file.
    echo.
    pause
    exit /b 1
)

set "OUT=%~dp1MPR"
if not exist "%OUT%" mkdir "%OUT%"

python "%~dp0dxf2mpr.py" %* -o "%OUT%" --log "%OUT%\convert-log.csv"
set RC=%ERRORLEVEL%

echo.
echo Output folder: %OUT%
if not "%RC%"=="0" echo Some files could not be converted - see the list above.
echo.
pause
exit /b %RC%
