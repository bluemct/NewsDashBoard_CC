"""PS Workspace Pack Script - Creates a deployment zip package."""
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
ZIP_NAME = "AgentProject_PSWorkspace.zip"

EXCLUDE_PATTERNS = [
    "__pycache__", "*.pyc", "*.pyo", ".git", "Log", "EDM", "Temp",
    "build", "dist", "*.log", "*.db", "*.sqlite", ".claude_backups",
    ".session_snapshots", "refresh_log.jsonl", "test_", "*.spec",
    ".edm_auth", "results", "reports", "unimarketing-dotnet-api",
    "listverify", "runoob-claude-demo", "_edm_build",
    "edm_email_dump", "test_word_export.files", "contacts_349913.json",
    "task_status.json", "compare_body.html", "compare_tr2.html",
    "dashboard.html", "gui_screenshot.png", "request_3233091.xml",
    "edm_agent_seen.json", "*.zip",
    "scheduled_tasks.json",
]

# Machine-specific files to exclude (exact relative paths, not patterns)
EXCLUDE_EXACT = {
    ".claude/settings.json",
    ".claude/settings.local.json",
}

# Directories to exclude (applied to path components, not filenames)
EXCLUDE_DIRS = [
    "Microsoft",          # Office temp folder, NOT EWS DLLs
    "worktrees",          # .claude/worktrees/ — not needed
    "projects",           # .claude/projects/ — memory, not needed
]

INCLUDE_DIRS = ["PSWorkspace", "EWS", "IcMHelper", ".claude"]
INCLUDE_FILES = ["ews_streaming.ps1", "xlsx_search_dir.json", "Tokenmapping.json",
                 "unimarketing_test_list.py", "verify_list_contacts.py", "deep_verify_list.py"]


def should_exclude(rel_path, full_path):
    """Check if a file should be excluded based on its relative path."""
    # Exact path exclusions (for .claude root-level config files)
    if rel_path in EXCLUDE_EXACT:
        return True
    # Wildcard and substring patterns
    for pat in EXCLUDE_PATTERNS:
        if pat.startswith("*"):
            if rel_path.endswith(pat[1:]):
                return True
        elif pat in rel_path:
            return True
    # Check directory components to avoid matching filenames (e.g., Microsoft.Exchange.WebServices.dll)
    for part in full_path.parts:
        if part in EXCLUDE_DIRS:
            return True
    return False


def copy_directory(src_dir, dst_dir):
    """Copy directory excluding patterns."""
    count = 0
    src = Path(src_dir)
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        rel = str(f.relative_to(src))
        if should_exclude(rel, f):
            continue
        dest = dst_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        count += 1
    return count


