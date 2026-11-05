; Inno Setup 7 script for the StreamBridge installer (per-user, no admin rights).
;
; Do not run ISCC on this file by hand: build\installer.ps1 passes the values below
; and checks that the packed program matches the current version.
;   /DAppVersion=<full text, e.g. 0.1.0b0>   /DWinVersion=<4 numbers, e.g. 0.1.0.0>
;   /DDistDir=<folder with StreamBridge.exe>  /DRepoDir=<repo root>

#ifndef AppVersion
  #error AppVersion is not defined. Build with build\installer.ps1.
#endif
#ifndef WinVersion
  #error WinVersion is not defined. Build with build\installer.ps1.
#endif
#ifndef DistDir
  #error DistDir is not defined. Build with build\installer.ps1.
#endif
#ifndef RepoDir
  #error RepoDir is not defined. Build with build\installer.ps1.
#endif

[Setup]
; Fixed forever: Windows uses it to recognise an older install and upgrade it in place.
AppId={{6B798149-4289-4D6D-8006-387C11C7713E}
AppName=StreamBridge
AppVersion={#AppVersion}
AppPublisher=StreamBridge contributors
AppPublisherURL=https://github.com/Nabshdq/StreamBridge
AppSupportURL=https://github.com/Nabshdq/StreamBridge/issues
VersionInfoVersion={#WinVersion}
VersionInfoDescription=StreamBridge Setup
; Per-user install (%LOCALAPPDATA%\Programs\StreamBridge): no admin prompt.
PrivilegesRequired=lowest
DefaultDirName={autopf}\StreamBridge
DisableProgramGroupPage=yes
; Inno Setup 7 builds 32-bit installers by default; the app is 64-bit only.
SetupArchitecture=x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile={#RepoDir}\LICENSE
OutputDir={#RepoDir}\build\output\installer
OutputBaseFilename=StreamBridge-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Ask for the language only when Windows' own language is not offered; Indonesian Windows
; gets Indonesian automatically (like the app's own "Auto" language rule).
ShowLanguageDialog=auto
; Close a running StreamBridge before replacing its files (upgrade over the old version).
CloseApplications=yes
RestartApplications=no
; The icon of the exe is used until the app gets its own .ico (separate item).
UninstallDisplayIcon={app}\StreamBridge.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
; Unofficial translation, copied unchanged from
; https://github.com/jrsoftware/issrc/blob/main/Files/Languages/Unofficial/Indonesian.isl
; (Inno Setup License: redistribution allowed with the copyright notices kept; the
; header of the file names its translators). The installer language is NOT linked to the
; app's own ui_language setting.
Name: "indonesian"; MessagesFile: "Indonesian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Upgrade: a newer build can drop DLLs or Qt plugin folders. Old leftovers could still be
; loaded, so clear the program folder first. Only when it really is our own folder
; (see IsOwnInstallFolder: a folder the user typed, such as D:\Apps, is never wiped).
; User data lives elsewhere (%APPDATA%, %LOCALAPPDATA%\StreamBridge, Credential Manager)
; and is never touched.
Type: filesandordirs; Name: "{app}\*"; Check: IsOwnInstallFolder

[Icons]
Name: "{autoprograms}\StreamBridge"; Filename: "{app}\StreamBridge.exe"
Name: "{autodesktop}\StreamBridge"; Filename: "{app}\StreamBridge.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\StreamBridge.exe"; Description: "{cm:LaunchProgram,StreamBridge}"; Flags: nowait postinstall skipifsilent

[Code]
{ True only when the chosen folder is named StreamBridge AND holds an earlier install of
  ours (the program and its uninstaller data). Anything else is left alone. }
function IsOwnInstallFolder: Boolean;
var
  Folder: String;
begin
  Folder := ExpandConstant('{app}');
  Result :=
    (CompareText(ExtractFileName(RemoveBackslash(Folder)), 'StreamBridge') = 0) and
    FileExists(AddBackslash(Folder) + 'StreamBridge.exe') and
    FileExists(AddBackslash(Folder) + 'unins000.dat');
end;
