---
title: Environment variables
description: Every NXSTATE_* variable nxstate reads, with their resolution order and security guidance.
owner: rnwolfe
lastReviewed: 2026-06-23
---

nxstate reads a small set of environment variables so credentials and connection defaults can
be wired in once — in a shell profile, a `.env` file, or a CI secret — without repeating them
on every command. Every variable is optional; a flag always wins over an env var, and an env var
always wins over a built-in default.

For the full resolution chain that governs how values are merged see
[Authentication](/guides/authentication/) and [Inventory and fan-out](/guides/inventory-and-fanout/).

---

## Connection variables

### `NXSTATE_HOST`

The hostname or IP address of the target switch. Equivalent to `--host`.

```bash
export NXSTATE_HOST=10.0.0.1
nxstate system version          # no --host needed
```

When an inventory file is active (`--device`, `--group`, or `--all`), this variable is
ignored — the target list comes from the inventory.

---

### `NXSTATE_USERNAME`

The login username for the target switch. Equivalent to `--username` / `-u`.

```bash
export NXSTATE_USERNAME=network-operator
```

nxstate recommends a least-privilege `network-operator` (read-only) account; see
[Authentication](/guides/authentication/) for RBAC notes.

---

### `NXSTATE_TRANSPORT`

Preferred transport method. Accepted values: `auto`, `ssh`, `nxapi`. Equivalent to
`--transport`. Defaults to `auto` when unset.

```bash
export NXSTATE_TRANSPORT=nxapi
```

With `auto`, nxstate probes NX-API first and falls back to SSH if NX-API is unavailable or
returns an error. See [Transports and parsing](/concepts/transports-and-parsing/) for a full
description of both paths.

---

### `NXSTATE_PORT`

Override the port used for the chosen transport. Equivalent to `--port`.

| Transport | Built-in default |
|-----------|-----------------|
| `nxapi`   | 443             |
| `ssh`     | 22              |

```bash
export NXSTATE_PORT=8443    # NX-API on a non-standard HTTPS port
```

Leave unset to use the per-transport defaults listed above.

---

## Password variable

### `NXSTATE_PASSWORD`

The device password used when connecting. This is **the only supported way to supply a
password non-interactively that is not tied to the OS keyring or `--password-stdin`**.

```bash
export NXSTATE_PASSWORD=my-secret
nxstate system version --host 10.0.0.1 --username network-operator
```

**Passwords are never accepted on the command line (no `--password` flag).** This is an
intentional security boundary: argv is visible in `ps`, shell history, and container
inspection. The three supported channels are:

| Channel | How |
|---------|-----|
| `--password-stdin` | Pipe or redirect: `echo $PW \| nxstate ...` |
| `NXSTATE_PASSWORD` | Set in environment; cleared after process exits |
| OS keyring | Stored via `nxstate auth login`; keyed by `user@host` |

**Resolution order (first match wins):**

1. `--password-stdin` — reads one line from stdin
2. `NXSTATE_PASSWORD` env var
3. OS keyring (`nxstate` service, key `<username>@<host>`)
4. Interactive prompt — only when a TTY is attached and `--no-input` is not set

#### Security guidance

`NXSTATE_PASSWORD` is convenient for CI pipelines and scripts, but the OS keyring is
preferable for interactive sessions because:

- Keyring entries survive shell sessions without leaving credentials in shell history or
  process lists.
- A single `nxstate auth login` stores the credential once per `user@host` pair.
- On headless systems without a keyring backend, `NXSTATE_PASSWORD` or `--password-stdin`
  are the right fallbacks.

When the env var is present it takes precedence over the keyring, so CI secrets set in
`NXSTATE_PASSWORD` always win — there is no risk of a stale keyring entry interfering with
automation.

See [Authentication](/guides/authentication/) for the full credential lifecycle.

---

## Inventory variable

### `NXSTATE_INVENTORY`

Path to the inventory YAML file. Equivalent to `--inventory`. Defaults to
`~/.config/nxstate/inventory.yaml` (or `$XDG_CONFIG_HOME/nxstate/inventory.yaml` when
`XDG_CONFIG_HOME` is set).

```bash
export NXSTATE_INVENTORY=/etc/nxstate/prod-inventory.yaml
nxstate interface list --all
```

The inventory file contains hosts, groups, and defaults — **no passwords**. Credentials are
always resolved at connection time from the channels described above.

See [Inventory schema](/reference/inventory-schema/) for the file format and
[Inventory and fan-out](/guides/inventory-and-fanout/) for targeting flags.

---

## Display variable

### `NO_COLOR`

Set to any non-empty value to disable colored output. This is the [no-color.org](https://no-color.org)
standard, honored by many CLI tools. nxstate also accepts `--no-color` as a flag.

```bash
export NO_COLOR=1
nxstate interface list --host 10.0.0.1 --username network-operator
```

Color is only applied to `--format plain` output on a TTY. JSON and TSV output is never
colored, regardless of this variable.

---

## Resolution precedence summary

The table below shows the full resolution chain for each setting, from highest to lowest
priority. The first non-empty value wins.

| Setting    | 1st: Flag          | 2nd: Inventory | 3rd: Env var          | 4th: Default |
|------------|--------------------|----------------|-----------------------|--------------|
| host       | `--host`           | host entry     | `NXSTATE_HOST`        | —            |
| username   | `--username` / `-u`| host entry     | `NXSTATE_USERNAME`    | —            |
| transport  | `--transport`      | host entry     | `NXSTATE_TRANSPORT`   | `auto`       |
| port       | `--port`           | host entry     | `NXSTATE_PORT`        | 443 / 22     |
| password   | `--password-stdin` | *(never)*      | `NXSTATE_PASSWORD`    | keyring → prompt |
| inventory  | `--inventory`      | *(n/a)*        | `NXSTATE_INVENTORY`   | `~/.config/nxstate/inventory.yaml` |

Notes:

- **Passwords never appear in inventory files.** The inventory column for password is always
  skipped; the env var and keyring are the only non-interactive paths.
- When no inventory targeting flag is present (`--device`, `--group`, `--all`), the inventory
  file is not loaded and `NXSTATE_INVENTORY` has no effect.
- A flag beats the inventory, which beats the env var, which beats the default. This means
  you can set organization-wide defaults in environment variables and override them per-run
  with flags — the typical CI / local-dev pattern.

---

## Quick-start snippet

Below is a minimal shell setup that lets you run nxstate against a single switch without
flags:

```bash
export NXSTATE_HOST=10.0.0.1
export NXSTATE_USERNAME=network-operator
export NXSTATE_PASSWORD=changeme   # or: nxstate auth login --host 10.0.0.1 -u network-operator

nxstate system version
nxstate interface list
nxstate vlan list
```

For multi-device workflows, drop the per-host variables and use an inventory file instead:

```bash
export NXSTATE_INVENTORY=~/infra/nxstate-inventory.yaml
nxstate interface list --group datacenter-core
```

See [Inventory and fan-out](/guides/inventory-and-fanout/) for the inventory file format and
concurrent fan-out behavior.

---

## Related pages

- [Authentication](/guides/authentication/) — keyring setup, `auth login`, RBAC
- [Inventory and fan-out](/guides/inventory-and-fanout/) — inventory file format, targeting, concurrent runs
- [Global flags](/reference/global-flags/) — flag-level overrides for every variable above
- [Troubleshooting](/guides/troubleshooting/) — diagnosing credential and connectivity issues
