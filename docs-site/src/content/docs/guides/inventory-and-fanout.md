---
title: Inventory & multi-device fan-out
description: Manage a fleet of Nexus switches with a single YAML inventory and run any read command across all of them at once.
owner: rnwolfe
lastReviewed: 2026-06-23
---

Running a command against one switch is useful. Running the same command across every spine and leaf in your fabric — concurrently, with one line — is what makes nxstate valuable at scale. This guide covers the inventory file, how settings are inherited, how to target devices, and what the concurrent fan-out output looks like.

## The inventory file

nxstate looks for a [Nornir](https://nornir.readthedocs.io/)-flavored YAML file at:

```bash
~/.config/nxstate/inventory.yaml
```

You can override that location with a flag or an environment variable:

```bash
# flag — takes effect for this one run
nxstate --inventory /etc/nxstate/prod.yaml interface list --all

# environment variable — applies to every run in this shell session
export NXSTATE_INVENTORY=/etc/nxstate/prod.yaml
nxstate interface list --all
```

If the file does not exist when you use `--device`, `--group`, or `--all`, nxstate exits immediately with code 10 (`config_error`) and tells you where it looked.

The file has three top-level sections: `defaults`, `groups`, and `hosts`. **Passwords are never stored here** — they come from the environment, the OS keyring, or `--password-stdin` at connection time. See [Authentication](/guides/authentication/) for the full credential resolution order.

### A complete example

```yaml
# ~/.config/nxstate/inventory.yaml
#
# No secrets here. Passwords come from NXSTATE_PASSWORD / the OS keyring
# (nxstate auth login) / --password-stdin.

defaults:
  username: netops
  transport: auto       # auto | ssh | nxapi

groups:
  datacenter:
    transport: nxapi
    insecure: true      # self-signed NX-API TLS certs are common in labs
  edge: {}

hosts:
  leaf1:
    host: 10.1.1.11
    groups: [datacenter]
  leaf2:
    host: 10.1.1.12
    groups: [datacenter]
  edge1:
    host: edge1.example.net
    groups: [edge]
    username: edge-ro   # host-level override: different account on this switch
```

### Inheritable keys

The following keys can appear in `defaults`, a `groups` entry, or a `hosts` entry:

| Key | Description |
|---|---|
| `host` | Hostname or IP to connect to (defaults to the inventory name if omitted) |
| `username` | Login username |
| `transport` | `auto`, `ssh`, or `nxapi` |
| `port` | Transport port (nxstate picks the right default per transport) |
| `insecure` | Skip TLS verification for NX-API self-signed certs (`true`/`false`) |
| `timeout` | Per-command timeout in seconds (default 30) |

## How settings are inherited

Resolution follows a simple three-level merge: `defaults` is the base, then each group listed in `groups:` for that host is applied in order, and finally the host's own keys win. The rule is **defaults ← groups ← host (host wins)**.

Working through the example above for `leaf1`:

1. Start with defaults: `{username: netops, transport: auto}`
2. Apply the `datacenter` group: `{username: netops, transport: nxapi, insecure: true}`
3. Apply `leaf1`'s own keys: `{host: "10.1.1.11", username: netops, transport: nxapi, insecure: true}`

For `edge1`, the host-level `username: edge-ro` overrides the default `netops`:

1. Start with defaults: `{username: netops, transport: auto}`
2. Apply the `edge` group (empty `{}`): no change
3. Apply `edge1`'s own keys: `{host: "edge1.example.net", username: edge-ro, transport: auto}`

A CLI flag always wins over everything else. So `--username admin --device edge1` would use `admin` even though the inventory says `edge-ro`.

## Targeting devices

All targeting flags are global — they can go anywhere in the command line, before or after the subcommand.

### By name (with glob support)

`--device` matches inventory host names. Pass it once per name, or use a shell glob:

```bash
# single device by exact name
nxstate --device leaf1 interface list

# two devices explicitly
nxstate --device leaf1 --device leaf2 vlan list

# all hosts whose name starts with "leaf"
nxstate --device 'leaf*' vlan list

# mix glob and explicit name — results are de-duplicated
nxstate --device 'leaf*' --device edge1 system version
```

If a pattern matches no inventory host, nxstate exits with code 5 (`not_found`) before connecting to anything.

### By group

`--group` selects all members of a named group. Repeatable:

```bash
# all datacenter hosts
nxstate --group datacenter bgp summary

# union of two groups
nxstate --group datacenter --group edge system version
```

If the group name does not exist in the inventory, nxstate exits with code 5 (`not_found`).

### All hosts

`--all` targets every host in the inventory:

```bash
nxstate --all system version
```

### Mixing targeting flags

You can combine `--device`, `--group`, and `--all` freely. Results are merged and de-duplicated, then sorted by inventory name before the run begins.

### Ad-hoc without an inventory

If you just want to hit one switch without setting up a file, use `--host` directly:

```bash
nxstate --host 10.1.1.11 --username netops system version
```

`--host` and the inventory targeting flags (`--device`/`--group`/`--all`) serve different purposes: `--host` selects an ad-hoc target without any inventory file, while `--device`/`--group`/`--all` resolve targets from the inventory. When inventory targeting flags are present, the inventory path is used; `--host` is not meaningful in that context and should be omitted.

## Single-device output

When exactly one target resolves, nxstate writes clean structured output to stdout — identical to what you get with `--host`:

```bash
$ nxstate --device leaf1 system version
{
  "nxos_ver_str": "10.3(8)",
  "hostname": "leaf1",
  ...
}
```

## Multi-device fan-out

When more than one target resolves, nxstate runs all devices **concurrently** (using a thread pool) and streams one JSON object to stdout per device as each completes. This is newline-delimited JSON (NDJSON) — one complete JSON object per line, in completion order (not inventory order).

```bash
$ nxstate --group datacenter system version
{"device":"leaf1","host":"10.1.1.11","ok":true,"data":{"nxos_ver_str":"10.3(8)","hostname":"leaf1",...}}
{"device":"leaf2","host":"10.1.1.12","ok":true,"data":{"nxos_ver_str":"10.3(8)","hostname":"leaf2",...}}
```

Each line is a self-contained envelope:

```json
{
  "device": "leaf1",
  "host": "10.1.1.11",
  "ok": true,
  "data": { ... }
}
```

On error, the envelope carries `"ok": false` and a structured `error` object instead of `data`:

```json
{
  "device": "leaf2",
  "host": "10.1.1.12",
  "ok": false,
  "error": {
    "code": "UNREACHABLE",
    "message": "10.1.1.12 is not reachable: connection timed out",
    "remediation": "check connectivity, --transport, --port, and credentials"
  }
}
```

### Per-device error isolation

A failure on one device never interrupts the others. All remaining devices continue to run and emit their results. You always get output for every device that succeeds, regardless of what other devices do.

### Exit code 15 — PARTIAL

After all devices have completed, nxstate exits **0** if every device succeeded, or **15** (`partial`) if at least one device returned an error. This makes it straightforward to detect partial failures in scripts:

```bash
nxstate --all interface list
EXIT=$?

if [ $EXIT -eq 0 ]; then
  echo "All devices OK"
elif [ $EXIT -eq 15 ]; then
  echo "Some devices failed — check the NDJSON output for ok:false lines"
else
  echo "Hard error: $EXIT"
fi
```

See [Exit codes](/reference/exit-codes/) for the full table.

### Controlling concurrency

The default thread-pool size is **10** concurrent devices. Increase or decrease it with `--workers`:

```bash
# run up to 30 devices at once
nxstate --all --workers 30 vlan list

# slow it down for a congested out-of-band network
nxstate --all --workers 2 vlan list
```

There is no enforced upper limit, but practical limits depend on your management network and CPU. For very large fleets, start with the default and increase once you observe stable results.

### Processing NDJSON output

Because each line is valid JSON, standard tools work cleanly:

```bash
# pretty-print with jq, one device at a time
nxstate --all system version | jq .

# extract just the hostname from each device's data
nxstate --all system version | jq -r '.data.hostname // .device + " (failed)"'

# filter to failures only
nxstate --group datacenter interface list | jq 'select(.ok == false)'

# collect all results into a JSON array
nxstate --all system version | jq -s '.'
```

## Running doctor across a fleet

`nxstate doctor` also fans out across multiple targets, emitting per-device NDJSON. This is the fastest way to confirm that every switch in your inventory is reachable with valid credentials before a bulk operation:

```bash
nxstate --all doctor
```

If any device fails the reachability check, the overall exit code is 9 (`unreachable`). The individual check objects in each envelope tell you exactly which step failed — host present, credentials present, or connectivity.

## Related pages

- [Global flags](/reference/global-flags/) — `--device`, `--group`, `--all`, `--inventory`, `--workers` and every other flag
- [Authentication](/guides/authentication/) — password resolution order, keyring setup, `--password-stdin`
- [Output & filtering](/guides/output-and-filtering/) — `--format`, `--select`, `--limit` all apply per-device in fan-out mode
- [Exit codes](/reference/exit-codes/) — full table including exit 15 (`partial`)
- [Inventory schema](/reference/inventory-schema/) — exhaustive YAML field reference
- [Troubleshooting](/guides/troubleshooting/) — debugging connectivity and credential issues
