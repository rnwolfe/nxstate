"""Click grammar, runtime context, and exit-code mapping for nxstate.
main() does nothing but sys.exit(run(...)) so every path is testable in-process.

Global flags are attached to every command (decorator + leaf-first context merge) so an agent
can place them in any position. nxstate is READ-ONLY by design: no --allow-mutations; the
show/debug passthrough refuses non-read input (WRITE_REFUSED)."""

from __future__ import annotations

import difflib
import json
import os
import sys
from dataclasses import dataclass

import click

from . import __version__
from .client import NexusClient
from .errors import (AppError, ExitCode, auth_required, debug_blocked, exit_table,
                     host_required, input_required, not_found)
from .output import Writer
from .safety import assert_read_command
from .skill import content as skill_content
from .wrap import fence

_active: "Runtime | None" = None

_GLOBAL_KEYS = ["fmt", "as_json", "no_color", "no_input", "limit", "select", "concise",
                "detailed", "host", "port", "username", "transport", "timeout", "insecure",
                "password_stdin", "allow_debug", "allow_tech"]


def global_options(f):
    """Attach the universal contract flags + Nexus connection flags to a command."""
    opts = [
        # output (contract §1, §6)
        click.option("--format", "fmt", type=click.Choice(["json", "plain", "tsv"]),
                     default=None, help="Output format: json, plain, or tsv."),
        click.option("--json", "as_json", is_flag=True, default=None, help="Shorthand for --format=json."),
        click.option("--no-color", is_flag=True, default=None, help="Disable colored output."),
        click.option("--no-input", is_flag=True, default=None, help="Never prompt; fail with exit 13."),
        click.option("--limit", type=int, default=None, help="Max rows for list operations (default 50)."),
        click.option("--select", default=None, help="Comma-separated dot-path field projection."),
        click.option("--concise", is_flag=True, default=None, help="Terser output (default)."),
        click.option("--detailed", is_flag=True, default=None, help="Richer output."),
        # connection
        click.option("--host", default=None, help="Target switch hostname/IP."),
        click.option("--port", type=int, default=None, help="Transport port (default per transport)."),
        click.option("--username", "-u", default=None, help="Login username (read-only role)."),
        click.option("--transport", type=click.Choice(["ssh", "nxapi", "auto"]), default=None,
                     help="Access method (default: auto — probe NX-API, fall back to SSH)."),
        click.option("--timeout", type=int, default=None, help="Per-command timeout seconds (default 30)."),
        click.option("--insecure", is_flag=True, default=None, help="Skip TLS verify for NX-API self-signed certs."),
        click.option("--password-stdin", is_flag=True, default=None, help="Read the password from stdin."),
        # safety gates for heavy / control-plane reads
        click.option("--allow-debug", is_flag=True, default=None, help="Permit control-plane-impacting debug reads."),
        click.option("--allow-tech", is_flag=True, default=None, help="Permit slow show tech-support."),
    ]
    for o in reversed(opts):
        f = o(f)
    return f


@dataclass
class Runtime:
    fmt: str
    no_input: bool
    out: Writer
    host: str | None
    port: int | None
    username: str | None
    transport: str
    timeout: int
    insecure: bool
    password_stdin: bool
    allow_debug: bool
    allow_tech: bool

    def require_host(self) -> str:
        if not self.host:
            raise host_required()
        return self.host

    def _password(self) -> str | None:
        if self.password_stdin:
            return sys.stdin.readline().rstrip("\n")
        return os.environ.get("NXSTATE_PASSWORD")  # never via argv (contract §7)

    def client(self) -> NexusClient:
        self.require_host()
        return NexusClient(host=self.host, username=self.username, password=self._password(),
                           port=self.port, transport=self.transport, timeout=self.timeout,
                           insecure=self.insecure)

    def emit_result(self, command: str, parsed, raw, parser: str) -> None:
        """Emit a show result: parsed JSON when available, else fenced untrusted raw text."""
        if self.fmt == "json":
            self.out.emit_json({"command": command, "parser": parser, "parsed": parsed,
                                "raw": raw, "untrusted": raw is not None})
        elif parsed is not None:
            self.out.emit(parsed)
        elif raw is not None:
            print(fence(raw), file=self.out.stdout)

    def show(self, command: str) -> None:
        r = self.client().run_show(command)
        self.emit_result(r["command"], r.get("parsed"), r.get("raw"), r.get("parser", "none"))


def _resolve(ctx) -> dict:
    vals = {k: None for k in _GLOBAL_KEYS}
    c = ctx
    while c is not None:
        for k in _GLOBAL_KEYS:
            if vals[k] is None and c.params.get(k) is not None:
                vals[k] = c.params[k]
        c = c.parent
    return vals


