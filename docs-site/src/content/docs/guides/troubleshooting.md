---
title: Troubleshooting
description: Diagnose and fix common nxstate errors by exit code, from missing credentials to unreachable switches.
owner: rnwolfe
lastReviewed: 2026-06-23
---

Something went wrong. Start here.

## Start with `nxstate doctor`

`doctor` is the first thing to run when a command fails. It probes three conditions —
host present, credentials present, reachability — and tells you exactly which check
failed and why.

```bash
nxstate doctor --host sw1 --username netops
```

```json
{
  "ok": false,
  "checks": [
    { "name": "host",        "ok": true,  "detail": "sw1" },
    { "name": "credentials", "ok": false, "detail": "set --username + NXSTATE_PASSWORD (or nxstate auth login)" },
    { "name": "reachable",   "ok": false, "detail": "skipped (need host + credentials)" }
  ]
}
```

Fix each failing check from top to bottom. Once `"ok": true`, the device is ready.

For inventory-based targets, run doctor across a group:

```bash
nxstate doctor --group core
```

Each device emits a separate NDJSON line. Exit code 9 if any check fails.

---

## Common errors by code

### HOST_REQUIRED — exit 2

```
error: no target switch given
  code: HOST_REQUIRED
  fix:  pass --host <switch> (and credentials via --username + NXSTATE_PASSWORD / --password-stdin)
```

You ran a command without telling nxstate which switch to connect to. There are three
ways to supply the target:

| Method | Example |
|--------|---------|
| Flag | `nxstate --host 10.0.0.1 system version` |
| Environment variable | `export NXSTATE_HOST=sw1` |
| Inventory targeting | `nxstate --device sw1 system version` |

See [Inventory & fan-out](/guides/inventory-and-fanout/) for the full targeting
model.

---

### AUTH_REQUIRED — exit 4

```
error: authentication failed: NX-OS SSH rejected the credentials
  code: AUTH_REQUIRED
  fix:  run: nxstate auth login --host <switch> --username <user>
```

The switch refused the login. Passwords are **never** accepted on the command line.
nxstate resolves credentials in this order:

1. `--password-stdin` — pipe a password to stdin
2. `NXSTATE_PASSWORD` environment variable
3. OS keyring (stored with `nxstate auth login`)
4. Interactive prompt (TTY only; blocked by `--no-input`)

Quick fix — export the password for the session:

```bash
export NXSTATE_PASSWORD=mypassword
nxstate system version --host sw1 --username netops
```

For long-term use, store it in the keyring (see [Authentication](/guides/authentication/)):

```bash
nxstate auth login --host sw1 --username netops
```

Check what credentials nxstate currently sees:

```bash
nxstate auth status --host sw1 --username netops
```

If `"credential_present": false`, nxstate has no password for that device.

**Wrong username or password?** Verify you can SSH directly:

```bash
ssh netops@sw1
```

**Least-privilege tip:** use a `network-operator` account (read-only role). See
[Authentication](/guides/authentication/) for RBAC notes.

---

### UNREACHABLE — exit 9

```
error: sw1 is not reachable: Connection refused
  code: UNREACHABLE
  fix:  check connectivity, --transport, --port, and credentials (nxstate doctor --host ...)
```

nxstate cannot open a connection to the switch. Work through the checklist:

1. **Ping the host** — confirm basic IP reachability from your machine.
2. **Check the transport** — nxstate defaults to `--transport auto` (probe NX-API on
   port 443, then fall back to SSH on port 22). Force a specific transport to narrow
   the problem:

   ```bash
   # Try SSH explicitly
   nxstate --host sw1 --username netops --transport ssh system version

   # Try NX-API explicitly
   nxstate --host sw1 --username netops --transport nxapi system version
   ```

3. **Check the port** — if SSH runs on a non-standard port, pass `--port`:

   ```bash
   nxstate --host sw1 --port 2222 --transport ssh system version
   ```

