#define AppVersion GetEnv("LSYNC_VERSION")
#if AppVersion == ""
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8F2C5B1E-3A44-4C7B-9C1D-5E7A9B0C2D31}
AppName=Lsync
AppVersion={#AppVersion}
AppVerName=Lsync {#AppVersion}
AppPublisher=LS Corporation
AppPublisherURL=https://github.com/LS-Corporation/lsync
AppSupportURL=https://github.com/LS-Corporation/lsync/issues
DefaultDirName={localappdata}\Programs\Lsync
DefaultGroupName=Lsync
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Lsync-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\Lsync.exe
UninstallDisplayName=Lsync
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Lsync\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Lsync"; Filename: "{app}\Lsync.exe"
Name: "{autodesktop}\Lsync"; Filename: "{app}\Lsync.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Lsync.exe"; Description: "{cm:LaunchProgram,Lsync}"; Flags: nowait postinstall skipifsilent
