---
title: Installation
description: How to install nxstate, choose an install method, add the optional Genie parser extra, and verify your setup.
owner: rnwolfe
lastReviewed: 2026-06-23
---

nxstate is a Python package published to [PyPI](https://pypi.org/project/nxstate/). It
requires **Python 3.10 or later** and runs on any OS that supports its dependencies.

## Choose an install method

These paths cover virtually every workflow. `uvx` is the recommended way to start.

| Goal | Command |
|---|---|
| Try nxstate with zero install (recommended) | `uvx nxstate --help` |
| Install for repeated daily use | `uv tool install nxstate` |
| Isolated permanent install with pipx | `pipx install nxstate` |
| Install with pip (any virtualenv) | `pip install nxstate` |
| Install with maximum parser coverage | `uv tool install "nxstate[genie]"` |
| Grab the wheel/sdist directly | [GitHub Releases](https://github.com/rnwolfe/nxstate/releases) |

### Zero-install trial with `uvx`

[uv](https://docs.astral.sh/uv/) can run nxstate as an ephemeral tool without touching
your system Python or any virtualenv:

```bash
uvx nxstate --help
uvx nxstate version
```

Everything runs in a temporary, isolated environment that uv manages automatically.
Nothing is left behind after the process exits. This is the fastest way to evaluate
nxstate before committing to a full install.

### Permanent install with `uv tool install`

When you run nxstate often, install it as a persistent tool so the `nxstate` binary is
always on your PATH:

```bash
uv tool install nxstate
```

uv places the binary under `~/.local/bin` (or the equivalent on your OS). If that
directory is not on your `PATH` yet, uv will tell you and you can add it once:

```bash
# Add to your shell profile (bash example):
export PATH="$HOME/.local/bin:$PATH"
```

### Isolated install with pipx

[pipx](https://pipx.pypa.io/) installs nxstate into its own isolated environment while
still putting the `nxstate` binary on your PATH — a good choice if you don't use uv:

```bash
pipx install nxstate
```

### Install with pip

If you prefer pip or are working inside a virtualenv:

```bash
pip install nxstate
```

Inside a virtualenv the binary is placed in the environment's `bin/` directory
automatically.

### Download the release artifacts directly

Every tagged release publishes a built wheel (`.whl`), an sdist (`.tar.gz`), and a
`SHA256SUMS` file on the [GitHub Releases page](https://github.com/rnwolfe/nxstate/releases).
You can install a specific downloaded artifact with pip if you'd rather pin to a file:

```bash
pip install ./nxstate-0.2.0-py3-none-any.whl
```

## Parsing pipeline and the optional `[genie]` extra

nxstate supports two transports (see `--transport`): **NX-API** (HTTP POST to `/ins`) and
**SSH** (scrapli `cisco_nxos`). The default `auto` mode probes NX-API first and falls
back to SSH if NX-API is unavailable.

The parsing pipeline, from most to least preferred, is:

1. **NX-API `cli_show` JSON** — fastest path; used when NX-API is reachable (`auto` or `--transport nxapi`)
2. **SSH `<cmd> | json`** — NX-OS native structured output over SSH (no extra packages needed)
3. **Genie** (optional `[genie]` extra) — ~293 NX-OS-specific parsers; runs after `| json` fails
4. **ntc-templates** (TextFSM — included in the core install) — broad community parser coverage
5. **Raw text** — always available as a last resort

Adding the `[genie]` extra drops in **Genie** (part of Cisco's pyATS suite), which
provides approximately **293 NX-OS-specific parsers**. Genie runs between SSH `| json`
and ntc-templates, and dramatically improves structured coverage for commands that don't
natively emit JSON.

```bash
# uv — recommended
uv tool install "nxstate[genie]"

# pip
pip install "nxstate[genie]"
```

> **Note:** pyATS is a sizeable dependency tree (~300 MB). Install it when you need
> richer parser coverage, not when the core install is already meeting your needs. The
> core install covers the majority of common operational commands via NX-OS native JSON
> and ntc-templates.

## Runtime dependencies

The following packages are installed automatically with every `nxstate` install:

| Package | Role |
|---|---|
| `click >= 8.1` | CLI framework |
| `scrapli >= 2024.1.30` | SSH transport (`cisco_nxos` platform) |
| `ntc-templates >= 4.0` | TextFSM-based parser fallback |
| `textfsm >= 1.1` | TextFSM engine (used by ntc-templates) |
| `keyring >= 24` | OS keyring credential storage |
| `pyyaml >= 6` | Inventory file parsing |

The optional `[genie]` extra adds `pyats[library] >= 24`.

## Verify the install

After installation, confirm the binary is reachable and working:

```bash
nxstate version
```

You should see output like:

```
version  0.0.1
```

If the command is not found, make sure `~/.local/bin` is on your `PATH` (see above), or
activate the virtualenv where you installed nxstate.

To verify nxstate can actually reach a device, run the built-in connectivity check:

```bash
export NXSTATE_HOST=sw1 NXSTATE_USERNAME=netops
nxstate doctor
```

`doctor` checks that a host is configured, credentials are available, and the device is
reachable — all without changing anything on the switch. See
[Troubleshooting](/guides/troubleshooting/) for interpreting its output.

## What's next

- [Quickstart](/getting-started/quickstart/) — run your first `show` command against a live switch.
- [Authentication](/guides/authentication/) — store credentials securely in the OS keyring.
- [Inventory and Fan-out](/guides/inventory-and-fanout/) — define hosts and query a whole fleet at once.
- [Output and Filtering](/guides/output-and-filtering/) — JSON, TSV, field projection, and limits.
