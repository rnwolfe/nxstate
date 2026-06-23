# spec.md — nxstate

> Build spec for an agent-focused, **read-only** Cisco Nexus (NX-OS) state-gathering CLI.
> Written by `cli-plan`; consumed by `cli-scaffold` / `cli-implement` / `cli-publish`.
> Name is provisional (`nxstate` = NX-OS state). Adjustable.

## Target
- **Service**: Cisco Nexus switches running NX-OS (fleet, mixed versions).
- **Scope**: READ-ONLY state gathering — `show` commands, counters, environment, neighbors,
  routing/BGP/MAC/ARP state, logging, inventory. **NO configuration (`conf t`), NO mutations.**
- **Surface**:
  - **Primary**: SSH CLI with `| json` / `| json-native` (9.3(1)+). Only surface enabled by
    default on every image/platform; no `conf t` to enable; `network-operator` RBAC = read-only.
  - **Accelerator (opportunistic)**: NX-API CLI `cli_show` (POST `/ins`, `output_format: json`).
    Default-on only on **N9K 9.2(1)+**; elsewhere needs `feature nxapi` → probe-and-use, never assume.
  - **Out of scope (need `conf t` to enable)**: NETCONF (`feature netconf`), gNMI (`feature grpc`).
    Optional future opt-in transports only.
- **Rate/scale & safety**:
  - `debug` commands are control-plane-impacting → gated (see `--allow-debug` below) + warned.
  - `show tech-support` is huge/slow → opt-in, long timeout, text-only, never fleet-wide by default.
  - Reuse NX-API session cookie / SSH channel; pace commands; bound large tables.
- **ToS / risk**: Cisco-sanctioned interfaces (SSH/NX-API), official auth/RBAC. Low ToS risk.
  Main risk is operational (debug/show-tech on busy boxes) — mitigated by gating + warnings.

## Language & framework
- **Language**: **Python** (SDK gravity overrides the Go default).
- **Rationale**: a state-gathering tool's value IS structured parsing of arbitrary `show`
  output; Python has ~293 Cisco-maintained Genie NX-OS parsers + 82 ntc-templates with
  auto-routing, Go has no equivalent. Go's cold-start edge is moot — every call opens an SSH
  session, so the network round-trip dominates.
- **Framework**: **Click 8.4+** (per blueprint-python.md; `to_info_dict()` → `schema --json`).
- **SDK/libraries**: **scrapli** (core `cisco_nxos` transport, sync) + **Genie**
  (`genie_parse_output()`) as primary parser + **ntc-templates** fallback. Optional `httpx`
  for the NX-API `cli_show` accelerator.
- **Blueprint**: references/research/blueprint-python.md
- **Gotchas to honor**: keep stdout machine-clean (scrapli/genie log to stderr/logging); keyring
  backend on headless Linux; Genie install is heavy (make it an extra, lazy-import).

## Auth
- **Model**: SSH (username/password OR SSH key) with `network-operator` role; OR NX-API HTTP
  Basic over HTTPS (+ session cookie reuse) when the accelerator is used.
- **Agent-completable path**: SSH key or env/stdin password — no interactive browser. `--transport
  ssh|nxapi|auto` (default auto: probe NX-API, fall back to SSH).
- **Secret storage**: OS keyring; env (`NXSTATE_PASSWORD`) / stdin / `--password-stdin`; **never
  argv**. Warn on insecure file perms. TLS: `--insecure` for NX-API self-signed (default cert).
- **Subcommands**: `auth login|status|logout`; `doctor` (reachability, creds, RBAC probe, TLS,
  which transport is available per host).
- **RBAC note**: stock `network-operator` cannot see `show running-config`/`startup-config`;
  document that a custom read-role is needed if those are required (still no config rights).

## Command surface (noun-verb) — ALL reads
Curated commands return Genie-parsed JSON; the generic passthrough covers the long tail.

