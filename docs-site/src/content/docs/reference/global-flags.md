---
title: Global flags
description: Every nxstate global flag — type, default, and meaning — grouped by function.
owner: rnwolfe
lastReviewed: 2026-06-23
---

Global flags apply to every command and can appear in any position — before the subcommand, after it, or between subcommand levels. nxstate merges flag values leaf-first up the Click context tree, so placement never matters.

```bash
# All three are equivalent:
nxstate --format json interface list
nxstate interface --format json list
nxstate interface list --format json
```

> **Read-only guarantee.** There is no `--allow-mutations` flag. nxstate has no mutation capability by design. The `show` passthrough validates input against a blocklist of forbidden leaders (`conf`, `configure`, `write`, `clear`, `reload`, …) and refuses anything that is not a `show …` command with exit code 11 (`WRITE_REFUSED`) — without connecting to the device. The `debug` passthrough is gated by `--allow-debug` and always prepends `debug` to your input. See [Read-only safety](/concepts/read-only-safety/) for details.

---

## Output flags

These flags control what is printed to stdout and how.

| Flag | Type | Default | Description |
|---|---|---|---|
| `--format` | `json\|plain\|tsv` | `plain` | Output format. `json` = 2-space indented JSON. `plain` = aligned columns (human-readable table). `tsv` = tab-separated values for pipelines. |
| `--json` | flag | off | Shorthand for `--format json`. |
| `--no-color` | flag | off | Disable ANSI color in `plain` output. Color is only emitted on a TTY anyway; this flag forces it off explicitly. |
| `--select` | string | — | Comma-separated dot-path field projection applied to every output row. Nested paths use dots: `--select interface_name,state.admin_state`. Non-existent paths are silently omitted. |
| `--limit` | integer | `50` | Maximum number of rows emitted by list commands. When the limit is hit, a truncation note is written to stderr. Pass `--limit 0` to disable bounding. |
| `--concise` | flag | off | Request terser output (command-specific). |
| `--detailed` | flag | off | Request richer output (command-specific). |

### Format examples

```bash
# JSON output — pipe-friendly, stable schema
nxstate --format json vlan list

# Alias
nxstate --json vlan list

# TSV — for awk, cut, or spreadsheet import
nxstate --format tsv interface list

# Narrow columns with --select and limit rows
nxstate --select interface_name,oper_st --limit 10 interface list
```

JSON is always written to stdout; notes and errors go to stderr. This separation makes `nxstate … | jq` reliable even when warnings are present.

### Notes on --no-color

`NO_COLOR` (any non-empty value) is also honoured as an environment variable. The flag takes precedence over the environment variable. See [Environment variables](/reference/environment-variables/) for the full env var list.

---

## Connection flags

