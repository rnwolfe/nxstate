"""Click grammar, runtime context, and exit-code mapping for nxstate.
main() does nothing but sys.exit(run(...)) so every path is testable in-process.

Global flags are attached to every command (decorator + leaf-first context merge) so an agent
can place them in any position. nxstate is READ-ONLY by design: no --allow-mutations; the
show/debug passthrough refuses non-read input (WRITE_REFUSED)."""

from __future__ import annotations

import concurrent.futures
import difflib
import json
import os
import sys
from dataclasses import dataclass

import click

from . import SPEC, __version__
from .client import NexusClient, first_rows, normalize_nxos
from .errors import AppError, ExitCode, debug_blocked, exit_table, host_required, input_required
from .inventory import Target, load_inventory
from .inventory import resolve as resolve_targets
from .output import Writer, shape
from .safety import assert_read_command
from .skill import content as skill_content
from .wrap import fence

_active: Runtime | None = None

_GLOBAL_KEYS = [
    "fmt",
    "as_json",
    "no_color",
    "no_input",
    "limit",
    "select",
    "concise",
    "detailed",
    "host",
    "port",
    "username",
    "transport",
    "timeout",
    "insecure",
    "password_stdin",
    "allow_debug",
    "allow_tech",
    "devices",
    "groups",
    "all_targets",
    "inventory",
    "workers",
]


def global_options(f):
    """Attach the universal contract flags + Nexus connection flags to a command."""
    opts = [
        # output (contract §1, §6)
        click.option(
            "--format",
            "fmt",
            type=click.Choice(["json", "plain", "tsv"]),
            default=None,
            help="Output format: json, plain, or tsv.",
        ),
        click.option(
            "--json", "as_json", is_flag=True, default=None, help="Shorthand for --format=json."
        ),
        click.option("--no-color", is_flag=True, default=None, help="Disable colored output."),
        click.option(
            "--no-input", is_flag=True, default=None, help="Never prompt; fail with exit 13."
        ),
        click.option(
            "--limit", type=int, default=None, help="Max rows for list operations (default 50)."
        ),
        click.option("--select", default=None, help="Comma-separated dot-path field projection."),
        click.option("--concise", is_flag=True, default=None, help="Terser output (default)."),
        click.option("--detailed", is_flag=True, default=None, help="Richer output."),
        # connection
        click.option("--host", default=None, help="Target switch hostname/IP."),
        click.option(
            "--port", type=int, default=None, help="Transport port (default per transport)."
        ),
        click.option("--username", "-u", default=None, help="Login username (read-only role)."),
        click.option(
            "--transport",
            type=click.Choice(["ssh", "nxapi", "auto"]),
            default=None,
            help="Access method (default: auto — probe NX-API, fall back to SSH).",
        ),
        click.option(
            "--timeout", type=int, default=None, help="Per-command timeout seconds (default 30)."
        ),
        click.option(
            "--insecure",
            is_flag=True,
            default=None,
            help="Skip TLS verify for NX-API self-signed certs.",
        ),
        click.option(
            "--password-stdin", is_flag=True, default=None, help="Read the password from stdin."
        ),
        # safety gates for heavy / control-plane reads
        click.option(
            "--allow-debug",
            is_flag=True,
            default=None,
            help="Permit control-plane-impacting debug reads.",
        ),
        click.option(
            "--allow-tech", is_flag=True, default=None, help="Permit slow show tech-support."
        ),
        # inventory / fan-out
        click.option(
            "--device",
            "devices",
            multiple=True,
            help="Inventory host(s) by name or glob (repeatable). Fan-out if >1 matches.",
        ),
        click.option("--group", "groups", multiple=True, help="Inventory group(s) (repeatable)."),
        click.option(
            "--all", "all_targets", is_flag=True, default=None, help="Target every inventory host."
        ),
        click.option(
            "--inventory",
            default=None,
            help="Inventory file path (default: ~/.config/nxstate/inventory.yaml).",
        ),
        click.option(
            "--workers",
            type=int,
            default=None,
            help="Max concurrent devices for fan-out (default 10).",
        ),
    ]
    for o in reversed(opts):
        f = o(f)
    return f


