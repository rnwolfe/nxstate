# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-06-25

### Added
- `version --check`: query PyPI for a newer release (network, short timeout, fail-silent) and
  report whether an upgrade is available, without ever self-mutating.
- SSRF override-guard on the release-check source: `NXSTATE_RELEASES_URL` is scheme-constrained
  to https (or http only for localhost/127.0.0.1/::1), falling back to the official PyPI JSON
  API otherwise — defends against local-file reads and remote-host probes via a misconfigured
  override.

### Changed
- Rolled up conformance to Agent CLI Guidelines v0.4.0.

## [0.1.0] - 2026-06-23

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

[Unreleased]: https://github.com/rnwolfe/nxstate/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/rnwolfe/nxstate/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/rnwolfe/nxstate/releases/tag/v0.1.0
