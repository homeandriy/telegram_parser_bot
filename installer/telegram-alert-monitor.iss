#define AppName "Telegram Alert Monitor"
#define AppVersion "0.1.0"
#define AppExeName "TelegramAlertMonitor.exe"

[Setup]
AppId={{C0D6F1C4-C19C-45B9-A29C-C92A50E61BE4}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\Telegram Alert Monitor
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=TelegramAlertMonitor-Setup
SetupIconFile=..\assets\telegram-alert.ico
WizardImageFile=..\assets\wizard-large.bmp
WizardSmallImageFile=..\assets\wizard-small.bmp
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExeName}

[Files]
Source: "..\dist\TelegramAlertMonitor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Створити значок на робочому столі"; GroupDescription: "Додаткові значки:"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Запустити Telegram Alert Monitor"; Flags: nowait postinstall skipifsilent