@dataclass
class Runtime:
    fmt: str
    no_input: bool
    out: Writer
    # connection overrides (None = unset; resolved per target via flag → inventory → env → default)
    host: str | None
    port: int | None
    username: str | None
    transport: str | None
    timeout: int | None
    insecure: bool | None
    password_stdin: bool
    allow_debug: bool
    allow_tech: bool
    # inventory / fan-out
    devices: tuple
    groups: tuple
    all_targets: bool
    inventory: str | None
    workers: int

    # ---- target resolution -------------------------------------------------

    @property
    def use_inventory(self) -> bool:
        return bool(self.devices or self.groups or self.all_targets)

    def _finalize(self, name: str, base: dict) -> Target:
        def pick(key, flagval, envvar=None, default=None):
            if flagval is not None:
                return flagval
            if base.get(key) is not None:
                return base[key]
            if envvar and os.environ.get(envvar):
                return os.environ[envvar]
            return default

        return Target(
            name,
            {
                "host": pick("host", self.host, "NXSTATE_HOST"),
                "username": pick("username", self.username, "NXSTATE_USERNAME"),
                "transport": pick("transport", self.transport, "NXSTATE_TRANSPORT", "auto"),
                "port": pick("port", self.port, "NXSTATE_PORT"),
                "insecure": self.insecure
                if self.insecure is not None
                else bool(base.get("insecure")),
                "timeout": self.timeout
                if self.timeout is not None
                else int(base.get("timeout") or 30),
            },
        )

    def targets(self) -> list[Target]:
        if self.use_inventory:
            inv = load_inventory(self.inventory)
            return [
                self._finalize(t.name, t.settings)
                for t in resolve_targets(inv, self.devices, self.groups, self.all_targets)
            ]
        t = self._finalize(self.host or os.environ.get("NXSTATE_HOST") or "", {})
        if not t.settings["host"]:
            raise host_required()
        return [t]

    def client_for(self, t: Target) -> NexusClient:
        s = t.settings
        pw = _password_for(s["host"], s["username"], self.password_stdin)
        return NexusClient(
            host=s["host"],
            username=s["username"],
            password=pw,
            port=s["port"],
            transport=s["transport"],
            timeout=s["timeout"],
            insecure=s["insecure"],
        )

    # ---- emit --------------------------------------------------------------

    def _payload(self, result: dict, rows: bool):
        """Return (value, is_raw_text) for a run_show result, normalized and projected."""
        parsed, raw = result.get("parsed"), result.get("raw")
        if parsed is not None:
            data = first_rows(parsed) if rows else normalize_nxos(parsed)
            return data, False
        if raw is not None:
            return {"raw": raw, "untrusted": True}, True
        return {"result": None, "parser": result.get("parser", "none")}, False

    def emit_result(self, command: str, parsed, raw, parser: str, rows: bool = False) -> None:
        """Single-device emit through the Writer (--select/--limit/--format apply); raw free
        text is fenced as untrusted (contract §8)."""
        if parsed is not None:
            self.out.emit(first_rows(parsed) if rows else normalize_nxos(parsed))
        elif raw is not None:
            if self.fmt == "json":
                self.out.emit_json(
                    {"command": command, "parser": parser, "raw": raw, "untrusted": True}
                )
            else:
                print(fence(raw), file=self.out.stdout)
        else:
            self.out.emit({"command": command, "parser": parser, "result": None})

    def show(self, command: str, rows: bool = False) -> None:
        tgts = self.targets()
        if len(tgts) == 1:
            r = self.client_for(tgts[0]).run_show(command)
            self.emit_result(
                r["command"], r.get("parsed"), r.get("raw"), r.get("parser", "none"), rows
            )
            return
        self.fanout(tgts, command, rows)

    def fanout(self, tgts: list[Target], command: str, rows: bool) -> None:
        """Run `command` across multiple devices concurrently, streaming one NDJSON object per
        device as it completes, with per-device error isolation. Exits PARTIAL if any failed."""

        def work(t: Target) -> dict:
            try:
                r = self.client_for(t).run_show(command)
                value, is_raw = self._payload(r, rows)
                if not is_raw:
                    value = shape(value, self.out.select, self.out.limit)
                return {"device": t.name, "host": t.settings["host"], "ok": True, "data": value}
            except AppError as e:
                return {
                    "device": t.name,
                    "host": t.settings["host"],
                    "ok": False,
                    "error": {"code": e.code, "message": e.message, "remediation": e.remediation},
                }
            except Exception as e:  # never let one device kill the run
                return {
                    "device": t.name,
                    "host": t.settings["host"],
                    "ok": False,
                    "error": {"code": "INTERNAL", "message": str(e)},
                }

        failures = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as ex:
            for fut in concurrent.futures.as_completed([ex.submit(work, t) for t in tgts]):
                res = fut.result()
                failures += 0 if res["ok"] else 1
                print(json.dumps(res, ensure_ascii=False), file=self.out.stdout, flush=True)
        if failures:
            raise click.exceptions.Exit(ExitCode.PARTIAL)


