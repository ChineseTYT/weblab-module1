@echo off
chcp 65001 > nul
title WebLab Модуль 1 — Тренажёр HTTP, Cookies, Статус-кодов и DevTools
cd /d "%~dp0"

echo ======================================================================
echo   WebLab Модуль 1: Запуск локального учебного тренажёра
echo ======================================================================
echo.

set "PY_EXE="

if exist "%LOCALAPPDATA%\Python\pythoncore-3.15-64\python.exe" (
    set "PY_EXE=%LOCALAPPDATA%\Python\pythoncore-3.15-64\python.exe"
    goto :FOUND
)

if exist "%LOCALAPPDATA%\Python\bin\python.exe" (
    set "PY_EXE=%LOCALAPPDATA%\Python\bin\python.exe"
    goto :FOUND
)

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    if exist "%%D\python.exe" (
        set "PY_EXE=%%D\python.exe"
        goto :FOUND
    )
)

for /d %%D in ("C:\Python*") do (
    if exist "%%D\python.exe" (
        set "PY_EXE=%%D\python.exe"
        goto :FOUND
    )
)

where py >nul 2>nul
if %errorlevel% equ 0 (
    set "PY_EXE=py -3"
    goto :FOUND
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    set "PY_EXE=python"
    goto :FOUND
)

echo [ОШИБКА] Python не найден на компьютере.
pause
exit /b 1

:FOUND
echo Найден Python: %PY_EXE%
echo Запускаю учебный сервер (браузер откроется автоматически)...
echo.

if "%PY_EXE%"=="py -3" (
    py -3 server.py
) else (
    "%PY_EXE%" server.py
)

if %errorlevel% neq 0 (
    echo.
    echo Сервер завершился с ошибкой (код %errorlevel%).
    pause
)
