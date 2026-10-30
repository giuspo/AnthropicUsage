"""Build script for Windows standalone binary packaging."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
RESOURCES_DIR = SRC_DIR / "claude_usage" / "resources"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
from claude_usage import __version__


def build_executable():
    print("=" * 60)
    print("Building Claude Usage Widget for Windows (PyInstaller)")
    print("=" * 60)

    # 1. Ensure icons exist
    ico_path = RESOURCES_DIR / "app_icon.ico"
    png_path = RESOURCES_DIR / "app_icon.png"
    if not ico_path.exists() or not png_path.exists():
        print("Generating app icon assets...")
        from claude_usage.ui.icon_renderer import IconRenderer
        IconRenderer.get_app_icon_path()

    # 2. Build PyInstaller command
    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=ClaudeUsageWidget",
        "--onefile",
        "--windowed",
        f"--icon={ico_path}",
        f"--add-data={RESOURCES_DIR / 'app_icon.png'};claude_usage/resources",
        f"--add-data={RESOURCES_DIR / 'app_icon.ico'};claude_usage/resources",
        f"--add-data={RESOURCES_DIR / 'check.svg'};claude_usage/resources",
        "--hidden-import=keyring.backends.Windows",
        "--hidden-import=desktop_notifier.backends.winrt",
        "--hidden-import=qasync",
        "--collect-all=desktop_notifier",
        "--collect-all=keyring",
        "--clean",
        "--noconfirm",
        str(ROOT_DIR / "main.py"),
    ]

    print("Running:", " ".join(pyinstaller_cmd))
    env = os.environ.copy()
    site_packages = ROOT_DIR / ".venv" / "Lib" / "site-packages"
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + str(site_packages) + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(pyinstaller_cmd, cwd=str(ROOT_DIR), env=env)
    if result.returncode != 0:
        print(f"Error: PyInstaller build failed with exit code {result.returncode}")
        sys.exit(result.returncode)

    dist_exe = ROOT_DIR / "dist" / "ClaudeUsageWidget.exe"
    if dist_exe.exists():
        size_mb = dist_exe.stat().st_size / (1024 * 1024)
        print("=" * 60)
        print(f"SUCCESS: Executable created at: {dist_exe}")
        print(f"File size: {size_mb:.1f} MB")
        print("=" * 60)
    else:
        print(f"Error: {dist_exe} was not found.")
        sys.exit(1)

    # 3. Compile Windows Setup Wizard with Inno Setup if installed
    iscc_candidates = [
        shutil.which("iscc"),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "iscc.exe"),
        str(Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "iscc.exe"),
        str(Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "iscc.exe"),
    ]
    iscc_path = None
    for cand in iscc_candidates:
        if cand and Path(cand).exists():
            iscc_path = cand
            break

    if iscc_path:
        print("\nCompiling standard Windows Setup Wizard with Inno Setup 6...")
        iss_path = ROOT_DIR / "packaging" / "installer.iss"
        iscc_cmd = [iscc_path, f"/DMyAppVersion={__version__}", str(iss_path)]
        res = subprocess.run(iscc_cmd, cwd=str(ROOT_DIR))
        if res.returncode == 0:
            setup_exe = ROOT_DIR / "dist" / f"ClaudeUsageWidget-Setup-v{__version__}.exe"
            if setup_exe.exists():
                print("=" * 60)
                print(f"SUCCESS: Setup Wizard created at: {setup_exe}")
                print(f"Setup Size: {setup_exe.stat().st_size / (1024 * 1024):.1f} MB")
                print("=" * 60)
                # Keep a legacy unversioned copy for automated shortcuts
                legacy_setup = ROOT_DIR / "dist" / "ClaudeUsageWidget-Setup.exe"
                try:
                    shutil.copy2(setup_exe, legacy_setup)
                except Exception:
                    pass

    # 4. Create release zip archive with version
    dist_dir = ROOT_DIR / "dist"
    dist_exe = dist_dir / "ClaudeUsageWidget.exe"
    dist_setup = dist_dir / f"ClaudeUsageWidget-Setup-v{__version__}.exe"
    zip_path = dist_dir / f"ClaudeUsageWidget-v{__version__}-Windows.zip"

    if dist_exe.exists():
        print(f"\nCreating release archive: {zip_path.name}...")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(dist_exe, "ClaudeUsageWidget.exe")
            if dist_setup.exists():
                z.write(dist_setup, dist_setup.name)
        print(f"SUCCESS: Release archive ready at: {zip_path}")
        print(f"Archive Size: {zip_path.stat().st_size / (1024 * 1024):.1f} MB")
        print("=" * 60)


if __name__ == "__main__":
    build_executable()

