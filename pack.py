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

INCLUDE_DIRS = ["PSWorkspace", "EWS", "IcMHelper", "IcMHelperPS", ".claude"]
INCLUDE_FILES = ["ews_streaming.ps1", "xlsx_search_dir.json"]


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

        # --- Generate config templates ---
        print("[3/5] 生成配置模板...")

        ews_example = {
            "ews": {
                "url": "https://outlook.office365.com/EWS/Exchange.asmx",
                "domain_user": "YOUR_DOMAIN\\YOUR_USERNAME",
                "password": "YOUR_PASSWORD",
                "folder_name": "EDM"
            }
        }
        write_json(staging_path / ".edm_agent_config.json.example", ews_example)
        print("  .edm_agent_config.json.example")

        ps_config_example = {
            "server": {"host": "0.0.0.0", "port": 9000},
            "paths": {
                "project_root": "{{PROJECT_ROOT}}",
                "icm_ps": "IcMHelperPS/IcmApi.ps1",
                "icm_config": "IcMHelperPS/icm_config.json",
                "edm_temp": "EDM/Temp",
                "edm_process": ".claude/skills/edm-process/edm_process.py",
                "edm_dashboard_data": "edmmailanalyzer.json",
                "edm_handlers": ".claude/skills/edm-dashboard/handlers.json",
                "eml_to_msg": ".claude/skills/eml-to-msg/eml_to_msg.py"
            },
            "auth": {"domain": "bj-oe.21vianet.com", "token_expiry_hours": 1},
            "tfs": {"organization": "21via", "project": "PS", "pat": "", "base_url": "https://dev.azure.com/21via"},
            "webhook": {"secret": ""}
        }
        write_json(staging_path / "PSWorkspace" / "ps_workspace_config.json.example", ps_config_example)
        print("  ps_workspace_config.json.example")

        icm_example = {
            "access_token": "", "token_obtained_at": "", "token_expires_at": "",
            "cookie_string": "", "cookie_expires": ""
        }
        write_json(staging_path / "IcMHelperPS" / "icm_config.json.example", icm_example)
        print("  icm_config.json.example (IcMHelperPS)")

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
    PS Workspace 启动脚本 - 双击运行
#>
$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PS Workspace 启动脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 检查 EWS 配置
Write-Host "[检查] 配置文件..." -ForegroundColor Yellow
$EwsConfig = Join-Path $ProjectRoot ".edm_agent_config.json"
if (-not (Test-Path $EwsConfig)) {
    $Example = Join-Path $ProjectRoot ".edm_agent_config.json.example"
    if (Test-Path $Example) {
        Write-Host "[警告] 未找到 .edm_agent_config.json" -ForegroundColor Red
        Write-Host "       请从模板 .edm_agent_config.json.example 复制并填入 EWS 凭据" -ForegroundColor Red
        Write-Host ""
        Read-Host "按回车退出"
        exit
    }
}

# 2. 检查 PS Workspace 配置
$PsConfig = Join-Path $ProjectRoot "PSWorkspace" "ps_workspace_config.json"
if (-not (Test-Path $PsConfig)) {
    $Example = Join-Path $ProjectRoot "PSWorkspace" "ps_workspace_config.json.example"
    if (Test-Path $Example) {
        Write-Host "[警告] 未找到 ps_workspace_config.json" -ForegroundColor Red
        Write-Host "是否从模板创建？(Y/N)" -ForegroundColor Yellow
        $Answer = Read-Host ""
        if ($Answer -eq 'Y' -or $Answer -eq 'y') {
            Copy-Item $Example $PsConfig
            $Content = Get-Content $PsConfig -Raw
            $Content = $Content -replace '{{PROJECT_ROOT}}', $ProjectRoot
            Set-Content $PsConfig $Content -Encoding utf8
            Write-Host "[OK] 已从模板创建 (project_root = $ProjectRoot)" -ForegroundColor Green
        } else {
            Write-Host "需要配置文件才能运行。" -ForegroundColor Red
            Read-Host "按回车退出"
            exit
        }
    }
}

