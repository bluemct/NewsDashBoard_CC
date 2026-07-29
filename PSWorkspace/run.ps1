# PS Workspace - PowerShell Launch Script
# Usage: .\PSWorkspace\run.ps1

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "PS Workspace - 启动中..." -ForegroundColor Cyan
Write-Host "项目目录: $ProjectRoot" -ForegroundColor Gray

# Set environment variable so app.py knows the project root
$env:PROJECT_ROOT = $ProjectRoot

# Check if Python is available
try {
    $python = Get-Command python -ErrorAction Stop
    Write-Host "Python: $($python.Source)" -ForegroundColor Green
} catch {
    Write-Host "错误: 找不到 Python" -ForegroundColor Red
    exit 1
}

# Install dependencies if needed
$requirementsFile = Join-Path $ScriptDir "requirements.txt"
if (Test-Path $requirementsFile) {
    Write-Host "安装依赖..." -ForegroundColor Yellow
    python -m pip install -r $requirementsFile --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "依赖安装失败" -ForegroundColor Red
        exit 1
    }
}

# Start Flask app
Write-Host ""
Write-Host "PS Workspace 运行在 http://0.0.0.0:9000" -ForegroundColor Green
Write-Host "按 Ctrl+C 停止服务" -ForegroundColor Gray
Write-Host ""

Set-Location $ScriptDir
python app.py