def _password_for(host: str | None, username: str | None, password_stdin: bool) -> str | None:
    # Resolution order (never via argv — contract §7): --password-stdin → env → OS keyring.
    if password_stdin:
        return sys.stdin.readline().rstrip("\n")
    if pw := os.environ.get("NXSTATE_PASSWORD"):
        return pw
    if host and username:
        try:
            import keyring

            return keyring.get_password("nxstate", f"{username}@{host}")
        except Exception:
            return None
    return None


def _resolve(ctx) -> dict:
    vals = {k: None for k in _GLOBAL_KEYS}
    c = ctx
    while c is not None:
        for k in _GLOBAL_KEYS:
            v = c.params.get(k)
            if vals[k] is None and v is not None and v != () and v != "":
                vals[k] = v
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
        fmt=fmt,
        no_input=bool(v["no_input"]),
        out=out,
        host=v["host"],
        port=v["port"],
        username=v["username"],
        transport=v["transport"],
        timeout=v["timeout"],
        insecure=v["insecure"],
        password_stdin=bool(v["password_stdin"]),
        allow_debug=bool(v["allow_debug"]),
        allow_tech=bool(v["allow_tech"]),
        devices=v["devices"] or (),
        groups=v["groups"] or (),
        all_targets=bool(v["all_targets"]),
        inventory=v["inventory"],
        workers=v["workers"] or 10,
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
    make_runtime(ctx).show("show interface brief", rows=True)


@interface.command("show")
@click.argument("name")
@global_options
@click.pass_context
def interface_show(ctx, name, **_):
    """show interface <name>"""
    make_runtime(ctx).show(f"show interface {name}", rows=True)


@interface.command("counters")
@click.argument("name", required=False)
@global_options
@click.pass_context
def interface_counters(ctx, name, **_):
    """show interface [<name>] counters"""
    cmd = f"show interface {name} counters" if name else "show interface counters"
    make_runtime(ctx).show(cmd, rows=True)


@cli.group()
def vlan():
    """VLAN state."""


@vlan.command("list")
@global_options
@click.pass_context
def vlan_list(ctx, **_):
    """show vlan"""
    make_runtime(ctx).show("show vlan", rows=True)


@cli.group()
def route():
    """Routing table state."""


@route.command("list")
@click.option("--vrf", default=None, help="Restrict to a VRF.")
@global_options
@click.pass_context
def route_list(ctx, vrf, **_):
    """show ip route [vrf <vrf>]"""
    make_runtime(ctx).show(f"show ip route vrf {vrf}" if vrf else "show ip route", rows=True)


@cli.group()
def bgp():
    """BGP state."""


@bgp.command("summary")
@click.option("--vrf", default=None, help="Restrict to a VRF.")
@global_options
@click.pass_context
def bgp_summary(ctx, vrf, **_):
    """show ip bgp summary [vrf <vrf>]"""
    make_runtime(ctx).show(
        f"show ip bgp summary vrf {vrf}" if vrf else "show ip bgp summary", rows=True
    )


@cli.group()
def neighbor():
    """Discovered neighbors (CDP/LLDP)."""


@neighbor.command("list")
@click.option(
    "--protocol", type=click.Choice(["cdp", "lldp"]), default="lldp", help="Discovery protocol."
)
@global_options
@click.pass_context
def neighbor_list(ctx, protocol, **_):
    """show {cdp|lldp} neighbors"""
    make_runtime(ctx).show(f"show {protocol} neighbors", rows=True)


@cli.group()
def mac():
    """MAC address table."""


@mac.command("list")
@global_options
@click.pass_context
def mac_list(ctx, **_):
    """show mac address-table"""
    make_runtime(ctx).show("show mac address-table", rows=True)


@cli.group()
def arp():
    """ARP table."""


@arp.command("list")
@global_options
@click.pass_context
def arp_list(ctx, **_):
    """show ip arp"""
    make_runtime(ctx).show("show ip arp", rows=True)


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
    assert_read_command(
        command
    )  # validate the RAW input — never auto-prepend (that would bypass the gate)
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
    rt.show(f"debug {command}")


