"""Build script for Linux standalone binary packaging and native Debian/Ubuntu (.deb) installer."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
RESOURCES_DIR = SRC_DIR / "claude_usage" / "resources"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
from claude_usage import __version__


def ensure_icon_assets() -> Path:
    """Ensures application PNG icon is generated and returns its path."""
    png_path = RESOURCES_DIR / "app_icon.png"
    if not png_path.exists():
        print("Generating app icon assets...")
        from claude_usage.ui.icon_renderer import IconRenderer
        IconRenderer.get_app_icon_path()
    return png_path


def build_pyinstaller_binary() -> Path:
    """Compiles the application into a standalone Linux ELF executable."""
    print("=" * 60)
    print("1. Compiling Claude Usage Widget for Linux (PyInstaller)")
    print("=" * 60)

    png_path = ensure_icon_assets()
    check_svg = RESOURCES_DIR / "check.svg"

    dist_dir = ROOT_DIR / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    # PyInstaller command for Linux ELF binary
    # Note: On Linux, --add-data uses ':' as path separator
    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=claude-usage-widget",
        "--onefile",
        "--windowed",
        f"--add-data={png_path}:claude_usage/resources",
        f"--add-data={check_svg}:claude_usage/resources",
        "--hidden-import=keyring.backends.SecretService",
        "--hidden-import=desktop_notifier.backends.dbus",
        "--hidden-import=qasync",
        "--collect-all=desktop_notifier",
        "--collect-all=keyring",
        "--clean",
        "--noconfirm",
        str(ROOT_DIR / "main.py"),
    ]

    print("Running:", " ".join(pyinstaller_cmd))
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(pyinstaller_cmd, cwd=str(ROOT_DIR), env=env)
    if result.returncode != 0:
        print(f"Error: PyInstaller build failed with exit code {result.returncode}")
        sys.exit(result.returncode)

    dist_bin = dist_dir / "claude-usage-widget"
    if not dist_bin.exists():
        print(f"Error: {dist_bin} was not found.")
        sys.exit(1)

    # Make sure binary is executable
    dist_bin.chmod(dist_bin.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Also maintain ClaudeUsageWidget binary / symlink for symmetry with Windows
    legacy_alias = dist_dir / "ClaudeUsageWidget"
    try:
        if legacy_alias.exists() or legacy_alias.is_symlink():
            legacy_alias.unlink()
        legacy_alias.symlink_to("claude-usage-widget")
    except Exception:
        shutil.copy2(dist_bin, legacy_alias)

    size_mb = dist_bin.stat().st_size / (1024 * 1024)
    print("=" * 60)
    print(f"SUCCESS: Linux standalone executable created at: {dist_bin}")
    print(f"File size: {size_mb:.1f} MB")
    print("=" * 60)
    return dist_bin


def build_deb_package(bin_path: Path) -> Path:
    """Builds a native Debian/Ubuntu (.deb) package using dpkg-deb."""
    print("\n" + "=" * 60)
    print("2. Building Native Debian/Ubuntu Package (.deb)")
    print("=" * 60)

    pkg_name = "claude-usage-widget"
    deb_version = __version__
    deb_arch = "amd64"
    deb_filename = f"{pkg_name}_{deb_version}_{deb_arch}.deb"
    deb_output_path = ROOT_DIR / "dist" / deb_filename

    staging_dir = ROOT_DIR / "dist" / "deb_staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)

    # Directory layout in .deb
    bin_target_dir = staging_dir / "usr" / "bin"
    applications_dir = staging_dir / "usr" / "share" / "applications"
    icons_dir = staging_dir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    pixmaps_dir = staging_dir / "usr" / "share" / "pixmaps"
    debian_control_dir = staging_dir / "DEBIAN"

    for d in (staging_dir, bin_target_dir, applications_dir, icons_dir, pixmaps_dir, debian_control_dir):
        d.mkdir(parents=True, exist_ok=True)
        d.chmod(0o755)

    # 1. Copy binary
    target_bin = bin_target_dir / "claude-usage-widget"
    shutil.copy2(bin_path, target_bin)
    target_bin.chmod(0o755)

    # Symlink ClaudeUsageWidget in /usr/bin
    alias_bin = bin_target_dir / "ClaudeUsageWidget"
    alias_bin.symlink_to("claude-usage-widget")

    # 2. Copy application icon
    icon_source = RESOURCES_DIR / "app_icon.png"
    target_icon = icons_dir / "claude-usage-widget.png"
    pixmap_icon = pixmaps_dir / "claude-usage-widget.png"
    shutil.copy2(icon_source, target_icon)
    shutil.copy2(icon_source, pixmap_icon)

    # 3. Create .desktop launcher
    desktop_content = """[Desktop Entry]
Type=Application
Name=Claude & Antigravity Usage
Comment=Monitor real-time quotas for Claude Code and Google Antigravity
Exec=/usr/bin/claude-usage-widget
Icon=claude-usage-widget
Terminal=false
Categories=Utility;Development;
StartupNotify=false
X-GNOME-Autostart-enabled=true
"""
    desktop_file = applications_dir / "claude-usage-widget.desktop"
    with open(desktop_file, "w", encoding="utf-8") as f:
        f.write(desktop_content)
    desktop_file.chmod(0o644)

    # 4. Create DEBIAN/control
    control_content = f"""Package: {pkg_name}
