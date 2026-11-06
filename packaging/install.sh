#!/usr/bin/env bash
# ==============================================================================
# 1-Click User-Space Installer for Claude & Antigravity Usage Widget
# Installs to ~/.local/bin and integrates with GNOME / Ubuntu Desktop (No sudo required)
# ==============================================================================

set -e

APP_NAME="Claude & Antigravity Usage"
BIN_NAME="claude-usage-widget"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Options
NO_AUTOSTART=0
NO_LAUNCH=0

for arg in "$@"; do
    case "$arg" in
        --no-autostart)
            NO_AUTOSTART=1
            ;;
        --no-launch)
            NO_LAUNCH=1
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --no-autostart    Do not enable autostart on system login"
            echo "  --no-launch       Install files without launching the application"
            echo "  --help, -h        Show this help message"
            exit 0
            ;;
    esac
done

echo "============================================================"
echo " Installing $APP_NAME for Linux (Ubuntu / GNOME)"
echo " Target User Directory: $HOME/.local/bin"
echo "============================================================"

# 1. Locate source executable
SOURCE_BIN=""
CANDIDATES=(
    "$SCRIPT_DIR/$BIN_NAME"
    "$ROOT_DIR/dist/$BIN_NAME"
    "$SCRIPT_DIR/ClaudeUsageWidget"
    "$ROOT_DIR/dist/ClaudeUsageWidget"
)

for cand in "${CANDIDATES[@]}"; do
    if [ -f "$cand" ]; then
        SOURCE_BIN="$cand"
        break
    fi
done

if [ -z "$SOURCE_BIN" ]; then
    echo "[!] Error: Standalone binary '$BIN_NAME' not found in dist/ or packaging/."
    echo "    Please run './build_setup.sh' first to compile the executable."
    exit 1
fi

# 2. Stop running instance gracefully
echo "[*] Stopping any active instance of $BIN_NAME..."
pkill -f "$BIN_NAME" 2>/dev/null || true
pkill -f "ClaudeUsageWidget" 2>/dev/null || true
sleep 0.5

# 3. Create target directories
TARGET_BIN_DIR="$HOME/.local/bin"
TARGET_APPS_DIR="$HOME/.local/share/applications"
TARGET_ICONS_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
AUTOSTART_DIR="$HOME/.config/autostart"

mkdir -p "$TARGET_BIN_DIR"
mkdir -p "$TARGET_APPS_DIR"
mkdir -p "$TARGET_ICONS_DIR"
mkdir -p "$AUTOSTART_DIR"

# 4. Copy binary
DEST_BIN="$TARGET_BIN_DIR/$BIN_NAME"
cp -f "$SOURCE_BIN" "$DEST_BIN"
chmod +x "$DEST_BIN"

# Create symlink ClaudeUsageWidget
ln -sf "$BIN_NAME" "$TARGET_BIN_DIR/ClaudeUsageWidget"
echo "[+] Installed binary to $DEST_BIN"

# 5. Install application icon
ICON_SRC=""
if [ -f "$SCRIPT_DIR/app_icon.png" ]; then
    ICON_SRC="$SCRIPT_DIR/app_icon.png"
elif [ -f "$ROOT_DIR/src/claude_usage/resources/app_icon.png" ]; then
    ICON_SRC="$ROOT_DIR/src/claude_usage/resources/app_icon.png"
fi

if [ -n "$ICON_SRC" ]; then
    cp -f "$ICON_SRC" "$TARGET_ICONS_DIR/$BIN_NAME.png"
    echo "[+] Installed icon to $TARGET_ICONS_DIR/$BIN_NAME.png"
fi

# 6. Create standard FreeDesktop .desktop application launcher
DESKTOP_FILE="$TARGET_APPS_DIR/$BIN_NAME.desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Claude & Antigravity Usage
Comment=Monitor real-time quotas for Claude Code and Google Antigravity
Exec=$DEST_BIN
Icon=$BIN_NAME
Terminal=false
Categories=Utility;Development;
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOF
chmod 644 "$DESKTOP_FILE"
echo "[+] Created desktop launcher: $DESKTOP_FILE"

# 7. Configure XDG Autostart at system login
AUTOSTART_FILE="$AUTOSTART_DIR/$BIN_NAME.desktop"
if [ "$NO_AUTOSTART" -eq 0 ]; then
    cp -f "$DESKTOP_FILE" "$AUTOSTART_FILE"
    echo "[+] Configured autostart at login: $AUTOSTART_FILE"
else
    rm -f "$AUTOSTART_FILE" 2>/dev/null || true
fi

# 8. Update desktop and icon databases
if which update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$TARGET_APPS_DIR" 2>/dev/null || true
fi
if which gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

# 9. Verify PATH contains ~/.local/bin
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "[ℹ] Note: Add '$HOME/.local/bin' to your PATH in ~/.bashrc or ~/.zshrc if not present:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# 10. Launch widget
if [ "$NO_LAUNCH" -eq 0 ]; then
    echo "[*] Launching $APP_NAME..."
    nohup "$DEST_BIN" >/dev/null 2>&1 &
    sleep 0.5
fi

echo "============================================================"
echo " SUCCESS: $APP_NAME has been installed successfully!"
echo " You can find it in your Ubuntu Applications menu."
echo "============================================================"
exit 0
