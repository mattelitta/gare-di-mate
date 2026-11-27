; Installer Windows di Gare di Mate (Inno Setup 6). Si compila con build_installer.bat.
; Eseguito sopra una versione già installata la aggiorna (stesso AppId); i dati in Documenti restano.
#define AppName "Gare di Mate"
#define AppExe "GareDiMate.exe"
#define AppId "8F3B2C41-6D7E-4A5B-9C10-2E4F6A8B0D13"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{{#AppId}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=admin
OutputDir=..\dist
OutputBaseFilename=GareDiMate-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
InfoAfterFile=dopo_installazione.txt
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; La chiusura del programma aperto è gestita in [Code], con messaggi più chiari.
CloseApplications=no

[Languages]
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"

[Messages]
UninstalledAll=%1 è stato disinstallato.%n%nLe gare salvate restano nella cartella Documenti\Gare di Mate: se non servono più, si può eliminare quella cartella.

[Tasks]
Name: "desktopicon"; Description: "Crea un'icona sul desktop"; GroupDescription: "Icone:"

[InstallDelete]
; Rimuove i file della versione precedente prima di copiare quelli nuovi.
Type: filesandordirs; Name: "{app}\_internal"
; La versione 1.0.0 metteva il collegamento direttamente nel menu Start (ora è nella cartella del programma).
Type: files; Name: "{autoprograms}\{#AppName}.lnk"

[Files]
Source: "..\dist\GareDiMate\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Disinstalla {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; Regola firewall: solo questo programma, solo porte 8000 (rimando) e 8443 (HTTPS), solo dispositivi della rete locale.
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#AppName}"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#AppName}"" dir=in action=allow program=""{app}\{#AppExe}"" protocol=TCP localport=8000,8443 remoteip=localsubnet enable=yes profile=any"; Flags: runhidden; StatusMsg: "Configurazione del firewall..."
Filename: "{app}\{#AppExe}"; Description: "Avvia {#AppName} adesso"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#AppName}"""; Flags: runhidden; RunOnceId: "DelFirewallRule"

[Code]
const
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{{#AppId}}_is1';

function InstalledVersion(): String;
begin
  Result := '';
  if not RegQueryStringValue(HKLM, UninstallKey, 'DisplayVersion', Result) then
    RegQueryStringValue(HKCU, UninstallKey, 'DisplayVersion', Result);
end;

function NextVersionPart(var S: String): Integer;
var
  P: Integer;
begin
  P := Pos('.', S);
  if P = 0 then
  begin
    Result := StrToIntDef(S, 0);
    S := '';
  end
  else
  begin
    Result := StrToIntDef(Copy(S, 1, P - 1), 0);
    Delete(S, 1, P);
  end;
end;

{ -1 se A < B, 0 se uguali, 1 se A > B }
function CompareVersions(A, B: String): Integer;
var
  I, PA, PB: Integer;
begin
  Result := 0;
  for I := 1 to 3 do
  begin
    PA := NextVersionPart(A);
    PB := NextVersionPart(B);
    if PA < PB then begin Result := -1; Exit; end;
    if PA > PB then begin Result := 1; Exit; end;
  end;
end;

function AppIsRunning(): Boolean;
var
  Locator, Service, Procs: Variant;
begin
  Result := False;
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root\CIMV2');
    Procs := Service.ExecQuery('SELECT ProcessId FROM Win32_Process WHERE Name = ''{#AppExe}''');
    Result := Procs.Count > 0;
  except
  end;
end;

procedure CloseApp();
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(1000);
end;

function InitializeSetup(): Boolean;
var
  Old: String;
  Cmp: Integer;
begin
  Result := True;
  Old := InstalledVersion();
  if Old = '' then
    Exit;
  Cmp := CompareVersions(Old, '{#AppVersion}');
  if Cmp < 0 then
    SuppressibleMsgBox('È installata la versione ' + Old + ' di Gare di Mate: verrà aggiornata alla versione {#AppVersion}.' + #13#10#13#10 +
      'Le gare salvate non verranno toccate.', mbInformation, MB_OK, IDOK)
  else if Cmp = 0 then
    Result := SuppressibleMsgBox('Gare di Mate {#AppVersion} è già installato.' + #13#10#13#10 +
      'Reinstallarlo? Le gare salvate non verranno toccate.', mbConfirmation, MB_YESNO, IDYES) = IDYES
  else
    Result := SuppressibleMsgBox('È già installata una versione più recente di Gare di Mate (' + Old + ').' + #13#10 +
      'Questo programma installerebbe la versione più vecchia {#AppVersion}.' + #13#10#13#10 +
      'Continuare comunque?', mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if AppIsRunning() then
  begin
    if SuppressibleMsgBox('Gare di Mate è aperto e deve essere chiuso per continuare.' + #13#10#13#10 +
        'Chiuderlo adesso?', mbConfirmation, MB_YESNO, IDYES) = IDYES then
      CloseApp()
    else
      Result := 'Chiudere Gare di Mate e poi avviare di nuovo l''installazione.';
  end;
end;

{ Aggiorna subito le gare salvate (Documenti dell'utente, non dell'amministratore), così un
  eventuale problema emerge adesso e non all'avvio il giorno della gara. }
procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
begin
  if CurStep <> ssPostInstall then
    Exit;
  if not ExecAsOriginalUser(ExpandConstant('{app}\{#AppExe}'), '--migra', '', SW_HIDE, ewWaitUntilTerminated, Code) then
    Exit;
  if Code = 2 then
    SuppressibleMsgBox('Le gare salvate sono state create da una versione più recente di Gare di Mate.' + #13#10#13#10 +
      'Per usarle, installare la versione più recente del programma.', mbError, MB_OK, IDOK)
  else if Code <> 0 then
    SuppressibleMsgBox('Non è stato possibile adattare le gare salvate alla nuova versione.' + #13#10#13#10 +
      'Nessun dato è andato perso: prima di ogni modifica viene salvata una copia di sicurezza ' +
      'nella cartella Documenti\Gare di Mate (file gare-backup-...).' + #13#10#13#10 +
      'I dettagli tecnici sono nel file gare-di-mate.log nella stessa cartella.', mbError, MB_OK, IDOK);
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  if AppIsRunning() then
  begin
    if SuppressibleMsgBox('Gare di Mate è aperto e deve essere chiuso per disinstallarlo.' + #13#10#13#10 +
        'Chiuderlo adesso?', mbConfirmation, MB_YESNO, IDYES) = IDYES then
      CloseApp()
    else
      Result := False;
  end;
end;
