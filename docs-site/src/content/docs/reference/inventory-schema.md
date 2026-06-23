---
title: Inventory file schema
description: Exhaustive reference for every field in the nxstate inventory YAML, including inheritance rules, glob matching, and the no-secrets contract.
owner: rnwolfe
lastReviewed: 2026-06-23
---

The inventory file is a single YAML document that lets you name, group, and configure every Nexus switch nxstate manages. This page is the field-by-field reference. For a narrative introduction and fan-out usage examples, see [Inventory & multi-device fan-out](/guides/inventory-and-fanout/).

## File location

nxstate resolves the inventory path in this order:

1. The `--inventory PATH` flag (highest priority)
2. The `NXSTATE_INVENTORY` environment variable
3. `$XDG_CONFIG_HOME/nxstate/inventory.yaml` (if `XDG_CONFIG_HOME` is set)
4. `~/.config/nxstate/inventory.yaml` (default)

If the file does not exist when you use `--device`, `--group`, or `--all`, nxstate exits with code 10 (`config_error`) and prints the path it looked for.

## Top-level structure

```yaml
defaults:   # <inheritable-keys>     optional
groups:     # map of group-name → <inheritable-keys>   optional
hosts:      # map of host-name → <host-definition>     required for inventory use
```

All three keys are optional in the file, but `hosts` must be present (and non-empty) for any inventory-based targeting to return results.

## Inheritable keys

