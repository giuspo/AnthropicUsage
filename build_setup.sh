#!/usr/bin/env bash
# ==============================================================================
# Claude & Antigravity Usage Widget - Linux / Ubuntu Build Script
# Compiles PyInstaller ELF standalone binary, native .deb package, and tarball
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo " Compilazione Claude & Antigravity Usage Widget - Linux"
echo "============================================================"

# Check Python environment
PYTHON_CMD=""
if [ -f "$SCRIPT_DIR/.venv/bin/python3" ]; then
    PYTHON_CMD="$SCRIPT_DIR/.venv/bin/python3"
elif which uv >/dev/null 2>&1; then
    PYTHON_CMD="uv run python"
elif which python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
else
    echo "[!] Errore: Python 3 non trovato."
    exit 1
fi

$PYTHON_CMD packaging/build_linux.py

if [ $? -eq 0 ]; then
    echo ""
    echo "============================================================"
    echo " SUCCESSO! I pacchetti per Linux sono stati generati in:"
    echo " 1. Binario standalone: dist/claude-usage-widget"
    echo " 2. Pacchetto Debian/Ubuntu: dist/claude-usage-widget_*.deb"
    echo " 3. Archivio distribuibile: dist/claude-usage-widget-*-Linux-x86_64.tar.gz"
    echo "============================================================"
else
    echo ""
    echo "[!] Errore durante la compilazione."
    exit 1
fi