These flags identify and authenticate to a single target switch. For multi-device targeting, see [Inventory and fan-out flags](#inventory-and-fan-out-flags) below.

| Flag | Short | Type | Default | Description |
|---|---|---|---|---|
| `--host` | — | string | `$NXSTATE_HOST` | Hostname or IP of the target switch. |
| `--port` | — | integer | transport default | TCP port. SSH defaults to 22; NX-API defaults to 443. |
| `--username` | `-u` | string | `$NXSTATE_USERNAME` | Login username. Use a `network-operator` (read-only) account. |
| `--transport` | — | `ssh\|nxapi\|auto` | `auto` | Access method. `auto` probes NX-API first and falls back to SSH if NX-API is unavailable. |
| `--timeout` | — | integer | `30` | Per-command timeout in seconds. |
| `--insecure` | — | flag | off | Skip TLS certificate verification for NX-API. Required when the switch uses a self-signed certificate. |
| `--password-stdin` | — | flag | off | Read the password from the first line of stdin instead of prompting or the keyring. |

### Credential resolution order

Passwords are never accepted on the command line. The resolution order is:

1. `--password-stdin` (reads one line from stdin)
2. `NXSTATE_PASSWORD` environment variable
3. OS keyring entry stored by `nxstate auth login` (key: `user@host`)
4. Interactive prompt — only on a TTY and only when `--no-input` is not set

See [Authentication](/guides/authentication/) for a complete walkthrough.

### Transport selection

```bash
# Explicit SSH (useful when NX-API is disabled on the switch)
nxstate --transport ssh --host 10.0.0.1 -u admin system version

# NX-API with self-signed cert
nxstate --transport nxapi --insecure --host 10.0.0.1 -u admin system version

# Default: auto-probe (NX-API → SSH)
nxstate --host 10.0.0.1 -u admin system version
```

SSH uses scrapli's `cisco_nxos` platform and runs `<cmd> | json` on the device. NX-API posts to `/ins` with `output_format: json`. Both paths produce the same normalized output. See [Transports and parsing](/concepts/transports-and-parsing/) for the full pipeline.

### RBAC recommendation

Provision a `network-operator` read-only account for nxstate. The stock `network-operator` role blocks `show running-config` and `show startup-config`; a custom read role is needed for those (but it still grants no configuration rights).

---

## Safety gate flags

These flags unlock commands that are expensive or have control-plane side effects. They must be passed explicitly — there is no way to enable them globally at configuration time.

| Flag | Type | Default | Description |
|---|---|---|---|
| `--allow-debug` | flag | off | Permit `nxstate debug "<cmd>"` commands. Debug reads are gated because they load the supervisor CPU. A warning is printed to stderr when this flag is active. |
| `--allow-tech` | flag | off | Permit `nxstate tech-support`. The full tech-support bundle is large and slow. |

Without `--allow-debug`, the `debug` subcommand exits with code 6 (`DEBUG_BLOCKED`). Without `--allow-tech`, `tech-support` exits with code 6 (`TECH_BLOCKED`).

```bash
# Blocked by default:
nxstate --host sw1 -u admin debug "show platform internal event-history errors"
# error: debug command ... is gated
#   code: DEBUG_BLOCKED
#   fix:  re-run with --allow-debug if you accept the control-plane load

# Unlocked:
nxstate --allow-debug --host sw1 -u admin debug "show platform internal event-history errors"
```

These flags do not affect curated state commands (`interface list`, `bgp summary`, etc.) — those are always permitted.

---

## Inventory and fan-out flags

Use these flags to target devices from your [inventory file](/reference/inventory-schema/) instead of a single `--host`. When more than one device resolves, nxstate runs concurrently and streams one NDJSON line per device as each completes.

| Flag | Type | Default | Description |
|---|---|---|---|
| `--device NAME` | string (repeatable) | — | Target inventory host(s) by name. Supports glob patterns (`*`, `?`). Repeat to add multiple devices. |
| `--group NAME` | string (repeatable) | — | Target all hosts in an inventory group. Repeat to include multiple groups. |
| `--all` | flag | off | Target every host in the inventory. |
| `--inventory PATH` | string | `~/.config/nxstate/inventory.yaml` | Path to the inventory YAML file. Also settable via `$NXSTATE_INVENTORY`. |
| `--workers N` | integer | `10` | Maximum number of concurrent device connections during fan-out. |

### Targeting examples

```bash
# Single named device
nxstate --device spine-01 vlan list

# Glob: all devices whose name starts with "spine-"
nxstate --device "spine-*" vlan list

# Multiple explicit devices
nxstate --device spine-01 --device leaf-01 vlan list

# All devices in a group
nxstate --group datacenter-a vlan list

# Multiple groups
nxstate --group datacenter-a --group datacenter-b vlan list

# Every host in the inventory
nxstate --all vlan list

# Custom inventory file
nxstate --inventory /etc/nxstate/prod.yaml --all system version
```

### Fan-out output format

When more than one device resolves, the output is NDJSON — one JSON object per line, in completion order:

```json
{"device": "spine-01", "host": "10.0.0.1", "ok": true, "data": [...]}
{"device": "leaf-01",  "host": "10.0.0.2", "ok": true, "data": [...]}
{"device": "leaf-02",  "host": "10.0.0.3", "ok": false, "error": {"code": "UNREACHABLE", "message": "..."}}
```

A single resolved device produces clean single-object output (not NDJSON). Failures are isolated per device — one unreachable switch does not stop the others. When any device fails, the exit code is 15 (`PARTIAL`). See [Inventory and fan-out](/guides/inventory-and-fanout/) for inventory YAML syntax and full examples.

### Worker tuning

```bash
# Slow, safe: one at a time
nxstate --all --workers 1 system version

# Aggressive: 32 concurrent (watch your switch AAA rate limits)
nxstate --all --workers 32 system version
```

---

## Automation flags

| Flag | Type | Default | Description |
|---|---|---|---|
| `--no-input` | flag | off | Never prompt for missing credentials or other input. Raises exit code 13 (`INPUT_REQUIRED`) instead. Required in non-TTY environments (CI, scripts, agents). |

```bash
# Script-safe: fail cleanly if the password is missing rather than hanging on a prompt
NXSTATE_PASSWORD="$PW" nxstate --no-input --host sw1 -u admin interface list
```

---

## Flag resolution precedence

When a flag is set in multiple ways, the resolution order is (highest wins):

1. **CLI flag** (any position on the command line)
2. **Inventory host/group/defaults** (for connection settings)
3. **Environment variable** (`NXSTATE_HOST`, `NXSTATE_USERNAME`, `NXSTATE_TRANSPORT`, `NXSTATE_PORT`)
4. **Built-in default** (shown in the tables above)

Passwords follow their own separate order: `--password-stdin` → `NXSTATE_PASSWORD` → OS keyring → interactive prompt.

See [Environment variables](/reference/environment-variables/) for the complete list of env vars and [Authentication](/guides/authentication/) for the credential resolution detail.

---

## Quick reference card

```bash
nxstate [OUTPUT] [CONNECTION] [SAFETY] [INVENTORY] COMMAND [SUBCOMMAND] [ARGS]

OUTPUT:
  --format json|plain|tsv   --json   --no-color
  --select FIELDS           --limit N
  --concise                 --detailed

CONNECTION (single switch):
  --host HOST               --port PORT
  --username / -u USER      --transport ssh|nxapi|auto
  --timeout SECS            --insecure
  --password-stdin

SAFETY GATES:
  --allow-debug             --allow-tech

INVENTORY / FAN-OUT:
  --device NAME (glob, repeatable)
  --group NAME (repeatable)
  --all
  --inventory PATH
  --workers N

AUTOMATION:
  --no-input
```

---

## Related pages

- [Output and filtering](/guides/output-and-filtering/) — `--format`, `--select`, `--limit` in depth with real output samples
- [Authentication](/guides/authentication/) — credential setup, keyring, `--password-stdin`, CI patterns
- [Inventory and fan-out](/guides/inventory-and-fanout/) — inventory YAML structure, device/group targeting, NDJSON processing
- [Environment variables](/reference/environment-variables/) — full env var reference
- [Exit codes](/reference/exit-codes/) — all exit codes including `WRITE_REFUSED` (11), `DEBUG_BLOCKED` (6), `PARTIAL` (15)
- [Command reference](/reference/commands/) — the full command tree
