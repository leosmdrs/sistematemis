; ─────────────────────────────────────────────────────────────
;  Sistema Têmis — instalador (Inno Setup 6)
;
;  Pré-requisito: gerar a pasta dist\SistemaTemis com
;      pyinstaller build/temis.spec --noconfirm
;  Depois compilar este script no Inno Setup Compiler.
; ─────────────────────────────────────────────────────────────

#define AppName        "Sistema Têmis"
#define AppVersion     "1.4.0"
#define AppPublisher   "Leonardo Medeiros"
#define AppExe         "SistemaTemis.exe"

[Setup]
AppId={{B7E4C1A2-9F3D-4E58-A6C7-2D1F8B0E5A34}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\SistemaTemis
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=SistemaTemis-{#AppVersion}-setup
SetupIconFile=temis.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

; Instala para o usuário atual quando não há direitos de administrador —
; útil em estações onde o servidor não tem privilégio de instalação.
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na &Área de Trabalho"; \
    GroupDescription: "Atalhos adicionais:"

[Files]
Source: "..\dist\SistemaTemis\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";     Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; \
    Description: "Executar o {#AppName} agora"; \
    Flags: nowait postinstall skipifsilent
