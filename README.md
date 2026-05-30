# wsl-win-admin-bridge

Run **elevated Windows commands from inside WSL2** — without an interactive admin
PowerShell window and without a UAC prompt on every call.

WSL2 can't elevate its way into Windows. If you want to run `usbipd bind`,
`netsh portproxy`, restart a Windows service, or poke the registry from a Linux
shell, you normally have to alt-tab to an Administrator PowerShell. This bridges
that gap: a one-time-registered Windows Scheduled Task runs at highest privilege,
and WSL triggers it on demand.

```bash
python3 win_admin.py run "netsh interface portproxy show all"
python3 win_admin.py run "usbipd bind --busid 6-3 --force"
python3 win_admin.py powershell "Restart-Service sshd"
```

## How it works

```
WSL2                          Windows (admin)
────                          ───────────────
win_admin.py
  │ 1. writes commands ──────► C:\temp\wsl_admin_cmd.bat
  │ 2. schtasks /run  ───────► WSL_ADMIN task fires (runs as highest privilege)
  │                            │ runs the .bat
  │                            ▼
  │ 4. polls for __DONE__ ◄─── C:\temp\wsl_admin_output.txt
  ▼
returns captured output
```

1. The command is written to a `.bat` file on the Windows filesystem (reachable
   from WSL via `/mnt/c`).
2. `schtasks.exe /run /tn WSL_ADMIN` triggers a pre-registered scheduled task that
   runs at **highest privilege**.
3. The task executes the `.bat`, redirecting output to a shared text file and
   appending a `__DONE__` marker.
4. `win_admin.py` polls the output file for `__DONE__`, then returns the captured
   text.

Because the task is registered once with `/rl highest`, **you approve UAC exactly
once — at setup time.** Every subsequent call is silent.

## Setup (one-time)

You need to register the `WSL_ADMIN` scheduled task with admin rights. Pick one:

**Option A — double-click helper (easiest)**

On Windows, double-click `scripts/setup_helper.bat`. Approve the UAC prompt.

**Option B — elevated PowerShell**

```powershell
# Run scripts/setup_task.ps1 from an Administrator PowerShell, or just:
schtasks /create /tn "WSL_ADMIN" /tr "C:\temp\wsl_admin_cmd.bat" /sc once /st 00:00 /rl highest /f
```

Then verify from WSL:

```bash
python3 win_admin.py status
python3 win_admin.py test     # should print your admin username
```

## Usage

```bash
# Run a single admin command
python3 win_admin.py run "whoami"
python3 win_admin.py run "usbipd bind --busid 6-3 --force"

# Run several commands sequentially
python3 win_admin.py run-multi "usbipd detach --busid 6-3" "usbipd unbind --busid 6-3"

# Run a PowerShell command as admin
python3 win_admin.py powershell "Get-Service | Where-Object {$_.Status -eq 'Running'}"
python3 win_admin.py powershell "Set-NetFirewallRule -Name 'MyRule' -Enabled True"

# Check the task / test execution
python3 win_admin.py status
python3 win_admin.py test
```

Add `--wait <seconds>` to allow longer-running commands more time, and `--json`
for machine-readable output.

## Use from your own scripts

```python
import sys
sys.path.insert(0, "/path/to/wsl-win-admin-bridge")
from win_admin import admin_cmd, admin_cmd_no_output, run_powershell_admin

output, ok = admin_cmd("usbipd bind --busid 6-3 --force")
output, ok = admin_cmd(["netsh interface portproxy reset", "netsh interface portproxy show all"])
_, ok      = admin_cmd_no_output("netsh interface portproxy reset")   # don't wait for output
output, ok = run_powershell_admin("Get-NetFirewallRule -Name 'MyRule'")
```

## Configuration

All optional, via environment variables:

| Variable          | Default                         | Purpose                              |
|-------------------|---------------------------------|--------------------------------------|
| `WIN_ADMIN_TASK`  | `WSL_ADMIN`                     | Scheduled task name                  |
| `WIN_ADMIN_TEMP`  | `C:\temp`                       | Windows scratch dir for `.bat`/output|
| `WIN_ADMIN_LOG`   | `logs/win_admin.log` (by script)| Log file path                        |

If you change `WIN_ADMIN_TEMP`, register the task to point at the matching
`wsl_admin_cmd.bat` in that directory.

## Requirements

- Windows 10/11 with WSL2
- Python 3.7+ inside WSL
- `schtasks.exe` reachable from WSL (it is, by default, via `/mnt/c/Windows/System32`)
- For `usbipd` examples: [usbipd-win](https://github.com/dorssel/usbipd-win)

## Security notes

This is a deliberate privilege-escalation path: any process that can write to the
trigger `.bat` (or run `win_admin.py`) can execute commands as a high-privilege
Windows user with no further prompt. That's the whole point — but it means:

- Only set this up on a machine you control.
- Keep the scratch directory (`C:\temp` by default) writable only by your user.
- Don't expose `win_admin.py` to untrusted callers.

## License

MIT — see [LICENSE](LICENSE).
