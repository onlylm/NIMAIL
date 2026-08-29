param(
    [switch]$SkipApplicationBuild
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$assetDir = Join-Path $projectRoot 'installer_assets'
$toolDir = Join-Path $projectRoot '.tools'
$innoDir = Join-Path $toolDir 'InnoSetup'
$innoCompiler = Join-Path $innoDir 'ISCC.exe'
$caddyVersion = '2.11.4'
$caddyArchiveName = "caddy_${caddyVersion}_windows_amd64.zip"
$caddyBaseUrl = "https://github.com/caddyserver/caddy/releases/download/v$caddyVersion"

New-Item -ItemType Directory -Force -Path $assetDir, $toolDir | Out-Null

if (-not $SkipApplicationBuild) {
    & (Join-Path $projectRoot 'build_server_windows.ps1')
    if ($LASTEXITCODE -ne 0) { throw '服务器程序构建失败。' }
    & (Join-Path $projectRoot 'build_desktop_windows.ps1')
    if ($LASTEXITCODE -ne 0) { throw '管理端程序构建失败。' }
}

$caddyExe = Join-Path $assetDir 'caddy.exe'
$caddyLicense = Join-Path $assetDir 'CADDY-LICENSE.txt'
if (-not (Test-Path -LiteralPath $caddyExe)) {
    $downloadDir = Join-Path $toolDir "caddy-$caddyVersion"
    $archivePath = Join-Path $downloadDir $caddyArchiveName
    $checksumsPath = Join-Path $downloadDir "caddy_${caddyVersion}_checksums.txt"
    New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null
    Invoke-WebRequest -UseBasicParsing -Uri "$caddyBaseUrl/$caddyArchiveName" -OutFile $archivePath
    Invoke-WebRequest -UseBasicParsing -Uri "$caddyBaseUrl/caddy_${caddyVersion}_checksums.txt" -OutFile $checksumsPath

    $checksumLine = Get-Content -LiteralPath $checksumsPath | Where-Object { $_ -match [regex]::Escape($caddyArchiveName) } | Select-Object -First 1
    if (-not $checksumLine) { throw 'Caddy 校验文件中没有找到 Windows x64 安装包。' }
    $expectedHash = ($checksumLine -split '\s+')[0].Trim().ToUpperInvariant()
    $algorithm = if ($expectedHash.Length -eq 128) { 'SHA512' } elseif ($expectedHash.Length -eq 64) { 'SHA256' } else { throw '无法识别 Caddy 校验算法。' }
    $actualHash = (Get-FileHash -Algorithm $algorithm -LiteralPath $archivePath).Hash.ToUpperInvariant()
    if ($actualHash -ne $expectedHash) { throw 'Caddy 下载文件校验失败。' }

    $extractDir = Join-Path $downloadDir 'expanded'
    if (Test-Path -LiteralPath $extractDir) { Remove-Item -LiteralPath $extractDir -Recurse -Force }
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extractDir -Force
    Copy-Item -LiteralPath (Join-Path $extractDir 'caddy.exe') -Destination $caddyExe -Force
    Copy-Item -LiteralPath (Join-Path $extractDir 'LICENSE') -Destination $caddyLicense -Force
}

if (-not (Test-Path -LiteralPath $innoCompiler)) {
    $installedCandidates = @(
        'C:\Program Files (x86)\Inno Setup 7\ISCC.exe',
        'C:\Program Files\Inno Setup 7\ISCC.exe',
        'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 7\ISCC.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
    )
    $existingCompiler = $installedCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($existingCompiler) {
        $innoCompiler = $existingCompiler
    } else {
        $innoInstaller = Join-Path $toolDir 'inno-setup.exe'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/jrsoftware/issrc/releases/download/is-7_1_0/innosetup-7.1.0-x64.exe' -OutFile $innoInstaller
        $magic = [System.IO.File]::ReadAllBytes($innoInstaller)[0..1]
        if ($magic[0] -ne 0x4D -or $magic[1] -ne 0x5A) { throw 'Inno Setup 下载结果不是有效的 Windows 程序。' }
        $signature = Get-AuthenticodeSignature -LiteralPath $innoInstaller
        if ($signature.Status -ne 'Valid') { throw "Inno Setup 安装程序签名无效：$($signature.Status)" }
        New-Item -ItemType Directory -Force -Path $innoDir | Out-Null
        $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=$innoDir")
        $process = Start-Process -FilePath $innoInstaller -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
        if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $innoCompiler)) {
            throw 'Inno Setup 编译器安装失败。'
        }
    }
}

$installerScript = Join-Path $projectRoot 'installer\NIMAIL.iss'
& $innoCompiler '/Qp' $installerScript
if ($LASTEXITCODE -ne 0) { throw 'NIMAIL 一键安装包构建失败。' }

$output = Join-Path $projectRoot 'dist-installer\NIMAIL-Setup.exe'
if (-not (Test-Path -LiteralPath $output)) { throw '安装包输出文件不存在。' }
Write-Host "构建完成：$output"