The following keys may appear at any level — `defaults`, a named entry under `groups`, or a named entry under `hosts`. When the same key appears at multiple levels, the [resolution rules](#resolution-semantics) determine which value wins.

| Key | Type | Description | Default |
|---|---|---|---|
| `host` | string | Hostname or IP address to connect to. If omitted from a host entry, the inventory name (the map key under `hosts`) is used as-is. | inventory name |
| `username` | string | Login username. | — |
| `transport` | string | `auto`, `ssh`, or `nxapi`. `auto` probes NX-API first and falls back to SSH. | `auto` |
| `port` | integer | TCP port to connect to. nxstate picks the right default per transport: 22 for SSH, 443 for NX-API. | transport default |
| `insecure` | boolean | Skip TLS certificate verification. Applies to NX-API only; has no effect on SSH. Set `true` for self-signed NX-API certificates, which are common in lab environments. | `false` |
| `timeout` | integer | Per-command timeout in seconds. | `30` |

No other keys are recognized. Unknown keys are silently ignored.

## `defaults` section

A single map of [inheritable keys](#inheritable-keys). Values here become the base for every host in the file.

```yaml
defaults:
  username: netops
  transport: auto
```

## `groups` section

A map of group names to maps of [inheritable keys](#inheritable-keys). A group entry may be empty (`{}`), which is valid — it still exists as a named group that hosts can reference.

```yaml
groups:
  datacenter:
    transport: nxapi
    insecure: true
  edge: {}
```

Groups have no hierarchy. A group entry cannot list `groups:` itself — only host entries do.

## `hosts` section

A map of host names to host definitions. The map key (e.g. `leaf1`) is the inventory name: it is used for targeting with `--device`, for display in fan-out output, and as the `host` value if none is explicitly set.

### Host definition

```yaml
hosts:
  <name>:
    groups: [<group-name>, ...]   # optional list of group names
    host: <string>                # optional, overrides the map key
    username: <string>            # optional
    transport: <string>           # optional
    port: <integer>               # optional
    insecure: <boolean>           # optional
    timeout: <integer>            # optional
```

The `groups` key is special: it is a list of group names (strings) and is **not** an inheritable key — it is only valid on a host entry. All other keys under a host entry are inheritable keys and follow the normal resolution rules.

A host may belong to multiple groups. Groups are applied in list order (left to right), each one overlaying the previous.

## Resolution semantics

Settings are computed per host using a three-level merge. The rule is:

```
effective = defaults ← groups (in order) ← host
```

In plain terms:

1. Start from `defaults` (all inheritable keys defined there).
2. For each group listed in the host's `groups:`, apply that group's keys in order — later groups in the list overwrite earlier ones for the same key.
3. Apply the host's own keys (excluding `groups:`). Host-level values always win.
4. If `host` is still unset after step 3, it is set to the inventory name.

A CLI flag (`--host`, `--username`, `--transport`, etc.) always overrides the effective inventory value. See [Authentication](/guides/authentication/) for the full four-level precedence including environment variables.

### Worked example

Given this inventory:

```yaml
defaults:
  username: netops
  transport: auto

groups:
  datacenter:
    transport: nxapi
    insecure: true
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
    username: edge-ro
```

Effective settings for each host:

**`leaf1`**

| Step | username | transport | insecure | host |
|---|---|---|---|---|
| defaults | netops | auto | — | — |
| + datacenter | netops | nxapi | true | — |
| + host keys | netops | nxapi | true | 10.1.1.11 |

**`edge1`**

| Step | username | transport | insecure | host |
|---|---|---|---|---|
| defaults | netops | auto | — | — |
| + edge (empty) | netops | auto | — | — |
| + host keys | **edge-ro** | auto | — | edge1.example.net |

The host-level `username: edge-ro` overrides the default. Passing `--username admin --device edge1` on the command line would override it further to `admin`.

## Targeting

The inventory is only consulted when you use `--device`, `--group`, or `--all`. `--host` is an ad-hoc flag that bypasses the inventory entirely.

### `--device NAME` (glob, repeatable)

Matches inventory host names using Python `fnmatch` glob rules:

- `*` matches any sequence of characters (including none).
- `?` matches exactly one character.
- `[seq]` matches any character in `seq`.
- Matching is case-sensitive on all platforms.

```bash
# exact name
nxstate --device leaf1 vlan list

# all names starting with "leaf"
nxstate --device 'leaf*' vlan list

# combine with another device
nxstate --device 'leaf*' --device edge1 system version
```

If a pattern matches no host name in the inventory, nxstate exits with code 5 (`not_found`) before opening any connection.

### `--group NAME` (repeatable)

Selects all hosts whose `groups:` list contains the named group. Results from multiple `--group` flags are unioned and de-duplicated.

```bash
nxstate --group datacenter bgp summary
nxstate --group datacenter --group edge system version
```

If the group name is not referenced by any host, nxstate exits with code 5 (`not_found`).

### `--all`

Targets every host defined under `hosts`. Equivalent to `--device '*'` but more explicit.

```bash
nxstate --all system version
```

### De-duplication and ordering

When multiple targeting flags resolve the same host (e.g. `--device leaf1 --group datacenter` where `leaf1` is in `datacenter`), it appears in the result once. The final target list is sorted by inventory name before any connections are made.

## No-secrets rule

**Passwords must never appear in the inventory file.** The inventory is committed to version control, stored at a well-known path, and readable by any process running as the same user — none of which are safe for credentials.

Passwords are resolved at connection time from a separate chain:

```
--password-stdin  →  NXSTATE_PASSWORD  →  OS keyring  →  TTY prompt
```

See [Authentication](/guides/authentication/) for full details on each source.

The only credential-adjacent fields the inventory accepts are `username` (which is not a secret) and `host`/`port` (network addresses). No `password:`, `secret:`, or `token:` key is recognized.

## Complete example

```yaml
# ~/.config/nxstate/inventory.yaml
#
# NO SECRETS HERE. Passwords come from NXSTATE_PASSWORD, --password-stdin,
# or the OS keyring (nxstate auth login).

defaults:
  username: netops
  transport: auto        # auto | ssh | nxapi

groups:
  datacenter:
    transport: nxapi
    insecure: true       # self-signed NX-API TLS certs
  edge: {}
  lab:
    transport: ssh
    timeout: 60          # slower out-of-band path

hosts:
  leaf1:
    host: 10.1.1.11
    groups: [datacenter]

  leaf2:
    host: 10.1.1.12
    groups: [datacenter]

  spine1:
    host: 10.1.0.1
    groups: [datacenter]
    username: spine-ro   # override: dedicated read account on spines

  edge1:
    host: edge1.example.net
    groups: [edge]
    username: edge-ro

  lab-n9k:
    host: 192.168.99.10
    groups: [lab]
    # transport: ssh from the lab group; timeout: 60 from the lab group
    # no groups key overrides username, so it falls through to defaults: netops
```

## Related pages

- [Inventory & multi-device fan-out](/guides/inventory-and-fanout/) — tutorial with fan-out examples and NDJSON output
- [Authentication](/guides/authentication/) — password resolution order, keyring setup, NX-API TLS
- [Environment variables](/reference/environment-variables/) — `NXSTATE_INVENTORY`, `NXSTATE_HOST`, `NXSTATE_USERNAME`, and others
- [Global flags](/reference/global-flags/) — `--device`, `--group`, `--all`, `--inventory`, `--workers`
- [Exit codes](/reference/exit-codes/) — full exit-code table including code 5 (`not_found`) and code 10 (`config_error`)
- [Troubleshooting](/guides/troubleshooting/) — diagnosing inventory and connectivity issues