@cli.command("tech-support")
@global_options
@click.pass_context
def tech_support(ctx, **_):
    """show tech-support (huge/slow; gated by --allow-tech)."""
    rt = make_runtime(ctx)
    if not rt.allow_tech:
        raise AppError(
            ExitCode.PERM,
            "TECH_BLOCKED",
            "show tech-support is large and slow and is gated",
            "re-run with --allow-tech (expect a long, text-only capture)",
        )
    rt.show("show tech-support")


# --- auth / doctor / schema / agent / version -----------------------------------------------


@cli.group()
def auth():
    """Manage authentication to the switch."""


@auth.command("status")
@global_options
@click.pass_context
def auth_status(ctx, **_):
    """Report whether credentials are present for the target(s)."""
    rt = make_runtime(ctx)

    def info_for(t: Target) -> dict:
        s = t.settings
        have = rt.password_stdin or bool(_password_for(s["host"], s["username"], False))
        return {
            "device": t.name,
            "host": s["host"],
            "username": s["username"],
            "transport": s["transport"],
            "credential_present": have,
        }

    tgts = rt.targets()
    if len(tgts) == 1:
        d = info_for(tgts[0])
        d.pop("device")
        d["note"] = (
            "credentials read from NXSTATE_PASSWORD / --password-stdin / keyring (never argv)"
        )
        rt.out.emit(d)
    else:
        for t in tgts:
            print(json.dumps(info_for(t), ensure_ascii=False), file=rt.out.stdout)


@auth.command("login")
@global_options
@click.pass_context
def auth_login(ctx, **_):
    """Store one device's password in the OS keyring (keyed by user@host)."""
    rt = make_runtime(ctx)
    tgts = rt.targets()
    if len(tgts) != 1:
        raise AppError(
            ExitCode.USAGE,
            "ONE_DEVICE",
            "auth login targets exactly one device",
            "pass a single --host or --device",
        )
    s = tgts[0].settings
    if not s["username"]:
        raise input_required("--username")
    pw = _password_for(s["host"], s["username"], rt.password_stdin)
    if not pw:
        if rt.no_input:
            raise input_required("password (set NXSTATE_PASSWORD or --password-stdin)")
        import getpass

        pw = getpass.getpass("NX-OS password: ")
    try:
        import keyring

        keyring.set_password("nxstate", f"{s['username']}@{s['host']}", pw)
    except Exception as e:
        raise AppError(
            ExitCode.CONFIG,
            "KEYRING_UNAVAILABLE",
            f"could not store credential: {e}",
            "use NXSTATE_PASSWORD / --password-stdin instead, or install a keyring backend",
        )
    rt.out.emit({"ok": True, "stored_for": f"{s['username']}@{s['host']}"})


@auth.command("logout")
@global_options
@click.pass_context
def auth_logout(ctx, **_):
    """Remove one device's stored credential from the OS keyring (local only)."""
    rt = make_runtime(ctx)
    tgts = rt.targets()
    if len(tgts) != 1:
        raise AppError(
            ExitCode.USAGE,
            "ONE_DEVICE",
            "auth logout targets exactly one device",
            "pass a single --host or --device",
        )
    s = tgts[0].settings
    if not s["username"]:
        raise input_required("--username")
    handle = f"{s['username']}@{s['host']}"
    removed = False
    try:
        import keyring

        if keyring.get_password("nxstate", handle) is not None:
            keyring.delete_password("nxstate", handle)
            removed = True
    except Exception as e:
        raise AppError(
            ExitCode.CONFIG,
            "KEYRING_UNAVAILABLE",
            f"could not access the keyring: {e}",
            "no keyring backend available",
        )
    # Removes local credentials only; it does not affect the device account.
    rt.out.emit({"ok": True, "removed": removed, "handle": handle})


