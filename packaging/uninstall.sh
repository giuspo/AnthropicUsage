#!/usr/bin/env bash
# ==============================================================================
# Uninstaller for Claude & Antigravity Usage Widget (User-Space)
# Cleans up binary, desktop launcher, icons, and autostart configuration
# ==============================================================================

set -e

APP_NAME="Claude & Antigravity Usage"
BIN_NAME="claude-usage-widget"

echo "============================================================"
echo " Uninstalling $APP_NAME..."
echo "============================================================"

# 1. Stop running instances
echo "[*] Stopping running instances..."
pkill -f "$BIN_NAME" 2>/dev/null || true
pkill -f "ClaudeUsageWidget" 2>/dev/null || true

# 2. Remove binary and symlink
TARGET_BIN_DIR="$HOME/.local/bin"
rm -f "$TARGET_BIN_DIR/$BIN_NAME"
rm -f "$TARGET_BIN_DIR/ClaudeUsageWidget"
echo "[+] Removed binary from $TARGET_BIN_DIR"

# 3. Remove desktop launcher
TARGET_APPS_DIR="$HOME/.local/share/applications"
rm -f "$TARGET_APPS_DIR/$BIN_NAME.desktop"
echo "[+] Removed application launcher from $TARGET_APPS_DIR"

# 4. Remove icon
TARGET_ICONS_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
rm -f "$TARGET_ICONS_DIR/$BIN_NAME.png"
echo "[+] Removed icon from $TARGET_ICONS_DIR"

# 5. Remove autostart entry
AUTOSTART_DIR="$HOME/.config/autostart"
rm -f "$AUTOSTART_DIR/$BIN_NAME.desktop"
echo "[+] Removed login autostart from $AUTOSTART_DIR"

# 6. Update desktop and icon databases
if which update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$TARGET_APPS_DIR" 2>/dev/null || true
fi
if which gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo "============================================================"
echo " SUCCESS: $APP_NAME has been uninstalled."
echo " Note: Your configuration settings in ~/.config/claude-usage-widget"
echo " were preserved. (Delete that directory manually if desired)."
echo "============================================================"
exit 0
