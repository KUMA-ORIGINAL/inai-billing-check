@echo off
rem One command for Windows: runs analyze.py with Python 3.10+.
rem Standard library only: no installation and no internet needed.
rem Usage:  run.bat [billing.csv ...] [--open] [--serve] [--llm] [other analyze.py options]
setlocal
set "ROOT=%~dp0"
if exist "%ROOT%.venv\Scripts\python.exe" goto venv
where py >nul 2>&1 && goto launcher
where python >nul 2>&1 && goto python
echo Python 3.10+ not found. Install it from https://www.python.org and run again.
exit /b 3

:venv
"%ROOT%.venv\Scripts\python.exe" "%ROOT%analyze.py" %*
exit /b %errorlevel%

:launcher
py -3 "%ROOT%analyze.py" %*
exit /b %errorlevel%

:python
python "%ROOT%analyze.py" %*
exit /b %errorlevel%