| Command | Description | Parsed via |
|---|---|---|
| `nxstate system version` | show version | Genie |
| `nxstate system environment` | show environment (power/fan/temp) | Genie |
| `nxstate system inventory` | show inventory | Genie |
| `nxstate interface list` | show interface brief | Genie |
| `nxstate interface show <name>` | show interface <name> | Genie |
| `nxstate interface counters [<name>]` | show interface counters | Genie |
| `nxstate vlan list` | show vlan | Genie |
| `nxstate route list [--vrf]` | show ip route | Genie |
| `nxstate bgp summary [--vrf]` | show ip bgp summary | Genie |
| `nxstate neighbor list` | show cdp/lldp neighbors | Genie |
| `nxstate mac list` | show mac address-table | Genie |
| `nxstate arp list` | show ip arp | Genie |
| `nxstate logging show` | show logging logfile | text (wrapped untrusted) |
| `nxstate show "<show ...>"` | generic read passthrough; Genie-parsed if a parser exists, else raw text | Genie/text |
| `nxstate debug "<...>"` | sensitive read; **gated** by `--allow-debug` + warning; time-bounded | text |
| `nxstate tech-support` | show tech-support; **gated** by `--allow-tech` + long timeout | text |

Targeting: `--host` (required), `--port`, `--username`, `--transport`, `--vrf`, `--timeout`.
(Fleet/multi-host iteration is a v2 concern — v1 is single `--host`.)

## Safety model (contract adaptation for a read-only-only domain)
- The tool has **no mutating commands**. The contract's read-only gate is realized as an
  **input validator**: `show`/`debug` passthrough **refuses any input that is not a read
  command** (anything starting with `conf`, `configure`, `write`, `copy`, `reload`, set/no/
  clear verbs, etc.) → structured **`WRITE_REFUSED`** error (new code) on stderr.
- **No `--allow-mutations` flag** — "no `conf t`" is the product boundary, not a toggle.
- `--allow-debug` / `--allow-tech` gate the operationally-sensitive reads (still reads).

## Exit codes (base table + additions)
Base from contract §4 (0 ok, 2 usage, 3 empty, 4 auth, 5 not_found, 7 rate, 8 retryable,
10 config). Additions:
- `11` `WRITE_REFUSED` (non-read command rejected by the passthrough validator)
- `9`  `UNREACHABLE` (host/transport not reachable)
- `14` `PARSE_UNAVAILABLE` (no parser for the command → returned raw text; soft, may still exit 0)

## Output schema
- Curated commands: the Genie parser's dict, emitted as stable JSON (document per command).
- Passthrough: `{ "command": "...", "parsed": <dict|null>, "raw": "<text|null>",
  "parser": "genie|ntc|none" }` — `raw` free text is **fenced untrusted** in agent mode (§8).
- `--format json|plain|tsv`; `--select`; `--limit`; `--concise`/`--detailed`.

## Universal contract surface (provided by scaffold)
`--format` · `--dry-run` (no-op for pure reads; still valid) · `--no-input` · `--limit` ·
`--select` · `schema` · `agent` · `auth` · `doctor`. (`--allow-mutations` intentionally omitted;
replaced by the WRITE_REFUSED validator + `--allow-debug`/`--allow-tech`.)

## Prompt-injection surface (contract §8)
HIGH — switch output (interface descriptions, CDP/LLDP neighbor names, logging, banners) is
attacker-influenceable free text. All `raw`/text output is **fenced as untrusted by default**.

## Distribution
- **Targets**: `uvx nxstate` (zero-install trial) + `uv tool install nxstate` (agent use);
  PyPI via `uv build`/`uv publish` (Trusted Publishing/OIDC). pipx as alt.
- **Trial path**: `uvx nxstate --host <sw> system version`.
- **Agent hot-loop path**: `uv tool install` then the bare `nxstate` binary (avoids uvx re-resolve).
- No single static binary by default (SSH-bound; cold start irrelevant). PyInstaller only if asked.

## Publish
- **Flag**: `full` — this is a portfolio-quality showcase (a clean, safe, agent-first read-only
  network tool is a strong OSS niche). Docs via `starlight-docs`/`harvest-docs`; release via the
  `release` skill; README + VHS demo + SECURITY.md (credential threat model) + discoverability
  (awesome-cli-apps, awesome-agent-clis).
