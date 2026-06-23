---
title: Transports & parsing
description: How nxstate connects to a Nexus switch and turns raw NX-OS output into clean, normalized data.
owner: rnwolfe
lastReviewed: 2026-06-23
---

Every `nxstate` command follows the same execution path: pick a transport, run the command on the device, parse and normalize the result, then hand clean structured data to the [output layer](/guides/output-and-filtering/). Understanding this pipeline tells you why a particular command returns the data shape it does — and what to reach for when the default isn't enough.

## Transports

nxstate supports two ways to talk to a Nexus switch: **SSH** and **NX-API**. You choose with `--transport`.

| Flag value | What it does |
|---|---|
| `auto` *(default)* | Probes NX-API first; falls back to SSH if NX-API is unreachable or disabled |
| `nxapi` | NX-API only — fails immediately if the endpoint is unavailable |
| `ssh` | SSH only — skips the NX-API probe entirely |

### SSH — scrapli `cisco_nxos`

The SSH transport opens a connection with [scrapli](https://github.com/carlmontanari/scrapli) using the built-in `NXOSDriver` (the `cisco_nxos` platform). Every command is sent as `<cmd> | json` first, requesting structured output directly from the device shell. If the device returns valid JSON, the result is recorded with `parser: "json"` and no further parsing is needed.

```bash
# Force SSH for a single run
nxstate --host 10.0.0.1 --transport ssh interface list
```

SSH connects on port 22 by default. Pass `--port` to override.

### NX-API — `cli_show` accelerator

When NX-API is enabled on the switch (`feature nxapi`), nxstate can use it instead of SSH. The NX-API transport issues an HTTP POST to `https://<host>:<port>/ins` with a `cli_show` JSON payload and `output_format: json`. This avoids the SSH handshake and interactive shell entirely, which is faster and more reliable over high-latency links.

```bash
# Force NX-API
nxstate --host 10.0.0.1 --transport nxapi interface list

# NX-API with a self-signed certificate (skip TLS verification)
nxstate --host 10.0.0.1 --transport nxapi --insecure interface list
```

NX-API connects on port 443 by default. Pass `--port` to override.

The `--insecure` flag instructs nxstate to skip TLS certificate verification. Use it when your Nexus switch uses the default self-signed certificate. It has no effect on SSH connections.

#### Auto-transport selection

In `auto` mode (the default), nxstate probes NX-API first. If the probe succeeds, all commands for that invocation go through NX-API. If NX-API is unreachable, disabled, or returns a network error, nxstate silently falls back to SSH. You'll see which transport won in the `parser` field of JSON output (`"parser": "nxapi"` vs. `"parser": "json"`, `"genie"`, `"ntc"`, or `"text"`).

If you pin `--transport nxapi` and NX-API is unavailable, nxstate exits with code 9 (`UNREACHABLE`) rather than silently switching.

## Parsing pipeline

Once nxstate has raw bytes from the device, it works through a five-level pipeline. Each level is tried in order; the first one that produces structured data wins.

```
NX-API cli_show JSON
       │
       └── (on failure or SSH transport)
           SSH  →  <cmd> | json
                   │
                   └── (| json unsupported or returns unstructured text)
                       Genie parse  (optional [genie] extra)
                       │
                       └── (Genie absent or no parser match)
                           ntc-templates / TextFSM
                           │
                           └── (no template match)
                               raw text
```

### Level 1 — NX-API JSON (`parser: "nxapi"`)

NX-API's `cli_show` endpoint returns a JSON body directly. No further parsing is required. This is the fastest and most reliable path and produces the cleanest structured data.

### Level 2 — SSH `| json` (`parser: "json"`)

Over SSH, nxstate appends `| json` to every command before sending it. NX-OS pipes the output through its built-in JSON encoder when this filter is supported. If the response is valid JSON and non-empty, the result is used as-is.

If the device rejects `| json` (the filter is unsupported for that particular command) or returns empty output, scrapli marks the response as failed. nxstate retries the bare command — without the filter — and proceeds to the next pipeline level.

### Level 3 — Genie (`parser: "genie"`)

[Genie](https://developer.cisco.com/docs/genie-docs/) is part of the Cisco pyATS test framework. It ships approximately 293 NX-OS parsers that produce rich, deeply-structured output — far more granular than `| json` for commands like routing tables, BGP, OSPF, and VPCs.

Genie is an **optional extra** because the pyATS dependency tree is large (~293 MB). Install it when you need the best-structured output for complex commands:

```bash
uv tool install "nxstate[genie]"
# or
pip install "nxstate[genie]"
```

Without the `[genie]` extra, this level is silently skipped.

### Level 4 — ntc-templates / TextFSM (`parser: "ntc"`)

[ntc-templates](https://github.com/networktocode/ntc-templates) is a community library of TextFSM templates. It covers hundreds of `show` commands across Cisco platforms and is always available (a required dependency). When neither `| json` nor Genie can produce structured data, nxstate tries ntc-templates next.

### Level 5 — raw text (`parser: "text"`)

If nothing above produces structured data, nxstate returns the raw device output in the `raw` field with `parsed: null`. You can still consume this output; nxstate wraps free-form device text in `BEGIN/END UNTRUSTED DEVICE OUTPUT` markers so an AI agent won't follow embedded device instructions. See [output and filtering](/guides/output-and-filtering/) for how raw output is rendered.

## NX-OS TABLE_/ROW_ normalization

NX-OS `| json` output wraps list-style results in a verbose envelope:

```json
{
  "TABLE_interface": {
    "ROW_interface": [
      { "interface": "Ethernet1/1", "state": "up" },
      { "interface": "Ethernet1/2", "state": "down" }
    ]
  }
}
```

These wrappers make consuming the data awkward. nxstate's `normalize_nxos` function unwraps them automatically: a `dict` containing exactly one `TABLE_*` key whose value contains a `ROW_*` key is replaced with a plain list of the rows. This happens recursively so nested tables are also unwrapped. Other shapes (objects, scalars) pass through unchanged.

### Primary-table extraction

List commands (e.g. `interface list`, `vlan list`, `arp list`) use `first_rows` to extract just the primary table from a response that may contain multiple `ROW_*` tables. `first_rows` performs a depth-first search for the first `ROW_*` key, returns its contents as a normalized list, and falls back to `normalize_nxos` on the whole object when no `ROW_*` is found.

This is why `nxstate interface list` returns a flat array of interface objects rather than the nested envelope from the raw device.

For commands with multiple peer tables (e.g. complex routing responses), the `[genie]` extra produces richer, multi-table output that preserves all the relationships.

## Structured device-error handling

When the device rejects a command, nxstate raises a structured `DEVICE_ERROR` rather than passing back raw error text. The error carries a remediation hint and exits with code 1.

**NX-API path:** a non-200 `code` field in the `ins_api.outputs.output` object signals an error. nxstate extracts `msg` and raises `DEVICE_ERROR`.

**SSH path:** scrapli sets `resp.failed = True` when the device prompt indicates an error. nxstate detects this after the bare-command retry (not the `| json` attempt) and raises `DEVICE_ERROR`.

```json
{
  "ok": false,
  "error": {
    "code": "DEVICE_ERROR",
    "message": "'show vlan id 999': VLAN 999 not configured",
    "remediation": "verify the command exists on this platform/version and the feature is enabled"
  }
}
```

Authentication failures are caught separately and raise `AUTH_REQUIRED` (exit 4); network-level failures raise `UNREACHABLE` (exit 9). See the [exit codes reference](/reference/exit-codes/) for the full table.

## Choosing a transport

**Use `auto` (default)** when you don't know whether NX-API is available. It tries the fast path first and degrades gracefully.

**Use `--transport nxapi`** in production automation when you know NX-API is enabled and want consistent, fast, structured output without SSH handshake overhead.

**Use `--transport ssh`** when:
- NX-API is not enabled or is locked down
- You're connecting through a jump host or SSH proxy
- You want to avoid HTTP/HTTPS network rules
- You're debugging and want to see exactly what the device shell returns

**Install `[genie]`** when:
- You're running `route list`, `bgp summary`, or other multi-table commands and need the richest structured data
- You're building an agent or dashboard that consumes nested protocol state
- Commands routinely fall through to raw text and you want better coverage

## Related pages

- [Output & filtering](/guides/output-and-filtering/) — `--format`, `--select`, `--limit`, and how raw text is fenced
- [Authentication](/guides/authentication/) — credential resolution, NX-API vs SSH credential requirements
- [Global flags reference](/reference/global-flags/) — full `--transport`, `--insecure`, `--port`, `--timeout` documentation
- [Troubleshooting](/guides/troubleshooting/) — diagnosing transport failures with `nxstate doctor`
- [Exit codes](/reference/exit-codes/) — `UNREACHABLE` (9), `AUTH_REQUIRED` (4), `DEVICE_ERROR` (1)
