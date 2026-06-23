"""Nexus client: read-only state retrieval over SSH (scrapli, core `cisco_nxos`) with an
NX-API `cli_show` accelerator. Structured output strategy (best → fallback):

    NX-API cli_show JSON  →  SSH `<cmd> | json`  →  Genie parse  →  ntc-templates  →  raw text

Genie is optional (the `[genie]` extra); without it we rely on `| json` + ntc-templates.
Result shape (stable contract for every show):
    {"command", "parsed": <dict|list|None>, "raw": <str|None>, "parser": "nxapi|json|genie|ntc|text"}
"""

from __future__ import annotations

import base64
import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass

from .errors import AppError, ExitCode, auth_required, unreachable


def normalize_nxos(obj):
    """Unwrap NX-OS `| json` list wrappers ({"TABLE_x": {"ROW_x": [...]}}) into plain lists,
    recursively, so --select/--limit/tsv work on a clean array. Other shapes pass through."""
    if isinstance(obj, dict):
        keys = list(obj)
        tables = [k for k in keys if k.startswith("TABLE_")]
        if len(keys) == 1 and tables:
            inner = obj[tables[0]]
            if isinstance(inner, dict):
                rows = [k for k in inner if k.startswith("ROW_")]
                if rows:
                    val = inner[rows[0]]
                    return normalize_nxos(val if isinstance(val, list) else [val])
        return {k: normalize_nxos(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_nxos(x) for x in obj]
    return obj


def first_rows(obj):
    """Return the first NX-OS ROW_* collection as a clean list (the primary table of a
    list-style `show`). Falls back to normalize_nxos(obj) when no ROW_ table is present.
    For deeply-nested/multi-table commands (e.g. routing), install the [genie] extra for
    richer parsing."""
    found = _find_rows(obj)
    return found if found is not None else normalize_nxos(obj)


def _find_rows(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("ROW_"):
                rows = v if isinstance(v, list) else [v]
                return [normalize_nxos(r) for r in rows]
        for v in obj.values():
            r = _find_rows(v)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for x in obj:
            r = _find_rows(x)
            if r is not None:
                return r
    return None


class _NxapiUnavailable(Exception):
    """NX-API not reachable/enabled — signals auto-transport to fall back to SSH."""


@dataclass
class NexusClient:
    host: str
    username: str | None = None
    password: str | None = None
    port: int | None = None
    transport: str = "auto"  # ssh | nxapi | auto
    timeout: int = 30
    insecure: bool = False

    # ---- public API ---------------------------------------------------------

    def run_show(self, command: str, parse: bool = True) -> dict:
        if self.transport in ("nxapi", "auto"):
            try:
                return self._nxapi_show(command)
            except _NxapiUnavailable as e:
                if self.transport == "nxapi":
                    raise unreachable(self.host, f"NX-API unavailable: {e}")
                # auto → fall through to SSH
        return self._ssh_show(command, parse)

    def reachable(self) -> tuple[bool, str]:
        try:
            r = self.run_show("show clock")
            return True, f"ok via {r.get('parser', '?')}"
        except AppError as e:
            return False, e.message

    # ---- NX-API accelerator -------------------------------------------------

    def _nxapi_show(self, command: str) -> dict:
        if not (self.username and self.password):
            raise _NxapiUnavailable("no credentials for NX-API")
        url = f"https://{self.host}:{self.port or 443}/ins"
        payload = {"ins_api": {"version": "1.0", "type": "cli_show", "chunk": "0",
                               "sid": "1", "input": command, "output_format": "json"}}
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        token = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
        ctx = ssl._create_unverified_context() if self.insecure else None
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise auth_required("NX-API rejected the credentials")
            raise _NxapiUnavailable(f"HTTP {e.code}")
        except (urllib.error.URLError, ssl.SSLError, ConnectionError, OSError, TimeoutError) as e:
            raise _NxapiUnavailable(str(e))

        out = body.get("ins_api", {}).get("outputs", {}).get("output", {})
        if isinstance(out, list):
            out = out[0] if out else {}
        code = str(out.get("code", ""))
        if code and code != "200":
            raise AppError(ExitCode.GENERIC, "DEVICE_ERROR",
                           out.get("msg", "device returned an error").strip(),
                           "verify the command is valid on this platform/version")
        return {"command": command, "parsed": out.get("body") or None, "raw": None,
                "parser": "nxapi"}

    # ---- SSH (scrapli) ------------------------------------------------------

    def _ssh_show(self, command: str, parse: bool) -> dict:
        from scrapli.driver.core import NXOSDriver
        from scrapli.exceptions import ScrapliAuthenticationFailed, ScrapliException

        if not self.username:
            raise auth_required("no username provided")
        conn_args = dict(host=self.host, auth_username=self.username,
                         auth_password=self.password or "", auth_strict_key=False,
                         transport="system", port=self.port or 22,
                         timeout_socket=self.timeout, timeout_ops=self.timeout,
                         ssh_config_file=False)
        try:
            with NXOSDriver(**conn_args) as conn:
                resp = conn.send_command(f"{command} | json")
                if not resp.failed:
                    try:
                        parsed = json.loads(resp.result)
                        if parsed:
                            return {"command": command, "parsed": parsed, "raw": None,
                                    "parser": "json"}
                    except (json.JSONDecodeError, ValueError):
                        pass
                # `| json` failed or wasn't structured — retry the bare command.
                resp = conn.send_command(command)
                if resp.failed:
                    raise _device_error(command, resp.result)
                raw = resp.result
                if parse:
                    if (g := _try_genie(resp)) is not None:
                        return {"command": command, "parsed": g, "raw": raw, "parser": "genie"}
                    if (n := _try_ntc(resp)) is not None:
                        return {"command": command, "parsed": n, "raw": raw, "parser": "ntc"}
                return {"command": command, "parsed": None, "raw": raw, "parser": "text"}
        except ScrapliAuthenticationFailed as e:
            raise auth_required(str(e))
        except (ScrapliException, OSError, TimeoutError) as e:
            raise unreachable(self.host, str(e))


def _device_error(command: str, output: str) -> AppError:
    msg = " ".join(output.split())[:200] or "device rejected the command"
    return AppError(ExitCode.GENERIC, "DEVICE_ERROR", f"{command!r}: {msg}",
                    "verify the command exists on this platform/version and the feature is enabled")


def _try_genie(resp) -> object | None:
    try:
        import genie  # noqa: F401  (the [genie] extra; skip quietly if absent)
    except Exception:
        return None
    try:
        g = resp.genie_parse_output()
        return g or None
    except Exception:
        return None


def _try_ntc(resp) -> object | None:
    try:
        n = resp.textfsm_parse_output()
        return n or None
    except Exception:
        return None
