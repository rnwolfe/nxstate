"""Stable exit-code table and the structured CLI error type. See contract.md §3, §4.

nxstate is read-only by design, so there is no mutation gate / MUTATION_BLOCKED. Instead the
`show`/`debug` passthrough refuses any non-read command with WRITE_REFUSED (exit 11)."""

from __future__ import annotations


class ExitCode:
    OK = 0
    GENERIC = 1
    USAGE = 2
    EMPTY = 3
    AUTH = 4
    NOT_FOUND = 5
    PERM = 6
    RATE = 7
    RETRY = 8
    UNREACHABLE = 9
    CONFIG = 10
    WRITE_REFUSED = 11
    INPUT_REQUIRED = 13
    PARSE_UNAVAILABLE = 14
    CANCELLED = 130


def exit_table() -> dict[str, int]:
    return {
        "ok": ExitCode.OK,
        "generic_error": ExitCode.GENERIC,
        "usage": ExitCode.USAGE,
        "empty_results": ExitCode.EMPTY,
        "auth_required": ExitCode.AUTH,
        "not_found": ExitCode.NOT_FOUND,
        "permission": ExitCode.PERM,
        "rate_limited": ExitCode.RATE,
        "retryable": ExitCode.RETRY,
        "unreachable": ExitCode.UNREACHABLE,
        "config_error": ExitCode.CONFIG,
        "write_refused": ExitCode.WRITE_REFUSED,
        "input_required": ExitCode.INPUT_REQUIRED,
        "parse_unavailable": ExitCode.PARSE_UNAVAILABLE,
        "cancelled": ExitCode.CANCELLED,
    }


class AppError(Exception):
    """Structured error carrying a machine code, remediation, and process exit code."""

    def __init__(self, exit_code: int, code: str, message: str, remediation: str = ""):
        super().__init__(message)
        self.exit = exit_code
        self.code = code
        self.message = message
        self.remediation = remediation


def write_refused(command: str, reason: str) -> AppError:
    return AppError(
        ExitCode.WRITE_REFUSED, "WRITE_REFUSED",
        f"refused non-read command: {command!r} ({reason})",
        "nxstate is read-only; only 'show ...' commands are permitted (no conf t / mutations)",
    )


def debug_blocked(command: str) -> AppError:
    return AppError(
        ExitCode.PERM, "DEBUG_BLOCKED",
        f"debug command {command!r} is control-plane-impacting and is gated",
        "re-run with --allow-debug if you accept the control-plane load",
    )


def host_required() -> AppError:
    return AppError(
        ExitCode.USAGE, "HOST_REQUIRED", "no target switch given",
        "pass --host <switch> (and credentials via --username + NXSTATE_PASSWORD / --password-stdin)",
    )


def unreachable(host: str, detail: str) -> AppError:
    return AppError(
        ExitCode.UNREACHABLE, "UNREACHABLE", f"{host} is not reachable: {detail}",
        "check connectivity, --transport, --port, and credentials (nxstate doctor --host ...)",
    )


def auth_required(detail: str) -> AppError:
    return AppError(
        ExitCode.AUTH, "AUTH_REQUIRED", f"authentication failed: {detail}",
        "run: nxstate auth login --host <switch> --username <user>",
    )


def not_found(kind: str, ident: str) -> AppError:
    return AppError(
        ExitCode.NOT_FOUND, "NOT_FOUND", f"{kind} {ident} not found",
        f"list available {kind}s to find a valid name",
    )


def input_required(what: str) -> AppError:
    return AppError(
        ExitCode.INPUT_REQUIRED, "INPUT_REQUIRED", f"{what} is required",
        "pass it as a flag/argument (running with --no-input, so prompts are disabled)",
    )
