"""Placeholder Nexus client. cli-implement replaces this with the real transport:
scrapli (core `cisco_nxos`) over SSH with `| json`/`| json-native`, plus an NX-API `cli_show`
accelerator (`--transport auto`), and Genie/ntc-templates parsing. See spec.md + the
blueprint. It is a stub here so the scaffold compiles, runs, and is contract-testable offline.

Result shape (stable contract for every show):
    {"command", "parsed": <dict|None>, "raw": <str|None>, "parser": "genie|ntc|json|none"}
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NexusClient:
    host: str
    username: str | None = None
    password: str | None = None
    port: int | None = None
    transport: str = "auto"  # ssh | nxapi | auto
    timeout: int = 30
    insecure: bool = False

    def run_show(self, command: str, parse: bool = True) -> dict:
        """Run a read-only `show` command and return parsed + raw output.

        TODO(cli-implement): connect via scrapli (cisco_nxos), prefer `<cmd> | json-native`
        (9.3(1)+) → `| json` → text; try NX-API cli_show when transport allows; parse with
        Genie (`genie_parse_output`) then ntc-templates; map failures to UNREACHABLE/AUTH/
        RATE/PARSE_UNAVAILABLE. This stub performs NO network I/O.
        """
        return {
            "command": command,
            "parsed": None,
            "raw": f"<stub output for {command!r} on {self.host}; run cli-implement to wire scrapli+Genie>",
            "parser": "none",
        }

    def reachable(self) -> tuple[bool, str]:
        """TODO(cli-implement): probe SSH/NX-API. Stub reports not-yet-implemented."""
        return False, "client not implemented (run cli-implement)"
