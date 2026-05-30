# AGENTS.md

Machine-readable guide for AI coding agents working with this repository.

## What this is

`wsl-win-admin-bridge` lets a process running inside **WSL2 (Linux)** execute
**elevated/administrator Windows commands** without an interactive UAC prompt on
every call. It does this through a pre-registered Windows Scheduled Task
(`WSL_ADMIN`) that runs at highest privilege.

Use this when an agent operating in WSL needs to run something that requires
Windows admin rights — `usbipd` (USB passthrough), `netsh` (port proxy /
firewall), Windows service control, registry edits, `schtasks`, etc.

## Entry point

Single script, no dependencies beyond the Python standard library:

```
win_admin.py        # CLI + importable API
scripts/setup_task.ps1   # one-time task registration (run as admin on Windows)
scripts/setup_helper.bat # double-click wrapper for setup_task.ps1
```

## How to invoke (CLI)

```bash
python3 win_admin.py run "<windows command>"          # run one admin command
python3 win_admin.py run-multi "<cmd1>" "<cmd2>"      # run several in sequence
python3 win_admin.py powershell "<ps command>"        # run a PowerShell command as admin
python3 win_admin.py status                            # check the WSL_ADMIN task
python3 win_admin.py test                              # verify elevation works (prints admin whoami)
```

Flags: `--wait <seconds>` (allow longer-running commands), `--json` (machine-readable output).

## How to invoke (Python API)

```python
import sys
sys.path.insert(0, "/path/to/wsl-win-admin-bridge")
from win_admin import admin_cmd, admin_cmd_no_output, run_powershell_admin

output, ok = admin_cmd("usbipd bind --busid 6-3 --force")   # (str, bool)
output, ok = admin_cmd(["cmd1", "cmd2"])                     # list runs sequentially
_, ok      = admin_cmd_no_output("netsh interface portproxy reset")
output, ok = run_powershell_admin("Get-NetFirewallRule -Name 'MyRule'")
```

Return contract: every call returns `(output_text: str, success: bool)`.

## Preconditions

- Running inside WSL2 with `/mnt/c` (Windows C: drive) accessible.
- `schtasks.exe` reachable on PATH (default on WSL via `/mnt/c/Windows/System32`).
- The `WSL_ADMIN` scheduled task must be registered once (see README "Setup").
  If `win_admin.py status` reports the task is missing, registration cannot be
  done from WSL — it requires a one-time admin action on Windows. Surface this to
  the user rather than attempting to self-elevate.

## Configuration (environment variables)

| Variable         | Default              | Purpose                                |
|------------------|----------------------|----------------------------------------|
| `WIN_ADMIN_TASK` | `WSL_ADMIN`          | Scheduled task name                    |
| `WIN_ADMIN_TEMP` | `C:\temp`            | Windows scratch dir for `.bat`/output  |
| `WIN_ADMIN_LOG`  | `logs/win_admin.log` | Log file path                          |

## Safety notes for agents

- This is a deliberate privilege-escalation path. Treat command strings as you
  would `sudo` on Linux. Do not pass untrusted input to `run`/`powershell`.
- Destructive Windows operations (service stops, firewall changes, registry
  edits) take effect immediately and system-wide. Confirm with the user before
  running anything that changes system state.
- There is no sandbox; commands run as a high-privilege Windows user.

## Verifying a change

```bash
python3 -m py_compile win_admin.py     # syntax check (no Windows needed)
python3 win_admin.py --help            # CLI smoke test
python3 win_admin.py test              # full round-trip (requires registered task + Windows)
```
