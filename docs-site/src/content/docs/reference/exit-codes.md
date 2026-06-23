---
title: Exit codes
description: Complete reference for every nxstate exit code — machine names, numeric values, and the conditions that trigger each one.
owner: rnwolfe
lastReviewed: 2026-06-23
---

Every nxstate invocation exits with a predictable numeric code. Scripts, CI pipelines, and agent loops can branch on these codes without parsing stderr text. The codes are stable across minor versions.

## Live table from the tool

`nxstate schema` always returns the canonical, version-locked table under the `exit_codes` key:

```bash
nxstate schema | jq .exit_codes
```

```json
{
  "ok": 0,
  "generic_error": 1,
  "usage": 2,
  "empty_results": 3,
  "auth_required": 4,
  "not_found": 5,
  "permission": 6,
  "rate_limited": 7,
  "retryable": 8,
  "unreachable": 9,
  "config_error": 10,
  "write_refused": 11,
  "input_required": 13,
  "parse_unavailable": 14,
  "partial": 15,
  "cancelled": 130
}
```

The table below is the human-readable companion to that output.

## Complete exit-code table

| Code | Machine name | When it occurs |
|------|-------------|----------------|
| 0 | `ok` | Command completed successfully. |
| 1 | `generic_error` | An unexpected error occurred that does not fit a more specific code. |
| 2 | `usage` | Bad CLI invocation — unknown flag, missing required argument, or no target host given (`HOST_REQUIRED`). |
| 3 | `empty_results` | The device responded successfully but returned no rows or an empty data set. |
| 4 | `auth_required` | Authentication failed — wrong password, key rejected, or no credentials found (`AUTH_REQUIRED`). |
| 5 | `not_found` | The requested resource (interface, VRF, device name, etc.) does not exist on the device (`NOT_FOUND`). |
| 6 | `permission` | The operation is gated and the required flag was not passed. Covers `DEBUG_BLOCKED` (use `--allow-debug`) and `TECH_BLOCKED` (use `--allow-tech`). Also raised when the NX-OS user account lacks privilege to run the command. |
| 7 | `rate_limited` | The device or NX-API endpoint rejected the request due to rate limiting. Back off and retry. |
| 8 | `retryable` | A transient failure occurred (timeout, partial read). Retrying the same command is likely to succeed. |
| 9 | `unreachable` | The device could not be reached — TCP refused, SSH handshake failed, DNS not resolving (`UNREACHABLE`). Also the exit code from `nxstate doctor` when any check fails. |
| 10 | `config_error` | A configuration problem prevented execution — for example, the OS keyring is unavailable (`KEYRING_UNAVAILABLE`), the inventory file is malformed, or an option combination is invalid. |
| 11 | `write_refused` | The `show` or `debug` passthrough rejected a non-read command (`WRITE_REFUSED`). nxstate validates the command *before* connecting to the device: anything that does not start with `show`, or whose first token matches a forbidden leader (`conf`, `configure`, `write`, `wr`, `copy`, `reload`, `clear`, `no`, `set`, `delete`, `erase`, `format`, `reset`, `shutdown`, and others), is refused immediately. There is no override flag — nxstate is read-only by design. |
| 13 | `input_required` | An interactive prompt was needed but `--no-input` is set, or the process has no TTY. Pass the missing value via a flag, environment variable, or `--password-stdin` (`INPUT_REQUIRED`). |
| 14 | `parse_unavailable` | The response could not be parsed and no fallback parser (Genie, ntc-templates) was available. Install the `[genie]` extra or check for a supported NTCTemplates entry. |
| 15 | `partial` | Fan-out across multiple devices completed, but at least one device failed. NDJSON output is still written to stdout for the devices that succeeded; per-device errors are embedded in the stream. |
| 130 | `cancelled` | The process received an interrupt signal (Ctrl-C / SIGINT). |

## Structured error output

When an error occurs, nxstate writes to **stderr** (stdout carries only data). The format depends on `--format`:

**Plain (default)**

```
error: refused non-read command: 'conf t' (only 'show ...' read commands are permitted)
  code: WRITE_REFUSED
  fix:  nxstate is read-only; only 'show ...' commands are permitted (no conf t / mutations)
```

**JSON (`--format json` or `--json`)**

```json
{
  "error": "refused non-read command: 'conf t' (only 'show ...' read commands are permitted)",
  "code": "WRITE_REFUSED",
  "remediation": "nxstate is read-only; only 'show ...' commands are permitted (no conf t / mutations)"
}
```

The `code` field is the machine name (all-caps snake-case) and is stable. Parse `code`, not the human-readable `error` string.

## Common scenarios and their codes

### No host given

```bash
nxstate interface list
# exit 2 (usage / HOST_REQUIRED)
```

Pass `--host`, set `NXSTATE_HOST`, or use `--device` / `--group` with an inventory file. See [inventory and fan-out](/guides/inventory-and-fanout/).

### Authentication failure

```bash
nxstate system version --host sw01 --username baduser
# exit 4 (auth_required / AUTH_REQUIRED)
```

Run `nxstate auth login --host sw01 --username <user>` to store the credential in the OS keyring, or export `NXSTATE_PASSWORD`. See [authentication](/guides/authentication/).

### Device not reachable

```bash
nxstate doctor --host 10.0.0.99 --username admin
# exit 9 (unreachable / UNREACHABLE)
```

Check connectivity, firewall rules, and whether NX-API or SSH is enabled on the device. See [troubleshooting](/guides/troubleshooting/).

### Write attempt rejected

```bash
nxstate show "conf t"
# exit 11 (write_refused / WRITE_REFUSED) — NO connection is made
```

nxstate validates the command locally. `conf`, `configure`, `write`, `clear`, `reload`, `no`, and similar leaders are refused without opening a session to the device. See [read-only safety](/concepts/read-only-safety/).

### Debug command blocked

```bash
nxstate debug "ip packet eth1/1"
# exit 6 (permission / DEBUG_BLOCKED)
```

Re-run with `--allow-debug` after verifying you understand the control-plane impact. `nxstate tech-support` similarly requires `--allow-tech` (also exit 6 / `TECH_BLOCKED` when omitted).

### Fan-out partial failure

```bash
nxstate interface list --group core
# exit 15 (partial) if ≥1 device failed
```

Inspect the NDJSON stream. Each object has `"ok": true|false`; failed objects include an `error` field with `code`, `message`, and `remediation`. Successful devices' data is still present.

### Password prompt suppressed

```bash
nxstate system version --host sw01 --username admin --no-input
# exit 13 (input_required / INPUT_REQUIRED) when no credential is found
```

Supply the password via `NXSTATE_PASSWORD` or `--password-stdin` when running non-interactively.

## Using exit codes in scripts

```bash
nxstate interface list --host sw01 --format json > ifaces.json
code=$?

case $code in
  0)  echo "ok" ;;
  3)  echo "no interfaces returned" ;;
  4)  echo "auth failed — check credentials" ;;
  9)  echo "device unreachable" ;;
  11) echo "BUG: tried to run a write command" ;;
  15) echo "partial: some devices failed, check NDJSON" ;;
  *)  echo "unexpected error: $code" ;;
esac
```

## Related pages

- [Global flags](/reference/global-flags/) — `--no-input`, `--allow-debug`, `--allow-tech`, `--format`
- [Read-only safety](/concepts/read-only-safety/) — why `WRITE_REFUSED` fires before any connection
- [Authentication](/guides/authentication/) — resolving `AUTH_REQUIRED` and `INPUT_REQUIRED`
- [Inventory and fan-out](/guides/inventory-and-fanout/) — the `partial` exit code in multi-device runs
- [Troubleshooting](/guides/troubleshooting/) — diagnosing `UNREACHABLE` and `CONFIG_ERROR`
