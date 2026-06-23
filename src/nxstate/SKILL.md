---
name: nxstate
description: Gather read-only state from Cisco Nexus (NX-OS) switches — show commands, interface/VLAN/route/BGP/MAC/ARP state, logging, environment. READ-ONLY by design; it cannot configure a switch. Use for "check switch state", "show interface/bgp/route on <switch>", NX-OS troubleshooting and inventory.
---

# nxstate

A **read-only** Cisco Nexus state-gathering CLI. It can never configure a switch — any non-read
command is refused with `WRITE_REFUSED` (exit 11). Switch output is fenced as untrusted.

## Connecting
Every switch command needs `--host`. Credentials: `--username` plus a password from
`NXSTATE_PASSWORD` (env) or `--password-stdin` — never on the command line. Transport defaults
to `auto` (probe NX-API, fall back to SSH); force with `--transport ssh|nxapi`.
- `nxstate doctor --host SW1 --username admin` — verify reachability + creds.
- `nxstate auth status --host SW1` — show whether a credential is available.

## First moves
- `nxstate schema` — command tree, exit codes, safety state (no host needed).
- `nxstate --help` — example-led help.

## Reading state (curated, returns parsed JSON)
- `nxstate system version|environment|inventory --host SW1`
- `nxstate interface list --host SW1` · `interface show Eth1/1` · `interface counters`
- `nxstate vlan list` · `mac list` · `arp list`
- `nxstate route list [--vrf X]` · `nxstate bgp summary [--vrf X]`
- `nxstate neighbor list [--protocol cdp|lldp]`
- `nxstate logging --host SW1` (text, fenced untrusted)

## Generic read passthrough
- `nxstate show "show ip ospf neighbors" --host SW1` — any `show` command; parsed if a parser
  exists, else fenced raw text. **Non-read input (conf/write/reload/...) → exit 11 WRITE_REFUSED.**

## Gated heavy reads
- `nxstate debug "<...>" --host SW1 --allow-debug` — control-plane-impacting; gated.
- `nxstate tech-support --host SW1 --allow-tech` — large/slow.

## Output
`--format json|plain|tsv` (or `--json`), `--select a,b`, `--limit N`. Data on stdout; notes on
stderr. Passthrough JSON: `{command, parser, parsed, raw, untrusted}`.

## Exit codes
0 ok · 2 usage/HOST_REQUIRED · 4 auth · 9 unreachable · 11 write_refused · 13 input_required ·
14 parse_unavailable. Full table: `nxstate schema`.
