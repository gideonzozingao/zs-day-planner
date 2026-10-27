; Inno Setup 6.3+ script for Zuqongtech Daily Planner.
; Normally run by build.ps1, which passes /DMyAppVersion=<planner.__version__>.
; Manual:  iscc /DMyAppVersion=1.0.0 packaging\installer.iss

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppName "Zuqongtech Daily Planner"
#define MyAppPublisher "Zuqongtech"
#define MyAppExeName "ZuqongtechPlanner.exe"
#define MyAppUserModelID "Zuqongtech.DailyPlanner"
#define ProjectRoot ".."

[Setup]
; Keep AppId fixed forever: it is how upgrades find the existing install.
AppId={{6E0F3B2A-9C4D-4E1B-8A57-2D7C1F4B9E36}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Zuqongtech\Daily Planner
DisableProgramGroupPage=yes
; Per-user install by default (no admin prompt); the user can choose "all users" instead.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ProjectRoot}\dist\installer
OutputBaseFilename=ZuqongtechPlanner-Setup-{#MyAppVersion}
SetupIconFile={#ProjectRoot}\packaging\assets\planner.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; Detect a running copy (the app creates this mutex) and offer to close it.
AppMutex=ZuqongtechDailyPlannerMutex
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup"; Description: "Start automatically when I sign in (runs quietly in the tray)"; GroupDescription: "Startup:"

[Files]
Source: "{#ProjectRoot}\dist\ZuqongtechPlanner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelID}"
Name: "{autoprograms}\{#MyAppName} - Quick add"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--capture"; Comment: "Add a task from anywhere"; AppUserModelID: "{#MyAppUserModelID}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelID}"; Tasks: desktopicon

[Registry]
; HKA = current user for per-user installs, all users for admin installs.
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ZuqongtechDailyPlanner"; ValueData: """{app}\{#MyAppExeName}"" --tray"; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
; Self-update: the app runs setup with /VERYSILENT /RELAUNCH, so start it again afterwards.
Filename: "{app}\{#MyAppExeName}"; Flags: nowait runasoriginaluser; Check: ShouldRelaunch

[Code]
function ShouldRelaunch(): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/RELAUNCH') = 0 then
      Result := True;
end;

// Tasks live in %USERPROFILE%\.zuqongtech_planner and survive upgrades.
// On uninstall, ask before deleting them (default: keep).
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{%USERPROFILE}\.zuqongtech_planner');
    if DirExists(DataDir) and (not UninstallSilent) then
      if MsgBox('Also delete your tasks, history and theme settings?' + #13#10#13#10 + DataDir,
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