4. **NX-API TLS errors** — see [NX-API self-signed certs](#nx-api-self-signed-certs)
   below.

5. **Firewall** — ensure TCP 22 (SSH) or TCP 443 (NX-API) is permitted from your
   source to the device management interface.

---

### DEVICE_ERROR — exit 1

```
error: 'show ip ospf neighbors': % OSPF feature is disabled
  code: DEVICE_ERROR
  fix:  verify the command exists on this platform/version and the feature is enabled
```

The switch accepted the connection but returned an error for the command itself. Common
causes:

- **Feature not enabled.** NX-OS features are opt-in. Check with:

  ```bash
  nxstate show "show feature" --host sw1 --username netops
  ```

  If the feature is off, a network operator can enable it — but nxstate is
  read-only; it cannot enable features itself.

- **Command not supported on this NX-OS version.** Some `show` commands were introduced
  in specific NX-OS releases. Consult Cisco's command reference for your version.

- **Wrong VRF.** Route and BGP commands scope to the default VRF by default. Pass
  `--vrf` to target another:

  ```bash
  nxstate route list --vrf management --host sw1 --username netops
  ```

- **Interface name typo.** For `interface show`, the name must match exactly
  (e.g. `Ethernet1/1`, not `eth1/1`):

  ```bash
  nxstate interface show Ethernet1/1 --host sw1 --username netops
  ```

---

### PARSE_UNAVAILABLE — exit 14

```
error: no structured parser available for this command
  code: PARSE_UNAVAILABLE
```

nxstate tried all available parsers — NX-API JSON, `| json`, Genie, ntc-templates —
and none produced structured data. The raw device text is returned as a fenced
`raw` field instead.

**To get more parsers, install the Genie extra:**

```bash
uv tool install "nxstate[genie]"
# or
pip install "nxstate[genie]"
```

This adds Genie (PyATS) with ~293 NX-OS parsers, covering commands that ntc-templates
does not handle. See [Transports & parsing](/concepts/transports-and-parsing/) for
the full parsing pipeline.

If Genie is installed and parsing still fails, the output is genuinely unstructured for
that command. Use the generic passthrough and inspect the raw text:

```bash
nxstate show "show ip pim neighbor" --host sw1 --username netops
```

---

### WRITE_REFUSED — exit 11

```
error: refused non-read command: 'conf t' (only 'show ...' read commands are permitted)
  code: WRITE_REFUSED
  fix:  nxstate is read-only; only 'show ...' commands are permitted (no conf t / mutations)
```

You (or a script) passed a command that would mutate the device. nxstate is
**read-only by design** — this is not a permission toggle. There is no
`--allow-mutations` flag. The check happens before any connection is made.

The `show` passthrough only accepts commands whose first token is `show`. The following
leaders are always blocked regardless of context:

`conf`, `configure`, `write`, `wr`, `copy`, `reload`, `boot`, `install`, `clear`,
`no`, `set`, `delete`, `erase`, `format`, `reset`, `shutdown`, `switchto`, `attach`,
`vsh`, `run`, `python`, `bash`, `guestshell`, `feature`

If you need to gather state from a `show` command that is not already a built-in
subcommand, use the passthrough:

```bash
nxstate show "show ip ospf neighbors detail" --host sw1 --username netops
```

Multi-line or newline-separated input is also refused. See
[Read-only safety](/concepts/read-only-safety/) for the full design rationale.

---

### DEBUG_BLOCKED and TECH_BLOCKED — exit 6

```
error: debug command 'debug ip routing' is control-plane-impacting and is gated
  code: DEBUG_BLOCKED
  fix:  re-run with --allow-debug if you accept the control-plane load
```

```
error: show tech-support is large and slow and is gated
  code: TECH_BLOCKED
  fix:  re-run with --allow-tech (expect a long, text-only capture)
```

These two gates protect you from accidentally running commands that can impact a live
switch:

- `debug ...` commands load the supervisor CPU. Unlock with `--allow-debug`:

  ```bash
  nxstate debug "ip routing" --allow-debug --host sw1 --username netops
  ```

- `tech-support` generates a very large text capture and can take minutes. Unlock
  with `--allow-tech`:

  ```bash
  nxstate tech-support --allow-tech --host sw1 --username netops
  ```

Use both flags deliberately and in maintenance windows on production switches.

---

## NX-API self-signed certs

NX-OS ships with a self-signed HTTPS certificate on the NX-API endpoint. When
`--transport auto` (or `--transport nxapi`) tries to connect, Python's TLS
verification rejects it:

```
UNREACHABLE: ssl.SSLCertVerificationError: certificate verify failed: self-signed certificate
```

Pass `--insecure` to skip TLS verification for NX-API:

```bash
nxstate --host sw1 --username netops --insecure system version
```

`--insecure` only affects NX-API connections; SSH transport is unaffected (scrapli uses
`auth_strict_key=False` for SSH host keys). If you would rather not use `--insecure`,
force SSH transport instead:

```bash
nxstate --host sw1 --username netops --transport ssh system version
```

You can also set `insecure: true` per-host in your
[inventory file](/reference/inventory-schema/) to avoid repeating the flag.

---

## Keyring on headless Linux

On a headless Linux server (no GUI, no desktop session), the `keyring` library has no
default backend, so `nxstate auth login` fails with a CONFIG error:

```
error: could not store credential: No recommended backend was available.
  code: KEYRING_UNAVAILABLE
  fix:  use NXSTATE_PASSWORD / --password-stdin instead, or install a keyring backend
```

There are two straightforward workarounds:

**Option 1 — Use the environment variable (simplest):**

```bash
export NXSTATE_PASSWORD=mypassword
nxstate system version --host sw1 --username netops
```

For automation, inject the password from a secrets manager rather than hard-coding it.

**Option 2 — Install a headless keyring backend:**

[`keyrings.alt`](https://pypi.org/project/keyrings.alt/) provides a file-based
backend that works without a desktop session:

```bash
pip install keyrings.alt
```

After installation, `nxstate auth login` stores the credential in an encrypted file
under `~/.local/share/keyrings/`. Re-run `nxstate auth login` once, then normal
keyring lookups will work.

---

## Choosing a transport

nxstate supports three transport modes, selectable with `--transport`:

| Mode | What it does | When to use |
|------|-------------|-------------|
| `auto` *(default)* | Probes NX-API (HTTPS/443) first; falls back to SSH if unavailable | Most environments |
| `nxapi` | NX-API only; fails if NX-API is unreachable | NX-API confirmed enabled; fastest |
| `ssh` | SSH only via scrapli | NX-API disabled or blocked; air-gapped management plane |

**NX-API must be explicitly enabled on NX-OS:**

```
# On the switch (not with nxstate — it is read-only):
feature nxapi
```

If you are unsure whether NX-API is running, force SSH to skip the probe:

```bash
nxstate --transport ssh --host sw1 --username netops system version
```

Structured JSON output is available over both transports. SSH appends `| json` to each
`show` command; NX-API uses the `cli_show` JSON endpoint directly. When neither
produces structured data, nxstate falls through to Genie, ntc-templates, and finally
raw text. See [Transports & parsing](/concepts/transports-and-parsing/) for details.

---

## Still stuck?

- Run `nxstate schema` for the full machine-readable command tree and exit code table.
- Run `nxstate --help` or `nxstate <subcommand> --help` for flag reference.
- Check [Global flags](/reference/global-flags/) for all connection and output options.
- Check [Exit codes](/reference/exit-codes/) for the authoritative code table.
- Check [Environment variables](/reference/environment-variables/) if you suspect an
  env var is overriding a flag.
