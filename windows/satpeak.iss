; SatPeak - QO-100 dish peaker - Inno Setup script
#define AppVer "1.0.0"

[Setup]
AppId={{6E0C1C2A-6F3B-4D1E-9A55-0B2C9D9A5A7E}
AppName=SatPeak QO-100 Dish Peaker
AppVerName=SatPeak {#AppVer}
AppVersion={#AppVer}
AppPublisher=SatPeak
DefaultDirName={autopf}\SatPeak
DefaultGroupName=SatPeak
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=output
OutputBaseFilename=SatPeak-Setup-{#AppVer}
SetupIconFile=satpeak.ico
UninstallDisplayIcon={app}\SatPeak.exe
UninstallDisplayName=SatPeak QO-100 Dish Peaker
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\SatPeak\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.txt"; DestDir: "{app}"; Flags: ignoreversion isreadme
#if FileExists(AddBackslash(SourcePath) + "SatPeak.apk")
Source: "SatPeak.apk"; DestDir: "{app}\Android app"; Flags: ignoreversion
#endif

[Icons]
Name: "{group}\SatPeak"; Filename: "{app}\SatPeak.exe"; WorkingDir: "{app}"
Name: "{group}\SatPeak (demo mode)"; Filename: "{app}\SatPeak.exe"; Parameters: "--demo"; WorkingDir: "{app}"
#if FileExists(AddBackslash(SourcePath) + "SatPeak.apk")
Name: "{group}\SatPeak Android app (APK)"; Filename: "{app}\Android app"
#endif
Name: "{group}\SatPeak README"; Filename: "{app}\README.txt"
Name: "{group}\Uninstall SatPeak"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SatPeak"; Filename: "{app}\SatPeak.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\SatPeak.exe"; Description: "Start SatPeak now"; Flags: nowait postinstall skipifsilent
