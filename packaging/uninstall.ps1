# PowerShell Uninstaller for Claude Code Usage Widget

$AppName = "Claude Code Usage Widget"
$InstallDir = "$env:LOCALAPPDATA\Programs\ClaudeUsageWidget"
$StartMenuDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Claude Code Usage"
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$AppName.lnk"

Write-Host "============================================================" -ForegroundColor Yellow
Write-Host " Uninstalling $AppName" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow

# 1. Terminate running process
Get-Process -Name "ClaudeUsageWidget" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

# 2. Remove Autostart Registry Key
$RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if (Get-ItemProperty -Path $RunKey -Name "ClaudeUsageWidget" -ErrorAction SilentlyContinue) {
    Remove-ItemProperty -Path $RunKey -Name "ClaudeUsageWidget" -ErrorAction SilentlyContinue
    Write-Host "[-] Removed Autostart Registry entry" -ForegroundColor Green
}

# 3. Remove Desktop Shortcut
if (Test-Path $DesktopShortcut) {
    Remove-Item -Path $DesktopShortcut -Force
    Write-Host "[-] Removed Desktop Shortcut" -ForegroundColor Green
}

# 4. Remove Start Menu Folder
if (Test-Path $StartMenuDir) {
    Remove-Item -Path $StartMenuDir -Recurse -Force
    Write-Host "[-] Removed Start Menu folder" -ForegroundColor Green
}

# 5. Remove Installation Directory
if (Test-Path $InstallDir) {
    Remove-Item -Path $InstallDir -Recurse -Force
    Write-Host "[-] Removed Installation Directory ($InstallDir)" -ForegroundColor Green
}

Write-Host "============================================================" -ForegroundColor Green
Write-Host " SUCCESS: $AppName has been completely removed." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

