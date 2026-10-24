; Inno Setup script. Build the PyInstaller folder first, then:
;   ISCC packaging\installer.iss /DMyAppVersion=0.1.0 /DDistDir=dist\CustomDic
; Per-user install (no admin rights): %LOCALAPPDATA%\Programs\CustomDic

#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#ifndef DistDir
  #define DistDir "..\dist\CustomDic"
#endif

[Setup]
AppId={{6E1B8C52-3F4A-4C0E-9A57-2D3B1C9E7F10}
AppName=CustomDic
AppVersion={#MyAppVersion}
AppPublisher=CustomDic
DefaultDirName={localappdata}\Programs\CustomDic
DefaultGroupName=CustomDic
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=CustomDic-Setup-{#MyAppVersion}
OutputDir=..\dist
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\CustomDic.exe
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
Name: "{group}\CustomDic"; Filename: "{app}\CustomDic.exe"
Name: "{group}\{cm:UninstallProgram,CustomDic}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\CustomDic"; Filename: "{app}\CustomDic.exe"; Tasks: desktopicon

[Registry]
; Same value the in-app "开机自动启动" checkbox uses, so the two stay in sync.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "CustomDic"; \
  ValueData: """{app}\CustomDic.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\CustomDic.exe"; Description: "{cm:LaunchProgram,CustomDic}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM CustomDic.exe /F"; Flags: runhidden; RunOnceId: "KillApp"
