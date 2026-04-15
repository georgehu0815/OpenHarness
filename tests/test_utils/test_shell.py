"""Tests for shell resolution helpers."""

from __future__ import annotations

from openharness.utils.shell import resolve_shell_command


def test_resolve_shell_command_prefers_bash_on_linux(monkeypatch):
    monkeypatch.setattr(
        "openharness.utils.shell.shutil.which",
        lambda name: "/usr/bin/bash" if name == "bash" else None,
    )

    command = resolve_shell_command("echo hi", platform_name="linux")

    assert command == ["/usr/bin/bash", "-lc", "echo hi"]


def test_resolve_shell_command_wraps_with_script_pty_linux(monkeypatch):
    def fake_which(name: str) -> str | None:
        return {"bash": "/usr/bin/bash", "script": "/usr/bin/script"}.get(name)

    monkeypatch.setattr("openharness.utils.shell.shutil.which", fake_which)
    monkeypatch.setattr("openharness.utils.shell.os.isatty", lambda fd: True)

    command = resolve_shell_command("echo hi", platform_name="linux", prefer_pty=True)

    # GNU script: -f flushes output, -c specifies the command, logfile last
    assert command == ["/usr/bin/script", "-qefc", "echo hi", "/dev/null"]


def test_resolve_shell_command_wraps_with_script_pty_macos(monkeypatch):
    def fake_which(name: str) -> str | None:
        return {"bash": "/usr/bin/bash", "script": "/usr/bin/script"}.get(name)

    monkeypatch.setattr("openharness.utils.shell.shutil.which", fake_which)
    monkeypatch.setattr("openharness.utils.shell.os.isatty", lambda fd: True)

    command = resolve_shell_command("echo hi", platform_name="macos", prefer_pty=True)

    # BSD script (macOS): no -c flag; command passed as positional args after logfile
    assert command == ["/usr/bin/script", "-qe", "/dev/null", "/usr/bin/bash", "-lc", "echo hi"]


def test_resolve_shell_command_no_pty_wrap_outside_tty(monkeypatch):
    def fake_which(name: str) -> str | None:
        return {"bash": "/usr/bin/bash", "script": "/usr/bin/script"}.get(name)

    monkeypatch.setattr("openharness.utils.shell.shutil.which", fake_which)
    monkeypatch.setattr("openharness.utils.shell.os.isatty", lambda fd: False)

    command = resolve_shell_command("echo hi", platform_name="linux", prefer_pty=True)

    # Falls back to plain bash when not in a real TTY (e.g. VS Code socket)
    assert command == ["/usr/bin/bash", "-lc", "echo hi"]


def test_resolve_shell_command_uses_powershell_on_windows(monkeypatch):
    def fake_which(name: str) -> str | None:
        mapping = {
            "pwsh": "C:/Program Files/PowerShell/7/pwsh.exe",
        }
        return mapping.get(name)

    monkeypatch.setattr("openharness.utils.shell.shutil.which", fake_which)

    command = resolve_shell_command("Write-Output hi", platform_name="windows")

    assert command == [
        "C:/Program Files/PowerShell/7/pwsh.exe",
        "-NoLogo",
        "-NoProfile",
        "-Command",
        "Write-Output hi",
    ]
