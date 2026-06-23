---
title: Authentication & credentials
description: How nxstate resolves connection settings and passwords, how to store credentials in the OS keyring, and how to configure RBAC for safe read-only access.
owner: rnwolfe
lastReviewed: 2026-06-23
---

nxstate needs to reach a switch and prove who it is. This guide covers the full
resolution chain for connection settings (host, username, transport, port) and the
separate—stricter—chain for passwords, plus OS keyring storage, NX-API TLS, and the
right RBAC role to create on the device.

## Connection settings resolution

Every setting that describes _how_ to reach a device follows the same four-level precedence.
The first source that provides a value wins; later sources are not consulted.

| Priority | Source | Example |
|---|---|---|
| 1 (highest) | CLI flag | `--host 10.0.0.1 --username netops` |
| 2 | Inventory entry | `hosts.leaf1.username: netops` |
| 3 | Environment variable | `NXSTATE_HOST=10.0.0.1` |
| 4 (lowest) | Built-in default | transport → `auto`, timeout → 30 s |

The settings resolved this way are: `host`, `username`, `transport`, `port`, `insecure`, and `timeout`.

A minimal one-liner using only flags and an env-var password:

```bash
nxstate --host 10.0.0.1 --username netops system version
```

The same target expressed with env vars (useful in CI or containers):

```bash
export NXSTATE_HOST=10.0.0.1
export NXSTATE_USERNAME=netops
export NXSTATE_PASSWORD=hunter2          # see password section below
nxstate system version
```

The full list of recognized environment variables is documented in
[Environment variables](/reference/environment-variables/).
Inventory-based targeting is covered in [Inventory & fan-out](/guides/inventory-and-fanout/).

## Password resolution

Passwords receive special handling because **argv is never a safe place for secrets** — it is
visible via `ps`, `/proc`, and shell history to any process on the same machine. nxstate
enforces this: there is no `--password` flag. The four sources below are tried in order; the
first non-empty result is used.

### 1. `--password-stdin`

Pipe the password to stdin. Nothing is stored, nothing touches the environment.

```bash
echo "hunter2" | nxstate --host 10.0.0.1 --username netops --password-stdin system version
# or from a secret manager:
vault read -field=password secret/nexus/sw1 | \
  nxstate --host 10.0.0.1 --username netops --password-stdin system version
```

This is the right choice for automated pipelines where a secret manager or CI secret
injection is available.

### 2. `NXSTATE_PASSWORD` environment variable

Set the variable in your shell session or script. It is consumed at connection time and
never written anywhere.

```bash
export NXSTATE_PASSWORD="hunter2"
nxstate system version
```

For short interactive sessions this is convenient, but be aware that environment variables
can be visible to other processes running as the same user.

### 3. OS keyring (`nxstate auth login`)

nxstate integrates with the native credential store on each platform:

- **macOS** — Keychain
- **Linux** — libsecret / GNOME Keyring / KWallet (via the `keyring` library)
- **Windows** — Windows Credential Manager

Credentials are keyed `user@host`, so you can store separate passwords for every switch.
They are never written to a file on disk that you might accidentally commit.

Store a password for one device:

```bash
nxstate auth login --host 10.0.0.1 --username netops
# prompts: NX-OS password: (input hidden)
```

Verify the stored credential (does not make a network connection):

```bash
nxstate auth status --host 10.0.0.1 --username netops
```

```json
{
  "host": "10.0.0.1",
  "username": "netops",
  "transport": "auto",
  "credential_present": true,
  "note": "credentials read from NXSTATE_PASSWORD / --password-stdin / keyring (never argv)"
}
```

Remove a stored credential:

```bash
nxstate auth logout --host 10.0.0.1 --username netops
```

`auth login` requires exactly one target. Pass `--host` (ad-hoc) or `--device` (inventory
name) — not both. Inventory-managed devices can still use keyring storage; the resolved `host`
and `username` from the inventory entry determine the keyring key.

If no keyring backend is available (headless server without libsecret), `auth login` will
raise `KEYRING_UNAVAILABLE` (exit 10) and suggest using `NXSTATE_PASSWORD` or
`--password-stdin` instead.

### 4. Interactive prompt (TTY only)

If no password is found from the three sources above and a TTY is attached, nxstate prompts
interactively (hidden input via `getpass`). This is the "just try it" experience for ad-hoc
use.

If you need to suppress this prompt in scripts—to get a clear failure rather than a hang—pass
`--no-input`. nxstate will then raise `INPUT_REQUIRED` (exit 13) instead of waiting.

