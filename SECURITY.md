# Security Policy

`nxstate` connects to network devices with real credentials, so security is a first-class
concern. This document covers the threat model, how secrets are handled, and how to report
issues.

## Reporting a vulnerability

**Please do not open public issues for security problems.** Use GitHub's **Private
Vulnerability Reporting** (the "Report a vulnerability" button under the repo's *Security*
tab). Include: affected version (`nxstate version`), repro steps, impact, and any logs (with
secrets redacted — see below).

- Acknowledgement target: within 48 hours.
- We follow coordinated disclosure and will credit reporters who want it.
- For dependency CVEs, please include a reachable proof-of-concept against `nxstate`.

## Supported versions

`nxstate` is pre-1.0; only the latest released version receives fixes.

| Version | Supported |
|---|---|
| latest `0.x` | ✅ |
| older | ❌ |

## Credential & secret handling (threat model)

- **Read-only by design.** `nxstate` has no configuration commands; the `show`/`debug`
  passthrough refuses any non-read input (`WRITE_REFUSED`). It cannot change device state.
- **Passwords are never accepted on the command line** (argv is visible via `ps`/`/proc` and
  shell history). Resolution order: `--password-stdin` → `NXSTATE_PASSWORD` env → OS keyring
  (`nxstate auth login`) → interactive prompt (TTY only).
- **Keyring storage**: credentials stored via `auth login` live in the OS keyring (macOS
  Keychain / libsecret / Windows Credential Manager), keyed `user@host`, never in a repo file.
- **The inventory file contains no secrets** — only hosts, usernames, transport, and group
  membership.
- **NX-API TLS**: `--insecure` disables certificate verification for self-signed NX-API certs.
  Use it only on trusted management networks; prefer installing a valid device certificate.
- **Untrusted device output** (interface descriptions, neighbor names, logging, banners) is
  attacker-influenceable and is **fenced as untrusted** in output so an LLM agent will not
  follow instructions embedded in it.
- **Logs/diagnostics**: `nxstate` does not log passwords. When filing a bug, redact any
  hostnames/credentials you consider sensitive and **rotate any credential that may have been
  exposed** in a paste.

## Hardening recommendations

- Use a least-privilege **`network-operator`** (read-only) account on the device.
- Prefer SSH key auth where supported; scope NX-API/keyring credentials per host.
- Run on a trusted management network; avoid `--insecure` over untrusted paths.
