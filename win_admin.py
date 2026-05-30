#!/usr/bin/env python3
"""
win_admin.py — Execute Windows admin commands from WSL2 via a scheduled task.

Uses a Windows Scheduled Task (WSL_ADMIN) registered to run at highest privilege.
Commands are written to a .bat file on the Windows side, the task is triggered via
schtasks.exe, and output is captured through a shared output file. You approve the
UAC elevation exactly once (when registering the task) — never again at call time.

Setup (one-time, in an elevated PowerShell):
    schtasks /create /tn "WSL_ADMIN" /tr "C:\\temp\\wsl_admin_cmd.bat" /sc once /st 00:00 /rl highest /f

Usage:
    python3 win_admin.py run "netsh interface portproxy show all"
    python3 win_admin.py run "usbipd bind --busid 6-3 --force"
    python3 win_admin.py run-multi "usbipd detach --busid 6-3" "usbipd unbind --busid 6-3"
    python3 win_admin.py powershell "Get-Service | Where-Object {$_.Status -eq 'Running'}"
    python3 win_admin.py status
    python3 win_admin.py test
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Log next to the script by default; override with WIN_ADMIN_LOG.
LOG_FILE = Path(os.environ.get("WIN_ADMIN_LOG", SCRIPT_DIR / "logs" / "win_admin.log"))

POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"

# Shared scratch files on the Windows side (visible from WSL via /mnt/c).
# Override the Windows temp dir with WIN_ADMIN_TEMP (e.g. "C:\\temp").
WIN_TEMP = os.environ.get("WIN_ADMIN_TEMP", "C:\\temp")
_WIN_TEMP_WSL = "/mnt/c/" + WIN_TEMP.split(":", 1)[1].replace("\\", "/").lstrip("/")
BAT_FILE = Path(_WIN_TEMP_WSL) / "wsl_admin_cmd.bat"
OUTPUT_FILE = Path(_WIN_TEMP_WSL) / "wsl_admin_output.txt"
TASK_NAME = os.environ.get("WIN_ADMIN_TASK", "WSL_ADMIN")


def _win_path(wsl_path):
    """Convert a /mnt/c/... path to a Windows C:\\... path for use inside .bat."""
    s = str(wsl_path)
    if s.startswith("/mnt/") and len(s) > 6:
        drive = s[5].upper()
        return drive + ":" + s[6:].replace("/", "\\")
    return s


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Core: admin task execution ───────────────────────────────


def run_admin(commands, wait=3, capture_output=True):
    """
    Execute command(s) as Windows admin via the scheduled task.

    Args:
        commands: str or list of str — command(s) to execute
        wait: seconds to wait for completion
        capture_output: if True, redirect stdout to the output file and return it

    Returns:
        (output_text, success_bool)
    """
    if isinstance(commands, str):
        commands = [commands]

    BAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    out_win = _win_path(OUTPUT_FILE)

    # Build .bat content
    lines = ["@echo off"]
    if capture_output:
        lines.append(f'del "{out_win}" 2>nul')
        for cmd in commands:
            lines.append(f'{cmd} >> "{out_win}" 2>&1')
        lines.append(f'echo __DONE__ >> "{out_win}"')
    else:
        for cmd in commands:
            lines.append(cmd)

    bat_content = "\r\n".join(lines) + "\r\n"
    BAT_FILE.write_text(bat_content)

    # Clear previous output
    if capture_output:
        try:
            OUTPUT_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    # Trigger the scheduled task
    try:
        result = subprocess.run(
            ["schtasks.exe", "/run", "/tn", TASK_NAME],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "does not exist" in stderr or "not been created" in stderr:
                return (
                    f"ERROR: Scheduled task '{TASK_NAME}' not found.\n"
                    f"See the README for one-time setup instructions.",
                    False,
                )
            return f"schtasks error: {stderr}", False
    except subprocess.TimeoutExpired:
        return "schtasks timed out", False

    # Wait for completion — poll for __DONE__ marker in the output file
    if capture_output:
        deadline = time.time() + wait + 10
        while time.time() < deadline:
            time.sleep(0.5)
            try:
                if OUTPUT_FILE.exists():
                    content = OUTPUT_FILE.read_text(errors="replace")
                    if "__DONE__" in content:
                        return content.replace("__DONE__", "").strip(), True
            except Exception:
                pass
        # Timeout — return whatever we have
        try:
            if OUTPUT_FILE.exists():
                content = OUTPUT_FILE.read_text(errors="replace").replace("__DONE__", "").strip()
                if content:
                    return content, True
        except Exception:
            pass
        return "(no output — task may still be running)", False
    else:
        time.sleep(wait)
        return "", True


def run_powershell_admin(ps_command, wait=5):
    """Execute a PowerShell command as admin."""
    cmd = f'powershell.exe -NoProfile -Command "{ps_command}"'
    return run_admin(cmd, wait=wait)


def powershell(cmd, timeout=15):
    """Run a non-admin PowerShell command directly (no elevation)."""
    try:
        result = subprocess.run(
            [POWERSHELL, "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "Timed out", 1
    except Exception as e:
        return str(e), 1


# ── Programmatic API (for importing into your own scripts) ────


def admin_cmd(commands, wait=3):
    """
    Run admin command(s) from another script.

    Usage:
        from win_admin import admin_cmd
        output, ok = admin_cmd("usbipd bind --busid 6-3 --force")
        output, ok = admin_cmd(["cmd1", "cmd2"])
    """
    return run_admin(commands, wait=wait, capture_output=True)


def admin_cmd_no_output(commands, wait=3):
    """Run admin command(s) without capturing output (faster)."""
    return run_admin(commands, wait=wait, capture_output=False)


# ── CLI commands ─────────────────────────────────────────────


def cmd_run(args):
    """Run command(s) as admin."""
    commands = args.commands
    log(f"Admin run: {commands}")
    output, ok = run_admin(commands, wait=args.wait)
    if args.json:
        print(json.dumps({"commands": commands, "output": output, "success": ok}))
    else:
        if output:
            print(output)
        if not ok:
            return 1
    return 0


def cmd_powershell(args):
    """Run PowerShell command as admin."""
    ps_cmd = " ".join(args.ps_command)
    log(f"Admin PowerShell: {ps_cmd}")
    output, ok = run_powershell_admin(ps_cmd, wait=args.wait)
    if args.json:
        print(json.dumps({"command": ps_cmd, "output": output, "success": ok}))
    else:
        if output:
            print(output)
        if not ok:
            return 1
    return 0


def cmd_status(args):
    """Check if the scheduled task exists and is ready."""
    try:
        result = subprocess.run(
            ["schtasks.exe", "/query", "/tn", TASK_NAME, "/fo", "LIST", "/v"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            output = result.stdout
            status = ""
            last_run = ""
            for line in output.split("\n"):
                if "Status:" in line:
                    status = line.split(":", 1)[1].strip()
                elif "Last Run Time:" in line:
                    last_run = line.split(":", 1)[1].strip()

            print(f"Task: {TASK_NAME}")
            print(f"Status: {status}")
            print(f"Last Run: {last_run}")
            print(f"Bat File: {BAT_FILE}")
            print(f"Output File: {OUTPUT_FILE}")

            if args.json:
                print(json.dumps({
                    "task": TASK_NAME, "status": status,
                    "last_run": last_run, "ready": status == "Ready",
                }))
        else:
            print(f"Task '{TASK_NAME}' not found. See the README for setup instructions.")
            return 1
    except Exception as e:
        print(f"Error checking task: {e}")
        return 1
    return 0


def cmd_test(args):
    """Run a quick test to verify admin execution works."""
    print("Testing admin execution...")
    output, ok = run_admin("whoami", wait=3)
    if ok:
        print(f"Admin user: {output}")
        print("Admin execution working.")
    else:
        print(f"Failed: {output}")
        return 1
    return 0


# ── Main ─────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Execute Windows admin commands from WSL2 via a scheduled task",
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("run", help="Run command(s) as Windows admin")
    p.add_argument("commands", nargs="+", help="Command(s) to execute")
    p.add_argument("--wait", type=float, default=3, help="Wait seconds (default: 3)")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("run-multi", help="Run multiple commands as admin")
    p.add_argument("commands", nargs="+", help="Commands to execute sequentially")
    p.add_argument("--wait", type=float, default=3, help="Wait seconds (default: 3)")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("powershell", help="Run PowerShell command as admin")
    p.add_argument("ps_command", nargs="+", help="PowerShell command")
    p.add_argument("--wait", type=float, default=5, help="Wait seconds (default: 5)")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("status", help="Check scheduled task status")
    p.add_argument("--json", action="store_true")

    sub.add_parser("test", help="Test admin execution")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "run": cmd_run,
        "run-multi": cmd_run,
        "powershell": cmd_powershell,
        "status": cmd_status,
        "test": cmd_test,
    }
    return commands[args.command](args) or 0


if __name__ == "__main__":
    sys.exit(main())
