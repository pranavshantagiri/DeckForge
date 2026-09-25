; DeckForge installer (Workstream J) - Inno Setup 6 script (6.3+).
;
; Produces dist\deckforge-setup.exe, which installs the frozen CLI
; (deckforge.exe, produced by packaging\deckforge.spec) into
; %LocalAppData%\Programs\DeckForge and adds Start Menu shortcuts.
;
; Build order (from the repository root):
;     pyinstaller --noconfirm --clean packaging\deckforge.spec
;     iscc packaging\deckforge.iss
;
; Per-user install (PrivilegesRequired=lowest): no UAC elevation and nothing is
; written outside the current user's profile. For a machine-wide install change
; PrivilegesRequired to admin and DefaultDirName to {autopf}\DeckForge.
; MIT licensed; the source of record is https://github.com/pranavshantagiri/DeckForge

#define AppName "DeckForge"
#define AppVersion "0.1.0"
#define AppPublisher "DeckForge"
#define AppURL "https://github.com/pranavshantagiri/DeckForge"
#define AppExeName "deckforge.exe"

[Setup]
AppId={{7C3B9E14-6D2A-4F58-9B0C-2A5D8E14F63C}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
AppComments=DeckForge learns presentation formats from real .pptx decks and renders native editable PowerPoint decks. MIT licensed.
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\DeckForge
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir=..\dist
OutputBaseFilename=deckforge-setup
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; one-directory PyInstaller build: deckforge.exe plus its _internal tree
Source: "..\dist\deckforge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DeckForge"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{userdocs}"; Comment: "Open a DeckForge command prompt - run: deckforge --help"
Name: "{group}\Uninstall DeckForge"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#AppExeName}"; Parameters: "version"; WorkingDir: "{app}"; Description: "Show the installed version"; Flags: postinstall skipifsilent waituntilterminated
