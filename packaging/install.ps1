# PowerShell 1-Click Installer for Claude Code Usage Widget
# Installs in %LOCALAPPDATA%\Programs\ClaudeUsageWidget without requiring Admin rights

param (
    [switch]$NoAutostart,
    [switch]$NoDesktopShortcut
)

$ErrorActionPreference = "Stop"

$AppName = "Claude Code Usage Widget"
$ExeName = "ClaudeUsageWidget.exe"
$InstallDir = "$env:LOCALAPPDATA\Programs\ClaudeUsageWidget"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# Locate source executable
$SourceExe = Join-Path $ScriptDir "..\dist\$ExeName"
if (-not (Test-Path $SourceExe)) {
    $SourceExe = Join-Path $ScriptDir $ExeName
}
if (-not (Test-Path $SourceExe)) {
    Write-Error "Could not find $ExeName in '$ScriptDir' or 'dist\' folder."
    exit 1
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Installing $AppName" -ForegroundColor Cyan
Write-Host " Target Directory: $InstallDir" -ForegroundColor Gray
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Kill any running instance
Get-Process -Name "ClaudeUsageWidget" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

# 2. Create Target Directory & Copy Exe
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}
$DestExe = Join-Path $InstallDir $ExeName
Copy-Item -Path $SourceExe -Destination $DestExe -Force
Write-Host "[+] Copied $ExeName to $InstallDir" -ForegroundColor Green

# 3. Create Start Menu Shortcut
$StartMenuDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Claude Code Usage"
if (-not (Test-Path $StartMenuDir)) {
    New-Item -ItemType Directory -Path $StartMenuDir -Force | Out-Null
}
$WshShell = New-Object -ComObject WScript.Shell
$StartShortcut = $WshShell.CreateShortcut((Join-Path $StartMenuDir "$AppName.lnk"))
$StartShortcut.TargetPath = $DestExe
$StartShortcut.WorkingDirectory = $InstallDir
$StartShortcut.IconLocation = "$DestExe,0"
$StartShortcut.Description = "Claude Code Quota & Token Monitor"
$StartShortcut.Save()
Write-Host "[+] Created Start Menu Shortcut" -ForegroundColor Green

# 4. Create Desktop Shortcut (optional)
if (-not $NoDesktopShortcut) {
    $DesktopDir = [Environment]::GetFolderPath("Desktop")
    $DesktopShortcut = $WshShell.CreateShortcut((Join-Path $DesktopDir "$AppName.lnk"))
    $DesktopShortcut.TargetPath = $DestExe
    $DesktopShortcut.WorkingDirectory = $InstallDir
    $DesktopShortcut.IconLocation = "$DestExe,0"
    $DesktopShortcut.Description = "Claude Code Quota & Token Monitor"
    $DesktopShortcut.Save()
    Write-Host "[+] Created Desktop Shortcut" -ForegroundColor Green
}

# 5. Configure Windows Autostart in Registry
if (-not $NoAutostart) {
    $RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    Set-ItemProperty -Path $RunKey -Name "ClaudeUsageWidget" -Value "`"$DestExe`""
    Write-Host "[+] Configured Windows Run Registry key for Autostart" -ForegroundColor Green
}

# 6. Launch Widget
Write-Host "[*] Launching $AppName..." -ForegroundColor Cyan
Start-Process -FilePath $DestExe

Write-Host "============================================================" -ForegroundColor Green
Write-Host " SUCCESS: $AppName has been installed and launched!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

