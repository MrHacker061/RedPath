; RedPath's in-app setup owns consent and verified dependency downloads.
; Uninstall removes this payload and shortcuts; user data and environments stay.
[Setup]
AppId={{F6B3970E-BF8A-4C32-B108-31560B255027}
AppName=RedPath
AppVersion=0.1.0
AppPublisher=RedPath
DefaultDirName={localappdata}\Programs\RedPath
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.22000
OutputDir=..\dist\installer
OutputBaseFilename=RedPath-Setup-0.1.0-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\RedPath.exe
TimeStampsInUTC=yes
TouchDate=2026-09-11
TouchTime=00:00:00

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\RedPath\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs touch

[Icons]
Name: "{userprograms}\RedPath"; Filename: "{app}\RedPath.exe"
Name: "{userdesktop}\RedPath"; Filename: "{app}\RedPath.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\RedPath.exe"; Description: "Launch RedPath and open first-run setup"; Flags: nowait postinstall skipifsilent