def main():
    staging = tempfile.mkdtemp(prefix="ps_workspace_pack_")
    staging_path = Path(staging)
    zip_path = PROJECT_ROOT / ZIP_NAME

    try:
        print("[1/5] 创建临时目录...")

        print("[2/5] 复制文件到临时目录...")
        for dir_name in INCLUDE_DIRS:
            src = PROJECT_ROOT / dir_name
            if src.exists():
                count = copy_directory(src, staging_path / dir_name)
                print(f"  {dir_name}: {count} 文件")

        for file_name in INCLUDE_FILES:
            src = PROJECT_ROOT / file_name
            if src.exists():
                shutil.copy2(src, staging_path / file_name)
                print(f"  {file_name}")

        # --- Copy real config files as-is (preserve all credentials, paths, etc.) ---
        print("[3/5] 复制配置文件（保留真实信息）...")
        real_configs = [
            ".edm_agent_config.json",
            "PSWorkspace/ps_workspace_config.json",
            "IcMHelper/icm_config.json",
            "xlsx_search_dir.json",
        ]
        for cfg in real_configs:
            src = PROJECT_ROOT / cfg
            if src.exists():
                dest = staging_path / cfg
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                print(f"  {cfg} (真实配置)")
            else:
                print(f"  {cfg} (不存在，跳过)")

        # --- Generate start.ps1 ---
        print("[4/5] 生成启动脚本...")
        start_ps1 = generate_start_ps1()
        (staging_path / "start.ps1").write_text(start_ps1, encoding="utf-8")
        print("  start.ps1")

        readme = generate_readme()
        (staging_path / "README.md").write_text(readme, encoding="utf-8")
        print("  README.md")

        # --- Create zip ---
        print("[5/5] 打包为 zip...")
        if zip_path.exists():
            zip_path.unlink()

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in staging_path.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(staging_path)
                    zf.write(f, rel)

        size_mb = zip_path.stat().st_size / (1024 * 1024)
        print(f"\n========================================")
        print(f"  打包完成！")
        print(f"  文件: {zip_path}")
        print(f"  大小: {size_mb:.2f} MB")
        print(f"========================================")

    finally:
        shutil.rmtree(staging, ignore_errors=True)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def generate_start_ps1():
    return r"""<#
.SYNOPSIS
    PS Workspace Launcher - Right-click and "Run with PowerShell"
#>
$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PS Workspace Launcher" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check config files
Write-Host "[Check] Config files..." -ForegroundColor Yellow
$Missing = $false
$cfg1 = Join-Path $ProjectRoot ".edm_agent_config.json"
if (Test-Path $cfg1) {
    Write-Host "  [OK] .edm_agent_config.json" -ForegroundColor Green
} else {
    Write-Host "  [MISSING] .edm_agent_config.json" -ForegroundColor Red
    $Missing = $true
}
$cfg2 = Join-Path (Join-Path $ProjectRoot "PSWorkspace") "ps_workspace_config.json"
if (Test-Path $cfg2) {
    Write-Host "  [OK] ps_workspace_config.json" -ForegroundColor Green
} else {
    Write-Host "  [MISSING] ps_workspace_config.json" -ForegroundColor Red
    $Missing = $true
}

# ICM config is optional
$IcmConfig = Join-Path (Join-Path $ProjectRoot "IcMHelper") "icm_config.json"
if (-not (Test-Path $IcmConfig)) {
    Write-Host "  [INFO] icm_config.json not found — Token will be auto-fetched at runtime" -ForegroundColor Yellow
}

if ($Missing) {
    Write-Host ""
    Write-Host "[ERROR] Required config files are missing. Cannot start." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit
}

# 2. Check Python
Write-Host "" -ForegroundColor Cyan
Write-Host "[Check] Python environment..." -ForegroundColor Yellow
try {
    $PyVersion = python --version 2>&1
    Write-Host "  $PyVersion" -ForegroundColor Gray
} catch {
    Write-Host "[ERROR] Python not found. Please install Python 3.10+ first." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit
}

# 3. Check Python dependencies
Write-Host "[Check] Python dependencies..." -ForegroundColor Yellow
$ReqFile = Join-Path (Join-Path $ProjectRoot "PSWorkspace") "requirements.txt"
if (Test-Path $ReqFile) {
    $Result = python -m pip list 2>$null -ErrorAction SilentlyContinue
    $MissingPkgs = @()
    $Packages = Get-Content $ReqFile | Where-Object { $_ -notmatch '^\s*#' -and $_ -notmatch '^\s*$' -and $_ -notmatch '^-' }
    foreach ($pkg in $Packages) {
        $Name = $pkg -replace '[>=<].*', ''
        if ($Result -notmatch [regex]::Escape($Name)) {
            $MissingPkgs += $Name
        }
    }
    if ($MissingPkgs.Count -gt 0) {
        Write-Host "  [INFO] Missing packages: $($MissingPkgs -join ', ')" -ForegroundColor Yellow
        $Answer = Read-Host "  Install now? (Y/N)"
        if ($Answer -eq 'Y' -or $Answer -eq 'y') {
            Write-Host "  Installing..." -ForegroundColor Yellow
            python -m pip install -r $ReqFile
            Write-Host "  [OK] Dependencies installed" -ForegroundColor Green
        }
    } else {
        Write-Host "  [OK] All dependencies installed" -ForegroundColor Green
    }
}

# 4. Check key files
Write-Host "" -ForegroundColor Cyan
Write-Host "[Check] Key files..." -ForegroundColor Yellow
foreach ($f in @("PSWorkspace/app.py", "EWS/lib/40/Microsoft.Exchange.WebServices.dll",
                 "ews_streaming.ps1", "unimarketing_test_list.py",
                 "verify_list_contacts.py", "deep_verify_list.py")) {
    $Path = Join-Path $ProjectRoot $f
    if (Test-Path $Path) {
        Write-Host "  [OK] $f" -ForegroundColor Green
    } else {
        Write-Host "  [MISSING] $f" -ForegroundColor Red
    }
}

# 5. Launch
Write-Host "" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Starting PS Workspace..." -ForegroundColor Cyan
Write-Host "  URL: http://localhost:9000" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "" -ForegroundColor Cyan

Set-Location $ProjectRoot
Set-Location PSWorkspace
python app.py
"""


def generate_readme():
    return """# PS Workspace - 完整打包

## 首次运行

右键 `start.ps1` -> 使用 PowerShell 运行

启动脚本会自动检查：配置文件、Python、依赖包、关键文件

## 配置文件（已包含，无需手动创建）

- `.edm_agent_config.json` — EWS 凭据及 EDM 监听配置（已包含真实信息）
- `PSWorkspace/ps_workspace_config.json` — Flask 应用配置（已包含真实路径）
- `IcMHelper/icm_config.json` — ICM Token 配置（如不存在，Token 将在运行时自动获取）

## 前置条件

- Python 3.10+ (安装时勾选 Add to PATH)
- Microsoft Outlook (登录 Exchange)
- 域成员 (bj-oe.21vianet.com)
- PowerShell 5.1+ (Windows 自带)

## 手动安装依赖

```
pip install -r PSWorkspace/requirements.txt
```

## 防火墙（如需从其他设备访问）

```powershell
New-NetFirewallRule -DisplayName 'PS Workspace' -Direction Inbound -LocalPort 9000 -Protocol TCP -Action Allow
```
"""


if __name__ == "__main__":
    main()
