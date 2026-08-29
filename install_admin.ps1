$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$exePath = Join-Path $projectRoot 'dist-desktop\NIMAIL-Admin.exe'
if (-not (Test-Path -LiteralPath $exePath)) { throw '请先运行 build_desktop_windows.ps1。' }

$desktop = [Environment]::GetFolderPath('Desktop')
$startMenu = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs'

function New-NimailShortcut([string]$path) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($path)
    $shortcut.TargetPath = $exePath
    $shortcut.WorkingDirectory = Split-Path -Parent $exePath
    $shortcut.Description = '匿邮服务器管理端'
    $shortcut.IconLocation = "$exePath,0"
    $shortcut.Save()
}

New-NimailShortcut (Join-Path $desktop '匿邮管理端.lnk')
New-NimailShortcut (Join-Path $startMenu '匿邮管理端.lnk')
Write-Host '桌面和开始菜单快捷方式已创建。'