Version: {deb_version}
Section: utils
Priority: optional
Architecture: {deb_arch}
Maintainer: giuspo <giuliosporti@gmail.com>
Depends: libc6 (>= 2.34), libgl1, libegl1, libdbus-1-3
Recommends: gnome-shell-extension-appindicator
Description: Real-time Quota & Token System Tray Monitor
 System Tray and Top Panel widget for Claude Code & Google Antigravity
 (Google AI Pro). Provides real-time tracking for 5h session quotas,
 weekly pool utilization, Partner models breakdown, and AI Credits.
"""
    control_file = debian_control_dir / "control"
    with open(control_file, "w", encoding="utf-8") as f:
        f.write(control_content)
    control_file.chmod(0o644)

    # 5. Create DEBIAN/postinst script
    postinst_content = """#!/bin/sh
set -e

if which update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi

if which gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi

exit 0
"""
    postinst_file = debian_control_dir / "postinst"
    with open(postinst_file, "w", encoding="utf-8") as f:
        f.write(postinst_content)
    postinst_file.chmod(0o755)

    # 6. Create DEBIAN/prerm script (safely terminate running instance before remove/upgrade)
    prerm_content = """#!/bin/sh
set -e

# Stop running instances cleanly
pkill -f claude-usage-widget || true
pkill -f ClaudeUsageWidget || true

exit 0
"""
    prerm_file = debian_control_dir / "prerm"
    with open(prerm_file, "w", encoding="utf-8") as f:
        f.write(prerm_content)
    prerm_file.chmod(0o755)

    # 7. Create DEBIAN/postrm script (clean up desktop database and icon cache on remove/purge)
    postrm_content = """#!/bin/sh
set -e

if which update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi

if which gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi

exit 0
"""
    postrm_file = debian_control_dir / "postrm"
    with open(postrm_file, "w", encoding="utf-8") as f:
        f.write(postrm_content)
    postrm_file.chmod(0o755)

    # Ensure permissions conform strictly to Debian package standards (0755 for dirs, 0755 for scripts/bins, 0644 for files)
    staging_dir.chmod(0o755)
    debian_control_dir.chmod(0o755)
    control_file.chmod(0o644)

    # 7. Run dpkg-deb --build
    dpkg_cmd = ["dpkg-deb", "--build", "--root-owner-group", str(staging_dir), str(deb_output_path)]
    print("Running:", " ".join(dpkg_cmd))
    res = subprocess.run(dpkg_cmd)
    if res.returncode != 0:
        print(f"Error: dpkg-deb failed with exit code {res.returncode}")
        sys.exit(res.returncode)

    # Clean up staging dir
    try:
        shutil.rmtree(staging_dir)
    except Exception:
        pass

    deb_size_mb = deb_output_path.stat().st_size / (1024 * 1024)
    print("=" * 60)
    print(f"SUCCESS: Debian/Ubuntu package created at: {deb_output_path}")
    print(f"Package Size: {deb_size_mb:.1f} MB")
    print("=" * 60)
    return deb_output_path


def build_release_tarball(bin_path: Path) -> Path:
    """Builds a portable .tar.gz archive containing binary, icons, desktop file, and install/uninstall scripts."""
    print("\n" + "=" * 60)
    print("3. Building Release Tarball Archive (.tar.gz)")
    print("=" * 60)

    dist_dir = ROOT_DIR / "dist"
    tar_name = f"claude-usage-widget-v{__version__}-Linux-x86_64.tar.gz"
    tar_path = dist_dir / tar_name

    install_sh = ROOT_DIR / "packaging" / "install.sh"
    uninstall_sh = ROOT_DIR / "packaging" / "uninstall.sh"
    icon_png = RESOURCES_DIR / "app_icon.png"

    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(bin_path, arcname="claude-usage-widget")
        if icon_png.exists():
            tar.add(icon_png, arcname="app_icon.png")
        if install_sh.exists():
            tar.add(install_sh, arcname="install.sh")
        if uninstall_sh.exists():
            tar.add(uninstall_sh, arcname="uninstall.sh")

    tar_size_mb = tar_path.stat().st_size / (1024 * 1024)
    print("=" * 60)
    print(f"SUCCESS: Release tarball created at: {tar_path}")
    print(f"Archive Size: {tar_size_mb:.1f} MB")
    print("=" * 60)
    return tar_path


def main():
    dist_bin = ROOT_DIR / "dist" / "claude-usage-widget"
    if ("--skip-build" in sys.argv or "--deb-only" in sys.argv) and dist_bin.exists():
        print(f"Reusing existing binary at {dist_bin}...")
        bin_path = dist_bin
    else:
        bin_path = build_pyinstaller_binary()
    build_deb_package(bin_path)
    build_release_tarball(bin_path)
    print("\n[🎉] Linux build and packaging completed successfully!")


if __name__ == "__main__":
    main()