# 3. 检查 ICM 配置
$IcmConfig = Join-Path $ProjectRoot "IcMHelperPS" "icm_config.json"
if (-not (Test-Path $IcmConfig)) {
    $Example = Join-Path $ProjectRoot "IcMHelperPS" "icm_config.json.example"
    if (Test-Path $Example) {
        Write-Host "[提示] 创建空 ICM 配置 (Token 将在运行时自动获取)" -ForegroundColor Yellow
        Copy-Item $Example $IcmConfig
    }
}

# 4. 检查 Python
Write-Host "" -ForegroundColor Cyan
Write-Host "[检查] Python 环境..." -ForegroundColor Yellow
try {
    $PyVersion = python --version 2>&1
    Write-Host "  $PyVersion" -ForegroundColor Gray
} catch {
    Write-Host "[错误] 未找到 Python，请先安装 Python 3.10+" -ForegroundColor Red
    Read-Host "按回车退出"
    exit
}

# 5. 检查依赖包
Write-Host "[检查] Python 依赖包..." -ForegroundColor Yellow
$ReqFile = Join-Path $ProjectRoot "PSWorkspace" "requirements.txt"
if (Test-Path $ReqFile) {
    $Result = python -m pip list 2>$null
    $Missing = @()
    $Packages = Get-Content $ReqFile | Where-Object { $_ -notmatch '^\s*#' -and $_ -notmatch '^\s*$' -and $_ -notmatch '^-' }
    foreach ($pkg in $Packages) {
        $Name = $pkg -replace '[>=<].*', ''
        if ($Result -notmatch [regex]::Escape($Name)) {
            $Missing += $Name
        }
    }
    if ($Missing.Count -gt 0) {
        Write-Host "  [提示] 缺少依赖包: $($Missing -join ', ')" -ForegroundColor Yellow
        $Answer = Read-Host "  是否现在安装？(Y/N)"
        if ($Answer -eq 'Y' -or $Answer -eq 'y') {
            Write-Host "  安装中..." -ForegroundColor Yellow
            python -m pip install -r $ReqFile
            Write-Host "  [OK] 依赖包安装完成" -ForegroundColor Green
        }
    } else {
        Write-Host "  [OK] 所有依赖包已安装" -ForegroundColor Green
    }
}

# 6. 检查关键文件
Write-Host "" -ForegroundColor Cyan
Write-Host "[检查] 关键文件..." -ForegroundColor Yellow
foreach ($f in @("PSWorkspace/app.py", "EWS/lib/40/Microsoft.Exchange.WebServices.dll", "ews_streaming.ps1")) {
    $Path = Join-Path $ProjectRoot $f
    if (Test-Path $Path) {
        Write-Host "  [OK] $f" -ForegroundColor Green
    } else {
        Write-Host "  [缺失] $f" -ForegroundColor Red
    }
}

# 7. 启动
Write-Host "" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  启动 PS Workspace..." -ForegroundColor Cyan
Write-Host "  访问: http://localhost:9000" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "" -ForegroundColor Cyan

Set-Location $ProjectRoot
Set-Location PSWorkspace
python app.py
"""


def generate_readme():
    return """# PS Workspace - 移植包

## 首次运行

右键 `start.ps1` -> 使用 PowerShell 运行

首次运行会自动检查：配置文件、Python、依赖包、关键文件

## 需要手动配置的文件

1. **`.edm_agent_config.json`** - 从 `.edm_agent_config.json.example` 复制并填入 EWS 凭据
2. **`PSWorkspace/ps_workspace_config.json`** - 从模板创建，确认 project_root 路径正确
3. **`IcMHelperPS/icm_config.json`** - 首次运行自动创建空配置，Token 自动刷新获取

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
