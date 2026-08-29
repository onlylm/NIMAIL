#define MyAppName "匿邮 NIMAIL"
#define MyAppVersion "0.3.7"
#define MyPublisher "NIMAIL"
#define MyAdminExe "NIMAIL-Admin.exe"
#define MyServerExe "NIMAIL-Server.exe"

[Setup]
AppId={{D0994545-06D6-49D8-BE44-895EC5C9FDE1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyPublisher}
DefaultDirName={autopf}\NIMAIL
DefaultGroupName=匿邮 NIMAIL
DisableProgramGroupPage=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist-installer
OutputBaseFilename=NIMAIL-Setup
SetupIconFile=..\desktop_assets\logo.ico
UninstallDisplayIcon={app}\{#MyAdminExe}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120
CloseApplications=yes
CloseApplicationsFilter={#MyAdminExe},{#MyServerExe},caddy.exe
RestartApplications=no
SetupLogging=yes
UsePreviousAppDir=yes
MinVersion=10.0.17763
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyPublisher}
VersionInfoDescription=匿邮本机与服务器一键部署安装包
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "..\dist-desktop\{#MyAdminExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist-server\{#MyServerExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\installer_assets\caddy.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\installer_assets\CADDY-LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\desktop_assets\logo.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\匿邮管理端"; Filename: "{app}\{#MyAdminExe}"; WorkingDir: "{app}"
Name: "{group}\匿邮管理端"; Filename: "{app}\{#MyAdminExe}"; WorkingDir: "{app}"
Name: "{group}\打开数据目录"; Filename: "{sys}\explorer.exe"; Parameters: "{commonappdata}\NIMAIL"
Name: "{group}\卸载匿邮"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAdminExe}"; Description: "打开匿邮管理端"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\schtasks.exe"; Parameters: "/End /TN NIMAIL-Server"; Flags: runhidden waituntilterminated; RunOnceId: "EndServerTaskV2"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN NIMAIL-Server /F"; Flags: runhidden waituntilterminated; RunOnceId: "DeleteServerTaskV2"
Filename: "{sys}\schtasks.exe"; Parameters: "/End /TN &quot;NIMAIL Server&quot;"; Flags: runhidden waituntilterminated; RunOnceId: "EndServerTask"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN &quot;NIMAIL Server&quot; /F"; Flags: runhidden waituntilterminated; RunOnceId: "DeleteServerTask"
Filename: "{sys}\sc.exe"; Parameters: "stop NIMAIL-Caddy"; Flags: runhidden waituntilterminated; RunOnceId: "StopCaddy"
Filename: "{sys}\sc.exe"; Parameters: "delete NIMAIL-Caddy"; Flags: runhidden waituntilterminated; RunOnceId: "DeleteCaddy"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=&quot;NIMAIL HTTPS&quot;"; Flags: runhidden waituntilterminated; RunOnceId: "DeleteFirewall"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#MyAdminExe} /T"; Flags: runhidden waituntilterminated; RunOnceId: "KillAdmin"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#MyServerExe} /T"; Flags: runhidden waituntilterminated; RunOnceId: "KillServer"

[Registry]
Root: HKA; Subkey: "Software\NIMAIL"; ValueType: string; ValueName: "DeploymentMode"; ValueData: "{code:GetDeploymentMode}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\NIMAIL"; ValueType: string; ValueName: "PublicDomain"; ValueData: "{code:GetPublicDomain}"; Flags: uninsdeletevalue

[Code]
var
  ModePage: TWizardPage;
  SummaryPage: TWizardPage;
  LocalMode: TNewRadioButton;
  ServerMode: TNewRadioButton;
  DomainLabel: TNewStaticText;
  DomainEdit: TNewEdit;
  ModeHint: TNewStaticText;
  SummaryTitle: TNewStaticText;
  SummaryBody: TNewStaticText;
  IsInstallerSmokeTest: Boolean;

procedure SetModeControls;
begin
  DomainLabel.Enabled := ServerMode.Checked;
  DomainEdit.Enabled := ServerMode.Checked;
  if ServerMode.Checked then
    ModeHint.Caption := '服务器将集中生成邮箱和收信；其他电脑、手机只通过域名 + CDK 查看邮件和复制验证码。'
  else
    ModeHint.Caption := '管理端、邮箱生成、收信和 CDK 查看均在当前电脑完成，不开放公网端口。';
end;

procedure ModeChanged(Sender: TObject);
begin
  SetModeControls;
end;

function NormalizeDomain(Value: String): String;
begin
  Result := Lowercase(Trim(Value));
  StringChangeEx(Result, 'https://', '', True);
  StringChangeEx(Result, 'http://', '', True);
  while (Length(Result) > 0) and (Result[Length(Result)] = '/') do
    Delete(Result, Length(Result), 1);
end;

function DomainLooksValid(Value: String): Boolean;
begin
  Result := (Length(Value) >= 4) and (Pos('.', Value) > 1) and
            (Pos(' ', Value) = 0) and (Pos('/', Value) = 0) and
            (Pos(':', Value) = 0);
end;

function GetDeploymentMode(Param: String): String;
begin
  if ServerMode.Checked then Result := 'server' else Result := 'local';
end;

function GetPublicDomain(Param: String): String;
begin
  if ServerMode.Checked then Result := NormalizeDomain(DomainEdit.Text) else Result := '';
end;

procedure InitializeWizard;
var
  Intro: TNewStaticText;
  RequestedMode, RequestedDomain: String;
begin
  WizardForm.Caption := '匿邮一键部署';

  ModePage := CreateCustomPage(wpSelectDir, '选择部署模式', '这台 Windows 电脑如何使用匿邮？');
  Intro := TNewStaticText.Create(ModePage);
  Intro.Parent := ModePage.Surface;
  Intro.Left := 0;
  Intro.Top := 4;
  Intro.Width := ModePage.SurfaceWidth;
  Intro.AutoSize := False;
  Intro.Height := 34;
  Intro.Caption := '安装包会自动配置管理端、后台收信服务和开机启动。';
  Intro.Font.Color := $007D6B55;

  LocalMode := TNewRadioButton.Create(ModePage);
  LocalMode.Parent := ModePage.Surface;
  LocalMode.Left := 8;
  LocalMode.Top := 52;
  LocalMode.Width := ModePage.SurfaceWidth - 16;
  LocalMode.Height := 28;
  LocalMode.Caption := '本机使用（推荐）';
  LocalMode.Checked := True;
  LocalMode.Font.Style := [fsBold];
  LocalMode.OnClick := @ModeChanged;

  ServerMode := TNewRadioButton.Create(ModePage);
  ServerMode.Parent := ModePage.Surface;
  ServerMode.Left := 8;
  ServerMode.Top := 100;
  ServerMode.Width := ModePage.SurfaceWidth - 16;
  ServerMode.Height := 28;
  ServerMode.Caption := '服务器远程使用';
  ServerMode.Font.Style := [fsBold];
  ServerMode.OnClick := @ModeChanged;

  ModeHint := TNewStaticText.Create(ModePage);
  ModeHint.Parent := ModePage.Surface;
  ModeHint.Left := 30;
  ModeHint.Top := 136;
  ModeHint.Width := ModePage.SurfaceWidth - 44;
  ModeHint.Height := 48;
  ModeHint.AutoSize := False;
  ModeHint.WordWrap := True;
  ModeHint.Font.Color := $00887766;

  DomainLabel := TNewStaticText.Create(ModePage);
  DomainLabel.Parent := ModePage.Surface;
  DomainLabel.Left := 8;
  DomainLabel.Top := 202;
  DomainLabel.Caption := '公网取信域名';
  DomainLabel.Font.Style := [fsBold];

  DomainEdit := TNewEdit.Create(ModePage);
  DomainEdit.Parent := ModePage.Surface;
  DomainEdit.Left := 8;
  DomainEdit.Top := 228;
  DomainEdit.Width := ModePage.SurfaceWidth - 16;
  DomainEdit.Text := 'mail.example.com';

  RequestedMode := Lowercase(ExpandConstant('{param:MODE|}'));
  RequestedDomain := NormalizeDomain(ExpandConstant('{param:DOMAIN|}'));
  IsInstallerSmokeTest := CompareText(ExpandConstant('{param:NIMAILTEST|0}'), '1') = 0;
  if RequestedMode = 'server' then
  begin
    ServerMode.Checked := True;
    LocalMode.Checked := False;
  end;
  if RequestedDomain <> '' then
    DomainEdit.Text := RequestedDomain;

  SetModeControls;

  SummaryPage := CreateCustomPage(ModePage.ID, '确认安装配置', '安装前请确认使用方式和访问范围');
  SummaryTitle := TNewStaticText.Create(SummaryPage);
  SummaryTitle.Parent := SummaryPage.Surface;
  SummaryTitle.Left := 0;
  SummaryTitle.Top := 12;
  SummaryTitle.Width := SummaryPage.SurfaceWidth;
  SummaryTitle.Height := 34;
  SummaryTitle.AutoSize := False;
  SummaryTitle.Font.Size := 13;
  SummaryTitle.Font.Style := [fsBold];

  SummaryBody := TNewStaticText.Create(SummaryPage);
  SummaryBody.Parent := SummaryPage.Surface;
  SummaryBody.Left := 0;
  SummaryBody.Top := 58;
  SummaryBody.Width := SummaryPage.SurfaceWidth;
  SummaryBody.Height := 240;
  SummaryBody.AutoSize := False;
  SummaryBody.WordWrap := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if ServerMode.Checked and not DomainLooksValid(NormalizeDomain(DomainEdit.Text)) then
    Result := '服务器远程模式需要有效域名，例如 mail.example.com。';
end;

procedure CurPageChanged(CurPageID: Integer);
var
  Domain: String;
begin
  if CurPageID = SummaryPage.ID then
  begin
    if ServerMode.Checked then
    begin
      Domain := NormalizeDomain(DomainEdit.Text);
      SummaryTitle.Caption := '服务器远程模式';
      SummaryBody.Caption :=
        '安装位置：' + WizardDirValue + #13#10#13#10 +
        '管理方式：只允许在服务器本机使用管理端' + #13#10 +
        '公开地址：https://' + Domain + '/c/CDK' + #13#10 +
        '公开范围：CDK 页面、邮件列表、验证码识别与复制' + #13#10 +
        '自动配置：后台任务、Caddy 自动证书服务、Windows 防火墙 443' + #13#10#13#10 +
        '不会公开：管理员登录、邮箱生成、删除、Apple Cookie 和 IMAP 配置。';
    end
    else
    begin
      SummaryTitle.Caption := '本机模式';
      SummaryBody.Caption :=
        '安装位置：' + WizardDirValue + #13#10#13#10 +
        '管理地址：http://127.0.0.1:8788' + #13#10 +
        'CDK 取信：http://127.0.0.1:8788/c/CDK' + #13#10 +
        '自动配置：管理端、后台收信任务和开机启动' + #13#10 +
        '公网端口：不开放。';
    end;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Domain: String;
begin
  Result := True;
  if (CurPageID = ModePage.ID) and ServerMode.Checked then
  begin
    Domain := NormalizeDomain(DomainEdit.Text);
    if not DomainLooksValid(Domain) then
    begin
      MsgBox('请输入有效域名，例如 mail.example.com。不要填写 http://、端口或路径。', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    DomainEdit.Text := Domain;
  end;
end;

function RunHidden(FileName, Parameters: String): Integer;
var
  ExitCode: Integer;
begin
  if not Exec(FileName, Parameters, '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
    Result := -1
  else
    Result := ExitCode;
end;

procedure WaitForCaddyRemoval;
var
  Attempt, QueryResult: Integer;
begin
  { sc delete 只会先标记删除，升级时必须等待 SCM 彻底释放同名服务。 }
  for Attempt := 1 to 40 do
  begin
    QueryResult := RunHidden(ExpandConstant('{sys}\sc.exe'), 'query NIMAIL-Caddy');
    if QueryResult <> 0 then
      Exit;
    Sleep(250);
  end;
end;

procedure RemoveRemoteAccess;
begin
  RunHidden(ExpandConstant('{sys}\sc.exe'), 'stop NIMAIL-Caddy');
  RunHidden(ExpandConstant('{sys}\sc.exe'), 'delete NIMAIL-Caddy');
  WaitForCaddyRemoval;
  RunHidden(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="NIMAIL HTTPS"');
end;

procedure RemoveServerTasks;
begin
  RunHidden(ExpandConstant('{sys}\schtasks.exe'), '/End /TN NIMAIL-Server');
  RunHidden(ExpandConstant('{sys}\schtasks.exe'), '/Delete /TN NIMAIL-Server /F');
  { 清理旧版本使用的任务名称。 }
  RunHidden(ExpandConstant('{sys}\schtasks.exe'), '/End /TN "NIMAIL Server"');
  RunHidden(ExpandConstant('{sys}\schtasks.exe'), '/Delete /TN "NIMAIL Server" /F');
end;

procedure StartServerDirectly(ServerPath: String);
var
  ExitCode: Integer;
begin
  if not Exec(ServerPath, '', ExpandConstant('{app}'), SW_HIDE, ewNoWait, ExitCode) then
    Log('NIMAIL Server 直接启动失败。');
end;

procedure ConfigureServerTask;
var
  ServerPath, RunValue: String;
  SetupResult: Integer;
begin
  ServerPath := ExpandConstant('{app}\{#MyServerExe}');
  RunValue := '"' + ServerPath + '"';
  RemoveServerTasks;
  { 由 Server EXE 以参数数组调用 schtasks，避免 Program Files 路径和 XML 模式错误。 }
  SetupResult := RunHidden(ServerPath, '--install-server-task');
  if SetupResult = 0 then
  begin
    RegDeleteValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Run', 'NIMAIL Server');
  end
  else
  begin
    { 部分精简版 Windows 会禁用任务计划程序；退回到登录启动，不中止安装。 }
    RegWriteStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Run',
      'NIMAIL Server', RunValue);
    StartServerDirectly(ServerPath);
    SuppressibleMsgBox(
      'Windows 未能创建 NIMAIL Server 开机任务（退出码 ' + IntToStr(SetupResult) + '）。' + #13#10#13#10 +
      '安装已继续，后台现已直接启动，并设置为管理员登录 Windows 后自动启动。',
      mbInformation, MB_OK, IDOK);
  end;
end;

procedure WriteDeploymentInfo(Mode, Domain: String);
var
  DataDir, Json: String;
begin
  DataDir := ExpandConstant('{commonappdata}\NIMAIL');
  ForceDirectories(DataDir);
  Json := '{"mode":"' + Mode + '","domain":"' + Domain + '"}';
  SaveStringToFile(DataDir + '\deployment.json', Json, False);
end;

procedure ConfigureRemoteAccess;
var
  AppDir, Domain, ServerPath: String;
  GatewayResult: Integer;
begin
  AppDir := ExpandConstant('{app}');
  Domain := NormalizeDomain(DomainEdit.Text);
  { 先保存部署模式，后续系统服务失败也不能让 CDK 链接退回 127.0.0.1。 }
  WriteDeploymentInfo('server', Domain);
  RemoveRemoteAccess;
  ServerPath := AppDir + '\{#MyServerExe}';
  { Server EXE 使用 subprocess 参数数组创建服务，不再经过 Inno 的多层引号。 }
  GatewayResult := RunHidden(ServerPath, '--install-caddy "' + Domain + '"');
  if GatewayResult <> 0 then
    SuppressibleMsgBox(
      '服务器域名 https://' + Domain + ' 已保存，CDK 将按该域名导出。' + #13#10#13#10 +
      '无法完成 HTTPS 网关自动配置（退出码 ' + IntToStr(GatewayResult) +
      '）。请检查 443 端口占用，或在安装后的“服务器设置”中再保存一次域名。',
      mbInformation, MB_OK, IDOK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if IsInstallerSmokeTest then
      Exit;
    ConfigureServerTask;
    if ServerMode.Checked then
      ConfigureRemoteAccess
    else
    begin
      RemoveRemoteAccess;
      DeleteFile(ExpandConstant('{app}\Caddyfile'));
      WriteDeploymentInfo('local', '');
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    RemoveServerTasks;
    RegDeleteValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Run', 'NIMAIL Server');
  end;
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) then
    MsgBox('匿邮程序已卸载。邮箱、CDK 和邮件数据库仍保留在：' + #13#10 +
      ExpandConstant('{commonappdata}\NIMAIL') + #13#10#13#10 +
      '如需永久清除数据，请手动备份后删除该目录。', mbInformation, MB_OK);
end;
