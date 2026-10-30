; Inno Setup 6 Script for Claude Code Usage Widget
; Produces a modern, lightweight, non-admin Windows Installer

#define MyAppName "Claude Code Usage Widget"
#define MyAppVersion "1.0.6"
#define MyAppPublisher "giuspo"
#define MyAppExeName "ClaudeUsageWidget.exe"
#define MyAppAssocName MyAppName + " File"

[Setup]
AppId={{E68F0D77-38B1-4A59-864B-8B2446A6C321}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\ClaudeUsageWidget
DisableDirPage=no
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ClaudeUsageWidget-Setup
SetupIconFile=..\src\claude_usage\resources\app_icon.ico
LicenseFile=..\LICENSE
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Avvia automaticamente all'accesso a Windows"; GroupDescription: "Opzioni di avvio:"

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

[InstallDelete]
; Clean up redundant startup shortcuts created by older installer versions (prevents duplicate instance at boot)
Type: files; Name: "{userstartup}\{#MyAppName}.lnk"
Type: files; Name: "{userstartup}\ClaudeUsageWidget.lnk"
Type: files; Name: "{userstartup}\Claude Code Usage.lnk"

[UninstallDelete]
Type: files; Name: "{userstartup}\{#MyAppName}.lnk"
Type: files; Name: "{userstartup}\ClaudeUsageWidget.lnk"
Type: files; Name: "{userstartup}\Claude Code Usage.lnk"

[Registry]
Root: HKCU; Subkey: "Software\Classes\AppUserModelId\ClaudeCode.UsageWidget"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ClaudeUsageWidget"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Helper to automatically terminate running instances of ClaudeUsageWidget before install or uninstall
procedure StopRunningInstances();
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM {#MyAppExeName} /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(300);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningInstances();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  StopRunningInstances();
  Result := True;
end;