def make_runtime(ctx) -> Runtime:
    global _active
    v = _resolve(ctx)
    fmt = "json" if v["as_json"] else (v["fmt"] or "plain")
    color = (not v["no_color"]) and sys.stdout.isatty() and fmt == "plain"
    sel = [s for s in (v["select"] or "").split(",") if s.strip()]
    limit = v["limit"] if v["limit"] is not None else 50
    out = Writer(fmt=fmt, color=color, limit=limit, select=sel)
    _active = Runtime(
        fmt=fmt, no_input=bool(v["no_input"]), out=out, host=v["host"], port=v["port"],
        username=v["username"], transport=v["transport"] or "auto",
        timeout=v["timeout"] if v["timeout"] is not None else 30, insecure=bool(v["insecure"]),
        password_stdin=bool(v["password_stdin"]), allow_debug=bool(v["allow_debug"]),
        allow_tech=bool(v["allow_tech"]),
    )
    return _active


class DYMGroup(click.Group):
    def resolve_command(self, ctx, args):
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError as exc:
            name = args[0] if args else ""
            matches = difflib.get_close_matches(name, self.list_commands(ctx), n=1)
            if matches:
                exc.message = f"{exc.message}\n  did you mean '{matches[0]}'?"
            raise


@click.group(cls=DYMGroup, context_settings={"help_option_names": ["-h", "--help"]})
@global_options
@click.pass_context
def cli(ctx, **_):
    """Read-only Cisco Nexus (NX-OS) state-gathering CLI. No configuration, ever."""


# --- curated state commands (each maps to a `show`, Genie-parsed by cli-implement) ----------

@cli.group()
def system():
    """Device facts: version, environment, inventory."""


@system.command("version")
@global_options
@click.pass_context
def system_version(ctx, **_):
    """show version"""
    make_runtime(ctx).show("show version")


@system.command("environment")
@global_options
@click.pass_context
def system_environment(ctx, **_):
    """show environment (power/fan/temperature)"""
    make_runtime(ctx).show("show environment")


@system.command("inventory")
@global_options
@click.pass_context
def system_inventory(ctx, **_):
    """show inventory"""
    make_runtime(ctx).show("show inventory")


@cli.group()
def interface():
    """Interface state and counters."""


@interface.command("list")
@global_options
@click.pass_context
def interface_list(ctx, **_):
    """show interface brief"""
    make_runtime(ctx).show("show interface brief")


@interface.command("show")
@click.argument("name")
@global_options
@click.pass_context
def interface_show(ctx, name, **_):
    """show interface <name>"""
    make_runtime(ctx).show(f"show interface {name}")


@interface.command("counters")
@click.argument("name", required=False)
@global_options
@click.pass_context
def interface_counters(ctx, name, **_):
    """show interface [<name>] counters"""
    cmd = f"show interface {name} counters" if name else "show interface counters"
    make_runtime(ctx).show(cmd)


@cli.group()
def vlan():
    """VLAN state."""


@vlan.command("list")
@global_options
@click.pass_context
def vlan_list(ctx, **_):
    """show vlan"""
    make_runtime(ctx).show("show vlan")


@cli.group()
def route():
    """Routing table state."""


@route.command("list")
@click.option("--vrf", default=None, help="Restrict to a VRF.")
@global_options
@click.pass_context
def route_list(ctx, vrf, **_):
    """show ip route [vrf <vrf>]"""
    make_runtime(ctx).show(f"show ip route vrf {vrf}" if vrf else "show ip route")


@cli.group()
def bgp():
    """BGP state."""


@bgp.command("summary")
@click.option("--vrf", default=None, help="Restrict to a VRF.")
@global_options
@click.pass_context
def bgp_summary(ctx, vrf, **_):
    """show ip bgp summary [vrf <vrf>]"""
    make_runtime(ctx).show(f"show ip bgp summary vrf {vrf}" if vrf else "show ip bgp summary")


@cli.group()
def neighbor():
    """Discovered neighbors (CDP/LLDP)."""


@neighbor.command("list")
@click.option("--protocol", type=click.Choice(["cdp", "lldp"]), default="lldp", help="Discovery protocol.")
@global_options
@click.pass_context
def neighbor_list(ctx, protocol, **_):
    """show {cdp|lldp} neighbors"""
    make_runtime(ctx).show(f"show {protocol} neighbors")


@cli.group()
def mac():
    """MAC address table."""


@mac.command("list")
@global_options
@click.pass_context
def mac_list(ctx, **_):
    """show mac address-table"""
    make_runtime(ctx).show("show mac address-table")


@cli.group()
def arp():
    """ARP table."""


@arp.command("list")
@global_options
@click.pass_context
def arp_list(ctx, **_):
    """show ip arp"""
    make_runtime(ctx).show("show ip arp")


@cli.command("logging")
@global_options
@click.pass_context
def logging_show(ctx, **_):
    """show logging logfile (text, fenced untrusted)"""
    make_runtime(ctx).show("show logging logfile")


# --- generic read passthrough + gated heavy reads -------------------------------------------

@cli.command("show")
@click.argument("command")
@global_options
@click.pass_context
def show_passthrough(ctx, command, **_):
    """Run an arbitrary read command: nxstate show "show ip ospf neighbors". Non-read input is refused."""
    assert_read_command(command)  # validate the RAW input — never auto-prepend (that would bypass the gate)
    make_runtime(ctx).show(command)


