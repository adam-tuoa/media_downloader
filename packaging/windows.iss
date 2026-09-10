; Inno Setup script - wraps build\windows (see scripts/build_windows.py) into a per-user installer.
; Build: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\windows.iss
; Output: UsefulMedia-windows-x64-setup.exe in the repo root.

#define AppName "UsefulMedia"
#define AppVersion GetEnv("APP_VERSION")
#if AppVersion == ""
  #define AppVersion "0.0.0"
#endif

[Setup]
; Paths below are relative to the repo root, not to this file's folder.
SourceDir=..
AppId={{7B2E1C1A-5D3B-4B7F-9C1E-6D0F2A9B8E11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Adam Simmons
AppPublisherURL=https://github.com/tuoa-tools/usefulmedia
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=.
OutputBaseFilename=UsefulMedia-windows-x64-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName}
WizardStyle=modern

[Files]
Source: "build\windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m app.launcher"; WorkingDir: "{app}"; Comment: "Download videos and music"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m app.launcher"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-m app.launcher"; WorkingDir: "{app}"; Description: "Open {#AppName} now"; Flags: postinstall nowait skipifsilent
