; Inno Setup script. Build the PyInstaller folder first, then:
;   ISCC packaging\installer.iss /DMyAppVersion=0.1.0 /DDistDir=dist\InstantDic
; The wizard asks: install for me only (no admin, %LOCALAPPDATA%\Programs\InstantDic)
; or for all users (admin, C:\Program Files\InstantDic).

#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#ifndef DistDir
  #define DistDir "..\dist\InstantDic"
#endif

[Setup]
AppId={{6E1B8C52-3F4A-4C0E-9A57-2D3B1C9E7F10}
AppName=InstantDic
AppVersion={#MyAppVersion}
AppPublisher=InstantDic
DefaultDirName={autopf}\InstantDic
DefaultGroupName=InstantDic
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputBaseFilename=InstantDic-Setup-{#MyAppVersion}
OutputDir=..\dist
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\InstantDic.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
#if FileExists(AddBackslash(CompilerPath) + "Languages\ChineseSimplified.isl")
Name: "chs"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
#endif
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "开机自动启动 / Start with Windows"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\InstantDic"; Filename: "{app}\InstantDic.exe"
Name: "{group}\{cm:UninstallProgram,InstantDic}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\InstantDic"; Filename: "{app}\InstantDic.exe"; Tasks: desktopicon

[Registry]
; Same value the in-app "开机自动启动" checkbox uses, so the two stay in sync.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "InstantDic"; \
  ValueData: """{app}\InstantDic.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\InstantDic.exe"; Description: "{cm:LaunchProgram,InstantDic}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM InstantDic.exe /F"; Flags: runhidden; RunOnceId: "KillApp"