@cli.command("debug")
@click.argument("command")
@global_options
@click.pass_context
def debug_cmd(ctx, command, **_):
    """Run a debug read (control-plane-impacting; gated by --allow-debug)."""
    rt = make_runtime(ctx)
    if not rt.allow_debug:
        raise debug_blocked(command)
    rt.out.info("warning: debug commands load the supervisor CPU; keep captures short")
    r = rt.client().run_show(f"debug {command}")
    rt.emit_result(r["command"], r.get("parsed"), r.get("raw"), r.get("parser", "none"))


@cli.command("tech-support")
@global_options
@click.pass_context
def tech_support(ctx, **_):
    """show tech-support (huge/slow; gated by --allow-tech)."""
    rt = make_runtime(ctx)
    if not rt.allow_tech:
        raise AppError(ExitCode.PERM, "TECH_BLOCKED",
                       "show tech-support is large and slow and is gated",
                       "re-run with --allow-tech (expect a long, text-only capture)")
    rt.show("show tech-support")


# --- auth / doctor / schema / agent / version -----------------------------------------------

@cli.group()
def auth():
    """Manage authentication to the switch."""


@auth.command("status")
@global_options
@click.pass_context
def auth_status(ctx, **_):
    """Report whether credentials are present for the target."""
    rt = make_runtime(ctx)
    have_pw = bool(rt.password_stdin or os.environ.get("NXSTATE_PASSWORD"))
    rt.out.emit({"host": rt.host, "username": rt.username, "transport": rt.transport,
                 "credential_present": have_pw,
                 "note": "credentials are read from NXSTATE_PASSWORD / --password-stdin / keyring (never argv)"})


@auth.command("login")
@global_options
@click.pass_context
def auth_login(ctx, **_):
    """Store credentials for the target in the OS keyring (wired by cli-implement)."""
    rt = make_runtime(ctx)
    rt.out.emit({"ok": False, "note": "TODO(cli-implement): keyring credential storage"})


@cli.command()
@global_options
@click.pass_context
def doctor(ctx, **_):
    """Diagnose reachability, transport, and credentials for the target."""
    rt = make_runtime(ctx)
    host_ok = bool(rt.host)
    cred_ok = bool(rt.password_stdin or os.environ.get("NXSTATE_PASSWORD") or rt.username)
    checks = [
        {"name": "host", "ok": host_ok, "detail": rt.host or "no --host provided"},
        {"name": "credentials", "ok": cred_ok,
         "detail": "present" if cred_ok else "set --username + NXSTATE_PASSWORD"},
        {"name": "transport-probe", "ok": False,
         "detail": "TODO(cli-implement): probe NX-API/SSH reachability"},
    ]
    rt.out.emit({"ok": all(c["ok"] for c in checks), "checks": checks})


@cli.command()
@global_options
@click.pass_context
def schema(ctx, **_):
    """Print the machine-readable command schema (JSON)."""
    rt = make_runtime(ctx)
    info = cli.to_info_dict(click.Context(cli, info_name="nxstate"))
    rt.out.emit_json({
        "tool": "nxstate",
        "version": __version__,
        "read_only": True,
        "commands": info,
        "exit_codes": exit_table(),
        "safety": {"read_only": True, "mutations": "none (WRITE_REFUSED on non-read input)",
                   "allow_debug": rt.allow_debug, "allow_tech": rt.allow_tech,
                   "no_input": rt.no_input},
    })


@cli.command()
@global_options
@click.pass_context
def agent(ctx, **_):
    """Print the bundled agent SKILL.md."""
    make_runtime(ctx).out.stdout.write(skill_content())


@cli.command()
@global_options
@click.pass_context
def version(ctx, **_):
    """Print the version."""
    make_runtime(ctx).out.emit({"version": __version__})


# --- entry / exit mapping -------------------------------------------------------------------

def run(argv: list[str] | None = None) -> int:
    try:
        cli.main(args=argv, standalone_mode=False)
        return ExitCode.OK
    except (click.exceptions.Exit, SystemExit) as e:
        code = getattr(e, "exit_code", getattr(e, "code", 0))
        return int(code or 0)
    except click.UsageError as e:
        click.echo(f"error: {e.format_message()}", err=True)
        return ExitCode.USAGE
    except click.Abort:
        return ExitCode.CANCELLED
    except AppError as e:
        _emit_error(e)
        return e.exit


def _emit_error(e: AppError) -> None:
    if _active is not None and _active.fmt == "json":
        print(json.dumps({"error": e.message, "code": e.code, "remediation": e.remediation},
                         ensure_ascii=False), file=sys.stderr)
    else:
        print(f"error: {e.message}", file=sys.stderr)
        if e.code:
            print(f"  code: {e.code}", file=sys.stderr)
        if e.remediation:
            print(f"  fix:  {e.remediation}", file=sys.stderr)


def main() -> None:
    sys.exit(run())
