---
title: Quickstart
description: Go from install to your first read-only Nexus state query in under five minutes.
owner: rnwolfe
lastReviewed: 2026-06-23
---

This guide takes you from a fresh install to a working read against a Cisco Nexus switch. You will verify connectivity with `nxstate doctor`, pull structured version data as JSON, and list interfaces as TSV — all in five minutes or less.

nxstate is **read-only by design**. It can never configure a device. Any non-read input (anything that does not start with `show`) is refused before a connection is even made.

## Before you start

You need:

- Python 3.10 or later
- Network access to a Cisco Nexus switch that has SSH or NX-API reachable
- A **read-only account** on that switch — the stock `network-operator` role is ideal

Keep the account least-privilege. `network-operator` cannot run `show running-config` or `show startup-config` by design, which is exactly what you want for an automated read-only tool.

## Install

Pick the method that fits your workflow:

```bash
# One-shot trial — no install needed
uvx nxstate --help

# Install for repeated use (recommended)
uv tool install nxstate

# pip
pip install nxstate

# Maximum parser coverage: adds Genie's ~293 NX-OS parsers
uv tool install "nxstate[genie]"
```

Verify the install:

```bash
nxstate version
```

## Step 1 — Export your credentials

nxstate resolves connection settings with a most-specific-wins chain: **flag → inventory → environment → default**. Exporting environment variables once removes the need to type them on every command.

```bash
export NXSTATE_HOST=sw1
export NXSTATE_USERNAME=netops
export NXSTATE_PASSWORD=hunter2
```

A few things worth noting:

- Passwords are **never accepted on the command line** (no `--password` flag exists). The resolution order for the password is: `--password-stdin` → `NXSTATE_PASSWORD` → OS keyring (`nxstate auth login`) → interactive prompt when a TTY is available.
- `NXSTATE_HOST` can be a hostname or an IP address.
- The default transport is `auto`, which probes NX-API first and falls back to SSH. Force one with `--transport ssh` or `--transport nxapi`.

If you prefer to store the password in your OS keyring instead of an environment variable, see the [Authentication guide](/guides/authentication/).

## Step 2 — Run `nxstate doctor`

Before pulling state, verify that nxstate can reach the switch and that your credentials work:

```bash
nxstate doctor
```

When everything is healthy you get a structured result on stdout:

```json
{
  "ok": true,
  "checks": [
    { "name": "host",        "ok": true, "detail": "sw1" },
    { "name": "credentials", "ok": true, "detail": "present" },
    { "name": "reachable (auto)", "ok": true, "detail": "ok via nxapi" }
  ]
}
```

If `ok` is `false`, `doctor` exits with code `9` (`UNREACHABLE`) and the failing check's `detail` field tells you what to fix — typically a connectivity or credential issue. See the [Troubleshooting guide](/guides/troubleshooting/) for common remedies.

## Step 3 — Pull structured version data

```bash
nxstate system version --json
```

This runs `show version` over your chosen transport, normalizes the NX-OS `TABLE_/ROW_` envelope, and emits clean 2-space-indented JSON on stdout. Notes and warnings go to stderr so you can pipe stdout without noise.

Typical output (abbreviated):

```json
{
  "bios_ver_str": "07.69",
  "kickstart_ver_str": "10.3(8)",
  "nxos_ver_str": "10.3(8)",
  "chassis_id": "Nexus9000 C9300v Chassis",
  "cpu_name": "Intel(R) Xeon(R) ...",
  "kern_uptm_days": 4,
  "kern_uptm_hrs": 2,
  "kern_uptm_mins": 15,
  "kern_uptm_secs": 3,
  "proc_board_id": "9YXYUIBKHWL",
  "host_name": "sw1"
}
```

The `--json` flag is a shorthand for `--format json`. You can also use `--format plain` (the default, aligned columns) or `--format tsv`.

## Step 4 — List interfaces as TSV

TSV output is easy to import into spreadsheets or pipe to tools like `cut` and `awk`:

```bash
nxstate interface list --format tsv
```

Each row is a tab-separated line with one interface per row. The first row is the header. Example (columns trimmed for readability):

```
interface  state    speed    mtu
Ethernet1/1  connected  1000     1500
Ethernet1/2  notconnect  auto     1500
mgmt0      connected  1000     1500
```

List commands cap output at 50 rows by default. Change the cap with `--limit N` or disable it with `--limit 0`. When output is truncated, a note is printed to stderr.

## What you have now

| Command | What it did |
|---|---|
| `nxstate doctor` | Confirmed host, credentials, and transport reachability |
| `nxstate system version --json` | Pulled structured version facts as JSON |
| `nxstate interface list --format tsv` | Listed all interfaces as tab-separated rows |

## A few more commands to try

```bash
# Project specific fields with --select (dot-path, comma-separated)
nxstate system version --json --select nxos_ver_str,host_name

# VLAN table — JSON piped to jq
nxstate vlan list --json | jq '.[].vlanshowbr-vlanname'

# ARP table as TSV
nxstate arp list --format tsv

# Generic show passthrough — any read command; non-read input is refused
nxstate show "show ip ospf neighbors"

# Limit a long list
nxstate route list --vrf default --limit 20
```

The `show` passthrough validates your input before connecting. If you pass anything that is not a read command (for example `configure terminal`, `write memory`, or `reload`) it is refused with exit code `11` (`WRITE_REFUSED`) and no connection is made.

## Next steps

- [Authentication](/guides/authentication/) — OS keyring, `--password-stdin`, `auth login`
- [Inventory and fan-out](/guides/inventory-and-fanout/) — define hosts, target groups, run concurrently across a fleet
- [Output and filtering](/guides/output-and-filtering/) — `--format`, `--select`, `--limit`, piping to `jq`
- [Gathering state](/guides/gathering-state/) — full command reference for every curated `show` mapping
- [Global flags reference](/reference/global-flags/) — every flag, what it does, and its default
