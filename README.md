# nxstate

> Read-only Cisco Nexus (NX-OS) state, as clean JSON — for your coding agent and for you.
> It runs `show` commands across one switch or a whole fleet, and it **physically cannot
> configure a device**: any non-read input is refused (`WRITE_REFUSED`). "No `conf t`" is the
> product boundary, not a flag.

[![CI](https://github.com/rnwolfe/nxstate/actions/workflows/ci.yml/badge.svg)](https://github.com/rnwolfe/nxstate/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/nxstate.svg)](https://pypi.org/project/nxstate/)
[![Python](https://img.shields.io/pypi/pyversions/nxstate.svg)](https://pypi.org/project/nxstate/)
[![License](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](#license)
[![Docs](https://img.shields.io/badge/docs-rnwolfe.github.io%2Fnxstate-0ea5a5)](https://rnwolfe.github.io/nxstate/)
[![Agent CLI Guidelines: Full](https://aclig.dev/badge/agent-cli-guidelines-full.svg)](https://aclig.dev/conformance/)

📖 **Documentation: <https://rnwolfe.github.io/nxstate/>**

![nxstate demo](demo/nxstate.gif)

<sub>Demo rendered from [`demo/nxstate.tape`](demo/nxstate.tape) via [vhs](https://github.com/charmbracelet/vhs).</sub>

## Why nxstate

- **Read-only by design** — no mutating commands exist; the `show`/`debug` passthrough refuses
  anything but reads. Safe to point an autonomous agent at production.
- **Structured output** — `--format json|plain|tsv`, `--select`, `--limit`; NX-OS `TABLE_/ROW_`
  noise normalized into clean arrays.
- **Self-describing** — `nxstate schema` (machine-readable command tree + exit codes + live
  safety state) and `nxstate agent` (a usage guide embedded in the binary).
- **Fleet-ready** — inventory + concurrent multi-device fan-out with per-device error isolation.
- **Prompt-injection hardened** — device free-text (descriptions, neighbor names, logs) is fenced
  as untrusted so an agent won't execute instructions hidden in it.
- **Credential-safe** — passwords via stdin/env/OS-keyring, never on the command line.

## Install

| Method | Command |
|---|---|
| Zero-install trial | `uvx nxstate --help` |
| For repeated use | `uv tool install nxstate` |
| pip | `pip install nxstate` |
| Max parser coverage | `uv tool install "nxstate[genie]"` (adds Genie's ~293 NX-OS parsers) |

## Quickstart

```bash
# Resolution is flag → inventory → env → default, so export defaults once:
export NXSTATE_HOST=sw1 NXSTATE_USERNAME=netops NXSTATE_PASSWORD=...   # never on argv
nxstate doctor                         # verify reachability + credentials
nxstate system version --json
nxstate interface list --format tsv
nxstate show "show ip ospf neighbors"  # generic read passthrough (non-read → WRITE_REFUSED)
```

## Authentication

`nxstate` needs a target (`--host` or an inventory `--device`) and a username; the password is
resolved **`--password-stdin` → `NXSTATE_PASSWORD` → OS keyring → prompt** — never via argv.

```bash
nxstate auth login --host sw1 -u netops   # store the password in the OS keyring (user@host)
nxstate auth status --host sw1            # is a credential available? (token redacted)
```

Use a least-privilege `network-operator` (read-only) account. NX-API with a self-signed cert
needs `--insecure` (trusted networks only). Transport defaults to `auto` (probe NX-API → SSH).

## Inventory & multi-device fan-out

Define hosts/groups in `~/.config/nxstate/inventory.yaml` (copy `docs/inventory.example.yaml`) —
`defaults` ← `groups` ← `host`, **no secrets in the file**:

```yaml
defaults: { username: netops, transport: auto }
groups:   { datacenter: { transport: nxapi, insecure: true } }
hosts:
  leaf1: { host: 10.1.1.11, groups: [datacenter] }
  leaf2: { host: 10.1.1.12, groups: [datacenter] }
```

```bash
nxstate interface list --device leaf1        # one host → clean output
nxstate interface list --group datacenter    # many → concurrent, NDJSON per device
nxstate system version --all --select nxos_ver_str
```

Fan-out runs concurrently (`--workers N`, default 10), streams one JSON object per device
(`{device, host, ok, data|error}`), **isolates per-device failures**, and exits `15` if any
device failed.

## Cookbook

```bash
nxstate vlan list --select vlanshowbr-vlanid,vlanshowbr-vlanname    # project fields
nxstate route list --vrf default --limit 20                        # bound output
nxstate neighbor list --protocol cdp --json | jq '.[].device_id'   # pipe to jq
nxstate logging                                                    # raw text, fenced untrusted
nxstate debug "ip ospf" --allow-debug    # gated control-plane read (warns)
nxstate tech-support --allow-tech        # gated, large/slow
nxstate schema | jq '{tool, read_only, exit_codes, safety}'        # self-description
```

## Exit codes

`0` ok · `2` usage / `HOST_REQUIRED` · `4` auth · `9` unreachable · `11` `WRITE_REFUSED` ·
`13` input required · `14` parse unavailable · `15` partial (some devices failed). Full table:
`nxstate schema`.

## Development

```bash
uv sync --extra dev
uv run pytest -q          # offline; network stubbed, no device needed
uv run ruff check .
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and [AGENTS.md](AGENTS.md).

## Status

Implemented and **live-verified against a Cisco DevNet Nexus 9000v sandbox** (NX-OS 10.3(8)):
SSH (`| json`) + NX-API accelerator, structured device-error handling, fan-out with per-device
isolation, untrusted fencing, and the `WRITE_REFUSED` boundary all confirmed end-to-end.

## License

Dual-licensed under either [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE), at your option.
