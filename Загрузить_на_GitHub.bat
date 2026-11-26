@echo off
chcp 65001 > nul
title WebLab — Загрузка проекта на GitHub
cd /d "%~dp0"

echo ======================================================================
echo   WebLab Модуль 1: Загрузка и обновление файлов на GitHub
echo ======================================================================
echo.

:: 1. Поиск Git
where git >nul 2>nul
if %errorlevel% equ 0 goto :GIT_FOUND

if exist "C:\antiVS\Git\cmd\git.exe" (
    set "PATH=C:\antiVS\Git\cmd;%PATH%"
    goto :GIT_FOUND
)

if exist "C:\Program Files\Git\cmd\git.exe" (
    set "PATH=C:\Program Files\Git\cmd;%PATH%"
    goto :GIT_FOUND
)

if exist "%LOCALAPPDATA%\Programs\Git\cmd\git.exe" (
    set "PATH=%LOCALAPPDATA%\Programs\Git\cmd;%PATH%"
    goto :GIT_FOUND
)

echo [ОШИБКА] Программа Git не найдена!
echo Скачай и установи Git с https://git-scm.com/ и запусти этот файл снова.
pause
exit /b 1

:GIT_FOUND
for /f "delims=" %%V in ('git --version') do echo Найден %%V
echo.

:: 2. Настройка имени и email (если ещё не настроены)
:CHECK_NAME
set "GIT_NAME="
for /f "delims=" %%A in ('git config user.name 2^>nul') do set "GIT_NAME=%%A"
if defined GIT_NAME goto :CHECK_EMAIL

echo Первый запуск Git: нужно один раз указать твоё имя и email от GitHub.
set /p "GIT_NAME=Введи своё имя (латиницей, например Ivan): "
if "%GIT_NAME%"=="" goto :CHECK_NAME
git config --global user.name "%GIT_NAME%"

:CHECK_EMAIL
set "GIT_EMAIL="
for /f "delims=" %%A in ('git config user.email 2^>nul') do set "GIT_EMAIL=%%A"
if defined GIT_EMAIL goto :INIT_REPO

set /p "GIT_EMAIL=Введи свой email, привязанный к GitHub: "
if "%GIT_EMAIL%"=="" goto :CHECK_EMAIL
git config --global user.email "%GIT_EMAIL%"
echo.

:: 3. Инициализация локального репозитория
:INIT_REPO
if not exist ".git" (
    echo Создаю локальный Git-репозиторий...
    git init
)
git branch -M main

:: 4. Проверка ссылки на удалённый репозиторий (origin)
set "REMOTE_URL="
for /f "delims=" %%A in ('git remote get-url origin 2^>nul') do set "REMOTE_URL=%%A"
if defined REMOTE_URL goto :HAS_REMOTE

echo ----------------------------------------------------------------------
echo Репозиторий GitHub ещё не привязан.
echo 1. Открой https://github.com/new
echo 2. Введи имя (например: weblab-module1)
echo 3. Галочки README и .gitignore НЕ ставь -> нажми Create repository
echo 4. Скопируй HTTPS-ссылку (вида https://github.com/ЛОГИН/weblab-module1.git)
echo ----------------------------------------------------------------------
echo.
set "NEW_URL="
set /p "NEW_URL=Вставь ссылку на репозиторий GitHub и нажми Enter: "
if "%NEW_URL%"=="" (
    echo [ОТМЕНА] Ссылка не введена.
    pause
    exit /b 1
)
git remote add origin "%NEW_URL%"
if %errorlevel% neq 0 (
    echo [ОШИБКА] Не удалось добавить ссылку origin.
    pause
    exit /b 1
)
goto :STAGE_FILES

:HAS_REMOTE
echo Привязанный репозиторий: %REMOTE_URL%
set "UPD_URL="
set /p "UPD_URL=Нажми Enter чтобы загрузить в него, или вставь новую ссылку: "
if "%UPD_URL%"=="" goto :STAGE_FILES
git remote set-url origin "%UPD_URL%"

:: 5. Подготовка файлов и коммит
:STAGE_FILES
echo.
echo Подготавливаю файлы к отправке...
git add .
git status -s
echo.

git diff --cached --quiet
if %errorlevel% equ 0 goto :NO_CHANGES

set "COMMIT_MSG=Обновление WebLab"
set /p "COMMIT_MSG=Комментарий к обновлению (Enter = Обновление WebLab): "
git commit -m "%COMMIT_MSG%"
if %errorlevel% neq 0 (
    echo [ОШИБКА] Не удалось создать коммит.
    pause
    exit /b 1
)
goto :PUSH_REPO

:NO_CHANGES
echo Новых локальных изменений нет — проверяю отправку на GitHub...

:: 6. Отправка на GitHub
:PUSH_REPO
echo.
echo Отправка на GitHub (при первом входе откроется окно авторизации)...
git push -u origin main
if %errorlevel% neq 0 (
    echo.
    echo ======================================================================
    echo   [ОШИБКА ОТПРАВКИ] Возможные причины:
    echo   1. Репозиторий на GitHub не пустой ^(были созданы README или .gitignore^).
    echo      Создай новый пустой репозиторий без галочек, либо в терминале выполни:
    echo      git pull origin main --allow-unrelated-histories
    echo   2. Авторизация в браузере была отменена или ссылка введена с ошибкой.
    echo ======================================================================
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo   ГОТОВО! Все файлы успешно загружены на GitHub!
echo.
echo   Как запустить тренажёр прямо в браузере (GitHub Codespaces):
echo   1. Открой репозиторий на GitHub
echo   2. Нажми зелёную кнопку "^<^> Code" -^> вкладка "Codespaces"
echo   3. Нажми "Create codespace on main"
echo   4. В терминале внизу введи: python3 server.py --no-browser
echo ======================================================================
pause
