# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Read-only Cisco Nexus (NX-OS) state-gathering CLI: `system`, `interface`, `vlan`, `route`,
  `bgp`, `neighbor`, `mac`, `arp`, `logging`, plus a generic `show` passthrough and gated
  `debug` / `tech-support`.
- SSH transport (scrapli `cisco_nxos`, `| json`) with an NX-API `cli_show` accelerator
  (`--transport auto`); Genie (optional `[genie]` extra) and ntc-templates parsing.
- `WRITE_REFUSED` read-only boundary (no `conf t`); untrusted-output fencing.
- Output contract: `--format json|plain|tsv`, `--select`, `--limit`, `schema`, `agent`,
  structured errors, stable exit codes.
- Inventory (`~/.config/nxstate/inventory.yaml`, defaults←groups←host) and concurrent
  multi-device fan-out (`--device`/`--group`/`--all`, NDJSON per device, partial-exit 15).
- Credential resolution: flag → inventory → env → default; password via stdin/env/keyring
  (never argv); keyring storage via `auth login` / removal via `auth logout`; `doctor`.

[Unreleased]: https://github.com/rnwolfe/nxstate/commits/main
