"""Script runner - wrapper for invoking Python and PowerShell scripts."""
import subprocess
import os
import sys
import logging
import json
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.environ.get(
    "PROJECT_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)


def run_python(script: str, args: Optional[List[str]] = None,
               cwd: Optional[str] = None) -> tuple:
    """Run a Python script. Returns (stdout, stderr, returncode)."""
    if cwd is None:
        cwd = PROJECT_ROOT

    script_path = os.path.join(PROJECT_ROOT, script) if not os.path.isabs(script) else script
    cmd = [sys.executable or "python", script_path]
    if args:
        cmd.extend(args)

    logger.info(f"Running Python: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Script timed out (300s)", -1
    except Exception as e:
        return "", str(e), -1


def run_powershell(script: str, params: Optional[Dict[str, Any]] = None,
                   cwd: Optional[str] = None,
                   dot_source: Optional[str] = None) -> tuple:
    """Run a PowerShell script. Returns (stdout, stderr, returncode).

    Args:
        script: Path to the PS1 script
        params: Dictionary of script parameters
        cwd: Working directory
        dot_source: Another PS1 file to dot-source first (e.g. IcmApi.ps1)
    """
    if cwd is None:
        cwd = PROJECT_ROOT

    if not os.path.isabs(script):
        script = os.path.join(PROJECT_ROOT, script)

    # Build parameter string
    param_str = ""
    if params:
        for k, v in params.items():
            if isinstance(v, str):
                param_str += f" -{k} '{v.replace("'", "''")}'"
            else:
                param_str += f" -{k} {json.dumps(v)}"

    ps_cmd = f"& '{{path}}'{param_str}".format(path=script)

    if dot_source:
        if not os.path.isabs(dot_source):
            dot_source = os.path.join(PROJECT_ROOT, dot_source)
        ps_cmd = f". '{{path}}'; {ps_cmd}".format(path=dot_source)

    full_cmd = [
        "pwsh", "-NoProfile", "-NonInteractive", "-Command",
        "$ErrorActionPreference='Continue'; " + ps_cmd,
    ]

    # Fallback to powershell.exe if pwsh not available
    try:
        subprocess.run(["pwsh", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        full_cmd = [
            "powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-Command", "$ErrorActionPreference='Continue'; " + ps_cmd,
        ]

    logger.info(f"Running PowerShell: {script}")
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "PowerShell script timed out (300s)", -1
    except Exception as e:
        return "", str(e), -1


def run_powershell_function(ps1_file: str, function: str,
                            params: Optional[Dict[str, Any]] = None,
                            cwd: Optional[str] = None) -> tuple:
    """Dot-source a PS1 file and call a specific function.

    Args:
        ps1_file: Path to the PS1 file containing the function
        function: Function name to call
        params: Function parameters
        cwd: Working directory
    """
    if cwd is None:
        cwd = PROJECT_ROOT

    if not os.path.isabs(ps1_file):
        ps1_file = os.path.join(PROJECT_ROOT, ps1_file)

    # Build parameter string for function call
    param_str = ""
    if params:
        for k, v in params.items():
            if isinstance(v, str):
                param_str += f" -{k} '{v.replace("'", "''")}'"
            elif isinstance(v, bool):
                param_str += f" -{k} ${v}"
            elif isinstance(v, list):
                param_str += f" -{k} @({','.join(json.dumps(x) for x in v)})"
            else:
                param_str += f" -{k} {json.dumps(v)}"

    ps_cmd = f". '{{path}}'; {function}{param_str}".format(path=ps1_file)

    full_cmd = [
        "powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-Command", ps_cmd,
    ]

    logger.info(f"Running PS function: {function} from {ps1_file}")
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "PowerShell timed out (300s)", -1
    except Exception as e:
        return "", str(e), -1