```bash
# Safe in scripts: fails immediately rather than hanging on a prompt
nxstate --host 10.0.0.1 --username netops --no-input system version
```

## Checking connectivity and credentials with `doctor`

`nxstate doctor` probes host, credentials, and reachability in one shot. Run it after
setting up any new target to confirm everything is wired correctly before writing automation
around it.

```bash
nxstate doctor --host 10.0.0.1 --username netops
```

```json
{
  "ok": true,
  "checks": [
    {"name": "host",        "ok": true, "detail": "10.0.0.1"},
    {"name": "credentials", "ok": true, "detail": "present"},
    {"name": "reachable (auto)", "ok": true, "detail": "ok via nxapi"}
  ]
}
```

A failed credential check looks like:

```json
{"name": "credentials", "ok": false, "detail": "set --username + NXSTATE_PASSWORD (or nxstate auth login)"}
```

Exit code 9 (`unreachable`) if any check fails. See [Exit codes](/reference/exit-codes/) for
the full table.

## NX-API and TLS (`--insecure`)

By default nxstate uses **`--transport auto`**: it probes NX-API (HTTPS POST to `/ins` on port
443) first, and falls back to SSH if NX-API is unreachable or disabled. You can pin a
transport with `--transport nxapi` or `--transport ssh`.

NX-API on most NX-OS devices ships with a **self-signed certificate**. TLS verification is
enabled by default, so the first attempt will fail until you do one of:

- **Install a valid device certificate** (recommended for production). Once in place, TLS
  verification works without any flags.
- **Pass `--insecure`** to skip TLS verification for self-signed certs. This is fine on a
  trusted management network but disables certificate-identity assurance.

```bash
# One-off with an untrusted cert
nxstate --host 10.0.0.1 --username netops --insecure system version

# Persistent per host via inventory:
#   hosts:
#     leaf1:
#       host: 10.0.0.1
#       insecure: true
```

`--insecure` only affects NX-API. SSH host-key verification is handled by scrapli with
`auth_strict_key: false` (the default) — appropriate for lab/test environments where host
keys are frequently regenerated; tighten this for production SSH by filing a feature request
or using NX-API with a real certificate instead.

## RBAC: least-privilege account

Always connect with the least-privilege role that can do the job. nxstate is read-only, so
the right NX-OS role is **`network-operator`**.

Create a dedicated account on the device:

```
username netops password <password> role network-operator
```

One important caveat: the stock `network-operator` role on NX-OS cannot read
`show running-config` or `show startup-config`. If you need those commands you must create a
custom read-only role that adds those privileges — but the account still has no configuration
rights.

```
! Example custom role (still read-only)
role name nxstate-reader
  rule 10 permit read-write feature show running-config
username netops role nxstate-reader
```

A `network-operator` account connecting via NX-API uses HTTP Basic auth; the credentials
travel over the HTTPS connection (TLS in transit). SSH uses password auth over the encrypted
channel. Neither path stores credentials on the device beyond the normal NX-OS password hash.

## Non-interactive and CI usage

For pipelines where no TTY is attached:

```bash
# Method A: pass via env (common in CI secret injection)
NXSTATE_HOST=10.0.0.1 \
NXSTATE_USERNAME=netops \
NXSTATE_PASSWORD="$SECRET" \
nxstate --no-input --json interface list

# Method B: pipe from a secret manager
vault read -field=password secret/nexus/sw1 \
  | nxstate --host 10.0.0.1 --username netops --no-input --password-stdin interface list
```

Always combine `--no-input` with CI runs to prevent the process from hanging on a terminal
prompt that will never appear.

## Summary

```
Password:  --password-stdin  →  NXSTATE_PASSWORD  →  OS keyring  →  TTY prompt
Settings:  --flag            →  inventory          →  env var     →  built-in default
```

- Passwords are **never on argv**.
- The inventory file holds **no secrets** — only hosts, usernames, and topology.
- Use `nxstate auth login` for interactive use; `NXSTATE_PASSWORD` or `--password-stdin` for
  automation.
- Use `--insecure` only on trusted management networks when you cannot install a valid
  device certificate.
- Connect with a `network-operator` (or equivalent custom read-only) account.

Related pages: [Global flags](/reference/global-flags/) · [Inventory & fan-out](/guides/inventory-and-fanout/) · [Troubleshooting](/guides/troubleshooting/) · [Exit codes](/reference/exit-codes/)
