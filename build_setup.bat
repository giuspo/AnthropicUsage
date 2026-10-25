@echo off
echo ============================================================
echo   Compilazione Claude Code Usage Widget - Windows Setup
echo ============================================================

uv run python packaging\build_windows.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================================
    echo   SUCCESSO! Il file di setup e' stato generato in:
    echo   dist\ClaudeUsageWidget-Setup.exe
    echo ============================================================
) else (
    echo.
    echo [!] Errore durante la compilazione.
)
pause
