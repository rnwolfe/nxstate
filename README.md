# nxstate

**Read-only** Cisco Nexus (NX-OS) state-gathering CLI, built for agents and humans. It runs
`show` commands and returns clean JSON — and it *cannot configure a switch*: any non-read input
is refused (`WRITE_REFUSED`). "No `conf t`" is the product boundary, not a flag.

> Scaffolded by [agent-cli-factory](https://github.com/OWNER/agent-cli-factory). The switch
> transport (scrapli + Genie/NX-API) is wired by the `cli-implement` stage — see `spec.md`.

## Quickstart
```bash
export NXSTATE_PASSWORD=...                 # never pass the password on argv
nxstate doctor --host SW1 --username admin  # verify reachability + creds
nxstate system version --host SW1 --json
nxstate interface list --host SW1 --format tsv
nxstate show "show ip ospf neighbors" --host SW1   # generic read passthrough
```

## Why it's safe for agents
- **Read-only by design** — no mutating commands exist; the `show`/`debug` passthrough refuses
  anything but reads.
- **Untrusted output fenced** — device text (descriptions, neighbor names, logs) is marked so an
  agent won't follow instructions embedded in it.
- **Self-describing** — `nxstate schema` (machine-readable command tree + exit codes + safety
  state) and `nxstate agent` (the bundled usage guide).
- **Structured everywhere** — `--format json|plain|tsv`, `--select`, `--limit`, stable exit codes.

## Install
```bash
uvx nxstate --help              # zero-install trial
uv tool install nxstate         # for repeated use
```

## Status
Implemented and **live-verified against a Cisco DevNet Nexus 9000v sandbox** (NX-OS 10.3(8)):
SSH (`| json`) + NX-API accelerator, structured device-error handling, `--select`/`--limit`/tsv,
untrusted fencing, and the `WRITE_REFUSED` boundary all confirmed end-to-end. 11 offline contract
tests pass (network stubbed). Parsing uses NX-OS `| json` + primary-table extraction; install the
`[genie]` extra for the full ~293-parser corpus on arbitrary commands.