@cli.command()
@global_options
@click.pass_context
def doctor(ctx, **_):
    """Diagnose reachability, transport, and credentials for the target(s)."""
    rt = make_runtime(ctx)

    def diagnose(t: Target) -> tuple[bool, list[dict]]:
        s = t.settings
        cred_ok = bool(s["username"]) and bool(
            _password_for(s["host"], s["username"], rt.password_stdin)
        )
        checks = [
            {"name": "host", "ok": bool(s["host"]), "detail": s["host"] or "no host"},
            {
                "name": "credentials",
                "ok": cred_ok,
                "detail": "present"
                if cred_ok
                else "set --username + NXSTATE_PASSWORD (or nxstate auth login)",
            },
        ]
        if s["host"] and cred_ok:
            try:
                ok, detail = rt.client_for(t).reachable()
            except AppError as e:
                ok, detail = False, e.message
            checks.append({"name": f"reachable ({s['transport']})", "ok": ok, "detail": detail})
        else:
            checks.append(
                {"name": "reachable", "ok": False, "detail": "skipped (need host + credentials)"}
            )
        return all(c["ok"] for c in checks), checks

    tgts = rt.targets()
    any_fail = False
    if len(tgts) == 1:
        ok, checks = diagnose(tgts[0])
        any_fail = not ok
        rt.out.emit({"ok": ok, "checks": checks})
    else:
        for t in tgts:
            ok, checks = diagnose(t)
            any_fail = any_fail or not ok
            print(
                json.dumps({"device": t.name, "ok": ok, "checks": checks}, ensure_ascii=False),
                file=rt.out.stdout,
                flush=True,
            )
    if any_fail:
        raise click.exceptions.Exit(ExitCode.UNREACHABLE)


@cli.command()
@global_options
@click.pass_context
def schema(ctx, **_):
    """Print the machine-readable command schema (JSON)."""
    rt = make_runtime(ctx)
    info = cli.to_info_dict(click.Context(cli, info_name="nxstate"))
    rt.out.emit_json(
        {
            "tool": "nxstate",
            "version": __version__,
            "conformance": {"spec": "agent-cli-guidelines", "version": SPEC, "level": "Full"},
            "read_only": True,
            "commands": info,
            "exit_codes": exit_table(),
            "safety": {
                "read_only": True,
                "mutations": "none (WRITE_REFUSED on non-read input)",
                "allow_debug": rt.allow_debug,
                "allow_tech": rt.allow_tech,
                "no_input": rt.no_input,
            },
        }
    )


@cli.command()
@global_options
@click.pass_context
def agent(ctx, **_):
    """Print the bundled agent SKILL.md."""
    make_runtime(ctx).out.stdout.write(skill_content())


def _latest_release() -> tuple[str | None, str]:
    """(latest version on PyPI or None, upgrade command). Network, short timeout, **fail-silent**.

    Release source overridable via NXSTATE_RELEASES_URL (tests). Defaults to the official PyPI
    JSON API — a structured, versioned endpoint, so no backpressure handling is needed.
    """
    import json as _json
    import os
    import urllib.request

    upgrade = "uv tool install --upgrade nxstate"
    url = os.environ.get("NXSTATE_RELEASES_URL", "https://pypi.org/pypi/nxstate/json")
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as r:  # noqa: S310 (https only)
            data = _json.load(r)
        return (data.get("info", {}).get("version") or None), upgrade
    except Exception:
        return None, upgrade


def _update_available(latest: str | None, current: str) -> bool:
    """Dev/source builds never report an update — don't nag them."""
    if not latest or not current or current == "dev":
        return False
    return latest.lstrip("v") != current.lstrip("v")


@cli.command()
@click.option(
    "--check",
    is_flag=True,
    help="Check PyPI for a newer release (network, short timeout, fail-silent).",
)
@global_options
@click.pass_context
def version(ctx, check, **_):
    """Print the version, or with --check report whether a newer release exists.

    Update awareness, never self-mutation: the tool never auto-updates; it only reports the
    upgrade command for the human / package manager.
    """
    rt = make_runtime(ctx)
    if not check:
        rt.out.emit({"version": __version__})
        return
    latest, upgrade = _latest_release()
    out = {
        "current": __version__,
        "latest": latest,
        "updateAvailable": _update_available(latest, __version__),
        "upgrade": upgrade,
    }
    if latest is None:
        out["note"] = "could not check for updates"
    rt.out.emit(out)


# --- entry / exit mapping -------------------------------------------------------------------


def run(argv: list[str] | None = None) -> int:
    try:
        # With standalone_mode=False, Click *returns* the code from ctx.exit()/Exit (e.g. our
        # doctor/partial exits, --help, --version) rather than raising it — so honor the return.
        rv = cli.main(args=argv, standalone_mode=False)
        return rv if isinstance(rv, int) else ExitCode.OK
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
        print(
            json.dumps(
                {"error": e.message, "code": e.code, "remediation": e.remediation},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
    else:
        print(f"error: {e.message}", file=sys.stderr)
        if e.code:
            print(f"  code: {e.code}", file=sys.stderr)
        if e.remediation:
            print(f"  fix:  {e.remediation}", file=sys.stderr)


def main() -> None:
    sys.exit(run())
