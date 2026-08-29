$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $projectRoot '.venv-server\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw '缺少 .venv-server，请先创建服务器构建环境并安装 server-requirements.txt。'
}

Set-Location -LiteralPath $projectRoot
& $pythonExe -m PyInstaller --noconfirm --clean --onefile --console `
    --name 'NIMAIL-Server' `
    --icon 'desktop_assets\logo.ico' `
    --add-data 'server_web;server_web' `
    --distpath 'dist-server' `
    --workpath 'build-server' `
    server_app.py

if ($LASTEXITCODE -ne 0) { throw '服务器构建失败。' }
$desktopDist = Join-Path $projectRoot 'dist-desktop'
if (Test-Path -LiteralPath $desktopDist) {
    Copy-Item -LiteralPath (Join-Path $projectRoot 'dist-server\NIMAIL-Server.exe') `
        -Destination (Join-Path $desktopDist 'NIMAIL-Server.exe') -Force
}
Write-Host "构建完成：$(Join-Path $projectRoot 'dist-server\NIMAIL-Server.exe')"
