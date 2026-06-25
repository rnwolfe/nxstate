---
title: Command reference
description: Exhaustive noun-verb command tree for nxstate — every subcommand, its arguments, the underlying NX-OS show it maps to, and whether it returns an array or an object.
owner: rnwolfe
lastReviewed: 2026-06-25
---

nxstate is a **read-only** CLI. Every command gathers state — none of them can configure a
device. The complete list follows, organized by noun group. Global flags (targeting, output,
credentials) apply to every command and are documented on [Global flags](/reference/global-flags/).

For a machine-readable version of this tree, run:

```bash
nxstate schema
```

That emits a JSON document containing `commands` (Click's `to_info_dict` tree), `exit_codes`,
and `safety` fields — no switch connection required.

---

## `system` — device facts

### `system version`

```bash
nxstate system version --host SW1 -u admin
```

Underlying show: `show version`

Returns an **object** with software version, platform, uptime, and serial number fields.
Uses `| json` or Genie (`[genie]` extra) for structured output.

```bash
# JSON output
nxstate system version --host SW1 -u admin --json
```

### `system environment`

```bash
nxstate system environment --host SW1 -u admin
```

Underlying show: `show environment`

Returns an **object** with power, fan, and temperature sensor readings.

### `system inventory`

```bash
nxstate system inventory --host SW1 -u admin
```

Underlying show: `show inventory`

Returns an **object** (or array when Genie is available) of hardware inventory records
(chassis, linecards, power supplies, fans).

---

## `interface` — interface state and counters

### `interface list`

```bash
nxstate interface list --host SW1 -u admin
```

Underlying show: `show interface brief`

Returns an **array** of interface summary rows (name, state, IP, speed). Subject to
`--limit` (default 50).

```bash
# Show all interfaces, no truncation
nxstate interface list --host SW1 -u admin --limit 0

# TSV for scripting
nxstate interface list --host SW1 -u admin --format tsv
```

### `interface show <name>`

```bash
nxstate interface show Ethernet1/1 --host SW1 -u admin
```

`<name>` is required and is passed directly to the device.

Underlying show: `show interface <name>`

Returns an **array** (one entry per matched interface — NX-OS may expand wildcards on
the device side, but the CLI accepts the name literally).

```bash
# Detailed counters for a port-channel
nxstate interface show port-channel10 --host SW1 -u admin --json
```

### `interface counters [name]`

```bash
# All interfaces
nxstate interface counters --host SW1 -u admin

# One interface
nxstate interface counters Ethernet1/1 --host SW1 -u admin
```

`name` is optional. When omitted, counters are fetched for all interfaces.

Underlying show: `show interface counters` or `show interface <name> counters`

Returns an **array** of counter rows.

---

## `vlan` — VLAN state

### `vlan list`

```bash
nxstate vlan list --host SW1 -u admin
```

Underlying show: `show vlan`

Returns an **array** of VLAN rows (id, name, state, ports).

```bash
# Select only id and name columns
nxstate vlan list --host SW1 -u admin --select id,name --format tsv
```

---

## `route` — routing table

### `route list [--vrf VRF]`

```bash
# Default VRF
nxstate route list --host SW1 -u admin

# Named VRF
nxstate route list --vrf MGMT --host SW1 -u admin
```

| Flag | Default | Description |
|------|---------|-------------|
| `--vrf VRF` | _(default VRF)_ | Restrict output to the named VRF. |

Underlying show: `show ip route` or `show ip route vrf <vrf>`

Returns an **array** of route rows. For deeply-nested multi-table output, install the
`[genie]` extra for richer structured parsing.

---

## `bgp` — BGP state

### `bgp summary [--vrf VRF]`

```bash
# Default VRF
nxstate bgp summary --host SW1 -u admin

# Named VRF
nxstate bgp summary --vrf prod --host SW1 -u admin
```

| Flag | Default | Description |
|------|---------|-------------|
| `--vrf VRF` | _(default VRF)_ | Restrict to the named VRF. |

Underlying show: `show ip bgp summary` or `show ip bgp summary vrf <vrf>`

Returns an **array** of BGP peer summary rows.

---

## `neighbor` — CDP/LLDP neighbor discovery

### `neighbor list [--protocol cdp|lldp]`

```bash
# Default: LLDP
nxstate neighbor list --host SW1 -u admin

# CDP instead
nxstate neighbor list --protocol cdp --host SW1 -u admin
```

| Flag | Default | Description |
|------|---------|-------------|
| `--protocol cdp\|lldp` | `lldp` | Discovery protocol to query. |

Underlying show: `show lldp neighbors` or `show cdp neighbors`

Returns an **array** of neighbor rows.

---

## `mac` — MAC address table

### `mac list`

```bash
nxstate mac list --host SW1 -u admin
```

Underlying show: `show mac address-table`

Returns an **array** of MAC table rows (MAC, VLAN, type, port).

---

## `arp` — ARP table

### `arp list`

```bash
nxstate arp list --host SW1 -u admin
```

Underlying show: `show ip arp`

Returns an **array** of ARP entries (IP, MAC, interface, age).

---

## `logging` — system log

```bash
nxstate logging --host SW1 -u admin
```

Underlying show: `show logging logfile`

Returns **raw text** (not a structured array or object). Because log content is free-form
device text that may contain arbitrary strings, the output is wrapped in
`BEGIN/END UNTRUSTED DEVICE OUTPUT` markers when printed in plain mode, and the JSON
envelope sets `"untrusted": true` — so an LLM agent will not follow instructions embedded
in log messages.

```bash
# JSON envelope showing the untrusted flag
nxstate logging --host SW1 -u admin --json
# {
#   "command": "show logging logfile",
#   "parser": "text",
#   "raw": "...",
#   "untrusted": true
# }
```

---

## `show "<cmd>"` — generic read passthrough

```bash
nxstate show "show ip ospf neighbors" --host SW1 -u admin
nxstate show "show ip interface brief" --host SW1 -u admin --json
```

Run any arbitrary NX-OS `show` command. The argument is the **complete command string**,
including the leading `show`. nxstate validates the input before connecting:

- The command **must** start with `show`. Any other leading token is refused.
- The following leaders are always blocked, regardless of context:
  `conf`, `configure`, `write`, `wr`, `copy`, `reload`, `boot`, `install`, `clear`,
  `no`, `set`, `delete`, `erase`, `format`, `reset`, `shutdown`, `switchto`, `attach`,
  `vsh`, `run`, `python`, `bash`, `guestshell`, `feature`.
- Multi-line or newline-separated commands are refused.
- Validation happens **without connecting** to the switch. A refused command exits **11
  (WRITE_REFUSED)** immediately.

Output shape depends on what parsers are available:

| Parser available | Output |
|-----------------|--------|
| NX-API JSON / `\| json` | Structured array or object |
| Genie (`[genie]` extra) | Structured (293 NX-OS parsers) |
| ntc-templates | Structured array |
| None | Raw text, fenced untrusted |

Returns an **array** when the underlying data is tabular (extracted from the primary
`ROW_*` table); returns an **object** for show commands with a single-record response.

```bash
# Works — valid show command
nxstate show "show ip ospf neighbors detail" --host SW1 -u admin

# Refused without connecting — exits 11
nxstate show "configure terminal"
# error: refused non-read command: 'configure terminal' ('configure' is not a read command)
#   code: WRITE_REFUSED
```

---

## `debug "<cmd>"` — gated debug reads

```bash
nxstate debug "ip routing" --host SW1 -u admin --allow-debug
```

Run a `debug ...` command that produces control-plane state. Because debug commands can
load the supervisor CPU, this requires **`--allow-debug`** on every invocation. Without
it the command exits **6 (DEBUG_BLOCKED)** before connecting.

nxstate prepends `debug ` to the argument you pass, so pass only the portion after
`debug`:

```bash
# Runs: debug ip routing
nxstate debug "ip routing" --host SW1 -u admin --allow-debug
```

A warning is printed to stderr:

```
warning: debug commands load the supervisor CPU; keep captures short
```

Returns raw text wrapped as untrusted (same fencing as `logging`).

---

## `tech-support` — full tech-support capture

```bash
nxstate tech-support --host SW1 -u admin --allow-tech
```

Underlying show: `show tech-support`

Gated by **`--allow-tech`** because the output is very large and the command runs slowly.
Without the flag the command exits **6 (TECH_BLOCKED)** before connecting.

Returns raw text wrapped as untrusted.

---

## `auth` — credential management

`auth` subcommands manage how nxstate locates passwords. Passwords are **never** accepted
as a command-line argument. See [Authentication](/guides/authentication/) for the full
resolution order.

### `auth login`

```bash
nxstate auth login --host SW1 -u admin
```

Stores the password for `admin@SW1` in the OS keyring (keyed as `user@host` under the
`nxstate` service). Prompts for the password interactively (TTY required unless
`--password-stdin` or `NXSTATE_PASSWORD` is set). Targets exactly one device — passing
`--device` or `--group` that resolves to multiple hosts is an error.

Returns an **object**: `{"ok": true, "stored_for": "admin@SW1"}`.

```bash
# Non-interactive: pipe the password in
echo "$MY_SECRET" | nxstate auth login --host SW1 -u admin --password-stdin
```

### `auth status`

```bash
nxstate auth status --host SW1 -u admin
```

Reports whether a credential is available for the target — checks env, keyring, and
`--password-stdin` — **without connecting** to the switch.

Single device returns an **object**:

```json
{
  "host": "SW1",
  "username": "admin",
  "transport": "auto",
  "credential_present": true,
  "note": "credentials read from NXSTATE_PASSWORD / --password-stdin / keyring (never argv)"
}
```

Fan-out (`--device`, `--group`, `--all`) returns **NDJSON** — one object per device.

---

## `doctor` — connectivity check

```bash
nxstate doctor --host SW1 -u admin
```

Probes three things for each target, in order:

1. **host** — a host is configured.
2. **credentials** — username and password are available.
3. **reachable** — runs `show clock` against the switch (only attempted if checks 1 and
   2 pass).

Returns an **object** for a single target:

```json
{
  "ok": true,
  "checks": [
    {"name": "host",        "ok": true, "detail": "SW1"},
    {"name": "credentials", "ok": true, "detail": "present"},
    {"name": "reachable (auto)", "ok": true, "detail": "..."}
  ]
}
```

Fan-out streams **NDJSON** — one object per device. If any check fails, exits **9
(UNREACHABLE)**. See [Troubleshooting](/guides/troubleshooting/) for common failure
patterns.

---

## `schema` — machine-readable command tree

```bash
nxstate schema
```

Emits a JSON document — no switch connection required:

```json
{
  "tool": "nxstate",
  "version": "x.y.z",
  "conformance": {
    "spec": "agent-cli-guidelines",
    "version": "0.4.0",
    "level": "Full"
  },
  "read_only": true,
  "commands": { ... },
  "exit_codes": { ... },
  "safety": {
    "read_only": true,
    "mutations": "none (WRITE_REFUSED on non-read input)",
    "allow_debug": false,
    "allow_tech": false,
    "no_input": false
  }
}
```

`commands` is Click's `to_info_dict` representation of the full command tree, including
all subcommands and their options. `exit_codes` is the complete name→integer table.
Useful for agents bootstrapping their understanding of the tool; combine with
`nxstate agent` for the intent-level SKILL document.

The `conformance` block is the machine-readable declaration that nxstate implements the
[Agent CLI Guidelines](https://rnwolfe.github.io/agent-cli-guidelines/) at the stated
`version` and `level`. An agent can read it directly:

```bash
nxstate schema | jq .conformance
# {"spec":"agent-cli-guidelines","version":"0.4.0","level":"Full"}
```

---

## `agent` — bundled agent skill

```bash
nxstate agent
```

Prints the `SKILL.md` embedded in the package — a compact description of nxstate's
capabilities, credential resolution, inventory, output format, and exit codes, written
for consumption by an LLM agent. No switch connection required.

---

## `version` — tool version

```bash
nxstate version
```

Prints `{"version": "x.y.z"}`. Use `--json` if you need stable machine-readable output:

```bash
nxstate version --json
```

### `version --check`

Reports whether a newer release is available, without ever self-updating — nxstate only
tells you the upgrade command; the human or package manager runs it.

```bash
nxstate version --check --json
```

```json
{
  "current": "0.4.0",
  "latest": "0.5.0",
  "updateAvailable": true,
  "upgrade": "uv tool install --upgrade nxstate"
}
```

The check queries the official [PyPI JSON API](https://pypi.org/pypi/nxstate/json) with a
short (3s) timeout and is **fail-silent**: if the network is unavailable or the lookup
fails, it returns `"latest": null`, `"updateAvailable": false`, and a
`"note": "could not check for updates"` — it never errors or blocks an agent loop, and it
exits `0`. Source/dev builds (`current` of `"dev"`) never report an update.

The release source can be overridden with the `NXSTATE_RELEASES_URL` environment variable
(used in tests). For safety the override scheme is constrained — only `https`, or `http`
to `localhost`/`127.0.0.1`/`::1`; any other scheme (e.g. `file://`) or a remote `http`
URL is ignored and the default PyPI URL is used instead. See
[Environment variables](/reference/environment-variables/).

---

## Output shape summary

| Command | Returns |
|---------|---------|
| `system version` | object |
| `system environment` | object |
| `system inventory` | object |
| `interface list` | array |
| `interface show <name>` | array |
| `interface counters [name]` | array |
| `vlan list` | array |
| `route list` | array |
| `bgp summary` | array |
| `neighbor list` | array |
| `mac list` | array |
| `arp list` | array |
| `logging` | raw text (fenced untrusted) |
| `show "<cmd>"` | array, object, or raw text (parser-dependent) |
| `debug "<cmd>"` | raw text (fenced untrusted) |
| `tech-support` | raw text (fenced untrusted) |
| `auth login` | object |
| `auth status` | object (single) / NDJSON (fan-out) |
| `doctor` | object (single) / NDJSON (fan-out) |
| `schema` | object |
| `agent` | plain text (SKILL.md) |
| `version` | object |
| `version --check` | object (`current`, `latest`, `updateAvailable`, `upgrade`) |

---

## Related pages

- [Global flags](/reference/global-flags/) — targeting, output, credentials, transport flags that apply to every command.
- [Exit codes](/reference/exit-codes/) — complete exit-code table with remediation notes.
- [Authentication](/guides/authentication/) — credential resolution order, keyring setup, `--password-stdin`.
- [Inventory and fan-out](/guides/inventory-and-fanout/) — inventory YAML, `--device`, `--group`, `--all`, NDJSON streaming.
- [Output and filtering](/guides/output-and-filtering/) — `--format`, `--select`, `--limit`, `--concise`/`--detailed`.
- [Transports and parsing](/concepts/transports-and-parsing/) — SSH vs NX-API, the parsing pipeline, the `[genie]` extra.
- [Read-only safety](/concepts/read-only-safety/) — why WRITE_REFUSED exists and what it blocks.
