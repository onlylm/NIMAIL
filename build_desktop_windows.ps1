$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $projectRoot '.venv-desktop\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw '缺少 .venv-desktop，请先创建桌面端构建环境并安装 desktop-requirements.txt。'
}

Set-Location -LiteralPath $projectRoot
$originalPath = $env:PATH
try {
    # Codex 工作区的 Poppler 自带另一套 ICU。构建 Qt 时必须排除该目录，
    # 否则 PyInstaller 会误打包不兼容的 ICU，导致 QtGui 启动失败。
    $env:PATH = (($originalPath -split ';') | Where-Object { $_ -notmatch '[\\/]poppler[\\/]' }) -join ';'
    & $pythonExe -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name 'NIMAIL-Admin' `
        --icon 'desktop_assets\logo.ico' `
        --add-data 'desktop_assets;desktop_assets' `
        --distpath 'dist-desktop' `
        --workpath 'build-desktop' `
        desktop_app.py
} finally {
    $env:PATH = $originalPath
}

if ($LASTEXITCODE -ne 0) { throw '桌面管理端构建失败。' }
$serverSource = Join-Path $projectRoot 'dist-server\NIMAIL-Server.exe'
$serverTarget = Join-Path $projectRoot 'dist-desktop\NIMAIL-Server.exe'
if (Test-Path -LiteralPath $serverSource) {
    Copy-Item -LiteralPath $serverSource -Destination $serverTarget -Force
}
Write-Host "构建完成：$(Join-Path $projectRoot 'dist-desktop\NIMAIL-Admin.exe')"
