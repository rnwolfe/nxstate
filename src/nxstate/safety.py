"""The read-only boundary. nxstate has no mutating commands; instead the show/debug
passthrough validates that input is a read command and refuses anything else (WRITE_REFUSED).
"No conf t" is the product boundary, not a toggle — there is deliberately no override flag."""

from __future__ import annotations

from .errors import write_refused

# Anything that could change state or disrupt the box. Checked as the leading token.
_FORBIDDEN_LEADERS = (
    "conf", "configure", "write", "wr", "copy", "reload", "boot", "install",
    "clear", "no", "set", "delete", "erase", "format", "reset", "shutdown",
    "switchto", "attach", "vsh", "run", "python", "bash", "guestshell", "feature",
)


def assert_read_command(command: str) -> None:
    """Raise WRITE_REFUSED unless `command` is a safe read (a `show ...`)."""
    cmd = command.strip()
    if "\n" in cmd or "\r" in cmd:
        raise write_refused(command, "multiple/newline-separated commands are not allowed")
    lead = cmd.split(maxsplit=1)[0].lower() if cmd else ""
    if lead in _FORBIDDEN_LEADERS:
        raise write_refused(command, f"'{lead}' is not a read command")
    if lead != "show":
        raise write_refused(command, "only 'show ...' read commands are permitted")
