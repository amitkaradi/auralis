; Inno Setup script for Auralis. Compile with the free Inno Setup compiler:
;   https://jrsoftware.org/isdl.php
; Output: dist\AuralisSetup-1.1.0.exe (one double-click installer).

#define AppName        "Auralis"
#define AppVersion     "1.1.0"
#define AppPublisher   "Amit"
#define AppURL         "https://github.com/amitkaradi/auralis"
#define AppExeName     "Auralis.exe"
; Optional output-filename suffix so the same script can produce
; AuralisSetup-1.1.0.exe (full) and AuralisSetup-1.1.0-lite.exe (no model).
; Override by passing /DBuildSuffix=-lite on the ISCC command line.
#ifndef BuildSuffix
  #define BuildSuffix ""
#endif

[Setup]
AppId={{B6F1F6E8-2C40-4D89-9D77-AURALIS00001}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE.txt
OutputDir=dist
OutputBaseFilename=AuralisSetup-{#AppVersion}{#BuildSuffix}
SetupIconFile=assets\auralis.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
MinVersion=10.0.17763

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startupicon";  Description: "Launch {#AppName} at sign-in"; GroupDescription: "Auto-start:"; Flags: unchecked

[Files]
Source: "dist\Auralis\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.md";   DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
