---
title: Contributing
description: How to set up a dev environment, understand the project layout, add a curated command, and get a PR merged.
owner: rnwolfe
lastReviewed: 2026-06-23
---

nxstate is a **read-only** Cisco Nexus state-gathering CLI built for network engineers and
their coding agents. Contributions that add curated `show` commands, improve parsing,
harden safety, or sharpen the docs are very welcome.

This page covers everything you need to go from zero to merged PR.

## Ground rules

Before touching any code, internalize these three invariants. PRs that violate them will
be declined regardless of other quality.

### Read-only — forever

nxstate must never gain configuration or mutation capability. There is no
`--allow-mutations` flag, and there never will be. The `show` passthrough in
`src/nxstate/safety.py` validates every caller-supplied command with `assert_read_command`
and refuses anything that does not start with `show` — plus an explicit blocklist of
forbidden leading tokens (`conf`, `configure`, `write`, `wr`, `reload`, `clear`, `no`,
`bash`, `python`, and more). The `debug` passthrough is gated separately by `--allow-debug`
and constructs the device command directly (it does not go through `assert_read_command`);
it still never accepts configuration input. "No conf t" is the product boundary, not a toggle.

See [Read-only safety](/concepts/read-only-safety/) for the full rationale.

### No secrets in the repository

Passwords must never appear in code, test fixtures, or the inventory format. The
credential resolution order (stdin → `NXSTATE_PASSWORD` → OS keyring) is the only
supported path. If you need a password in a test, pass it via `monkeypatch.setenv` on
`NXSTATE_PASSWORD` — and never commit it.

### Raw device text stays fenced

Any free-text device output (log files, banner text, passthrough raw) must stay wrapped
in `BEGIN/END UNTRUSTED DEVICE OUTPUT` markers via `src/nxstate/wrap.py`. This protects
LLM agents consuming nxstate output from prompt-injection embedded in device banners.
Do not bypass `fence()` or strip the `"untrusted": true` key from raw JSON envelopes.

---

## Dev setup

nxstate uses [uv](https://docs.astral.sh/uv/) for environment management.

```bash
# 1. Clone the repo
git clone https://github.com/rnwolfe/nxstate.git
cd nxstate

# 2. Create the venv and install all dependencies (including dev extras)
uv sync --extra dev

# 3. Verify the suite passes offline (no switch needed)
uv run pytest -q

# 4. Lint and format
uv run ruff check .
uv run ruff format .
```

The test suite **must pass offline**. `NexusClient.run_show` is stubbed via `monkeypatch`
in the `offline` autouse fixture in `tests/test_cli.py`, so no device is ever required
to run tests. Live testing against a real switch (e.g., Cisco DevNet Nexus 9000v) is
done manually and is never required of a PR reviewer.

If you are adding the optional Genie parsers to your local environment:

```bash
uv sync --extra dev --extra genie
```

The `[genie]` extra pulls in `pyats[library]` (~293 NX-OS parsers). It is optional and
must never be a hard dependency of new commands.

### Docs dev server

Documentation lives in `docs-site/` — an Astro Starlight site.

```bash
cd docs-site
pnpm dev --host 0.0.0.0   # live-reload at http://localhost:4321
pnpm build                 # also regenerates llms.txt / llms-full.txt
```

---

## Project layout

```
src/nxstate/
  cli.py          Click grammar, Runtime dataclass, fan-out, exit-code mapping
  client.py       scrapli SSH + NX-API transport, NX-OS JSON normalization, parsing pipeline
  inventory.py    YAML inventory load/resolve (defaults ← groups ← host)
  output.py       Output contract: json/plain/tsv, --select, --limit, Writer
  errors.py       Stable exit-code table (ExitCode) + structured AppError helpers
  safety.py       assert_read_command — the WRITE_REFUSED read-only boundary
  wrap.py         fence() — untrusted device output fencing
  SKILL.md        Embedded agent usage guide (served by `nxstate agent`)
tests/
  test_cli.py     Offline test suite; stubs NexusClient.run_show
docs-site/        Astro Starlight documentation site
pyproject.toml    Build config, dependency declarations, ruff settings
CHANGELOG.md      Keep-a-Changelog; update [Unreleased] on every PR
CONTRIBUTING.md   Condensed ground rules (machine-friendly)
AGENTS.md         Agent-specific guardrails for coding assistants working in this repo
```

The entry point is `nxstate.cli:main` (declared in `pyproject.toml`). `main()` calls
`run()` and calls `sys.exit()` on the result, so every code path is testable in-process
without spawning a subprocess.

---

## Adding a curated command

Curated commands (e.g., `interface list`, `bgp summary`) are the preferred way to surface
NX-OS state. They are safer than `nxstate show "..."` because the mapping from noun-verb
to NX-OS command is explicit and tested. Here is the complete checklist:

### 1. Add the Click subcommand in `cli.py`

All curated commands live in `src/nxstate/cli.py` as Click subcommands grouped by noun.
The pattern is:

```python
@cli.group()
def widget():
    """Widget state."""


@widget.command("list")
@global_options
@click.pass_context
def widget_list(ctx, **_):
    """show widget (human summary)."""
    make_runtime(ctx).show("show widget", rows=True)
```

Key points:

- **`@global_options`** — every leaf command must carry this decorator so all global flags
  (`--format`, `--host`, `--select`, `--limit`, etc.) work in any position on the command
  line.
- **`rows=True`** on list commands — `rt.show("show widget", rows=True)` tells the runtime
  to call `first_rows()` on the parsed result, extracting the primary `ROW_` table from
  the `TABLE_/ROW_` NX-OS JSON wrapper. This is what makes `--select` field projection
  and `--limit` row capping work correctly. Omit `rows=True` only for commands that return
  a single object (e.g., `system version`).
- **Only `show ...` commands.** The underlying NX-OS command passed to `rt.show()` must
  start with `show`. Do not pass the command through `assert_read_command` yourself — the
  curated layer is responsible for constructing only safe commands.

### 2. Route output through `Writer` — never bypass it

The `Runtime.emit_result()` method (called internally by `rt.show()`) routes data through
`output.Writer`. This is what gives every command `--select`, `--limit`, `--format json`,
`--format tsv`, and the untrusted-fencing contract. Do not `print()` results directly or
call `rt.out.emit_json()` from new curated commands.

### 3. Update `src/nxstate/SKILL.md`

`SKILL.md` is the embedded agent guide served by `nxstate agent`. It is the canonical
reference for coding agents that drive nxstate. After adding a command, add it to the
command table in `SKILL.md` with its NX-OS mapping, key output fields, and any caveats.

### 4. Write an offline test

Every new command needs at least one test in `tests/test_cli.py`. The pattern is:

```python
def test_widget_list(capsys, monkeypatch):
    from nxstate import client as clientmod

    # Return a TABLE_/ROW_ shaped parsed result (as NX-OS would)
    table = {
        "TABLE_widget": {
            "ROW_widget": [
                {"name": "w1", "state": "up"},
                {"name": "w2", "state": "down"},
            ]
        }
    }

    monkeypatch.setattr(
        clientmod.NexusClient,
        "run_show",
        lambda self, command, parse=True: {
            "command": command,
            "parsed": table,
            "raw": None,
            "parser": "json",
        },
    )

    code = run(["widget", "list", "--host", "sw1", "--json"])
    out = capsys.readouterr().out
    assert code == 0
    rows = json.loads(out)
    assert isinstance(rows, list)
    assert rows[0]["name"] == "w1"
```

Cover at minimum: the happy path (parsed data → normalized array), `--select` + `--limit`
projection, and the read-only boundary if your command has any passthrough surface. The
existing `test_write_refused` and `test_write_refused_sneaky_leader` tests show the
expected pattern for safety tests.

---

## The read-only invariant in tests

The test suite already verifies the safety boundary. When you add a passthrough surface
or modify `safety.py`, add a corresponding test:

```python
def test_new_surface_write_refused(capsys):
    code = run(["show", "conf t", "--host", "sw1", "--json"])
    err = capsys.readouterr().err
    assert code == 11              # ExitCode.WRITE_REFUSED
    assert "WRITE_REFUSED" in err
    assert capsys.readouterr().out.strip() == ""   # no stdout on refusal
```

Note that `WRITE_REFUSED` fires **before** any network connection is made. The validator
in `safety.py` never dials the device.

---

## Pull request checklist

Before opening a PR, verify:

- [ ] `uv run pytest -q` passes (all tests green, no network access).
- [ ] `uv run ruff check .` reports no issues.
- [ ] `uv run ruff format .` has been run (or produced no diff).
- [ ] `CHANGELOG.md` `[Unreleased]` section is updated with a user-facing entry.
- [ ] If you added or changed a command, flag, output field, env var, exit code, or
      inventory key — the matching docs page in `docs-site/` is updated in the **same PR**.
      (If your change has no docs impact, say so explicitly in the PR description.)
- [ ] If you added `src/nxstate/SKILL.md` additions, `nxstate agent` still renders cleanly.
- [ ] Commits use **Conventional Commits** format (see below).
- [ ] Each commit is signed off with `git commit -s` (DCO).

### Conventional Commits

Use these prefixes. One logical change per commit and per PR.

| Prefix | Use for |
|---|---|
| `feat:` | New command, flag, or user-visible capability |
| `fix:` | Bug fix |
| `docs:` | Docs-only changes |
| `refactor:` | Internal restructuring with no behavior change |
| `test:` | Test additions or corrections |
| `chore:` | Build, CI, dependency bumps |

Examples:

```
feat: add widget list command (show widget)
fix: normalize TABLE_/ROW_ wrapper for show ip arp on NX-OS 9.x
docs: add contributing guide
test: cover fan-out partial exit when one device is unreachable
```

### Developer Certificate of Origin (DCO)

nxstate uses the [DCO](https://developercertificate.org/) instead of a CLA. Sign every
commit with:

```bash
git commit -s -m "feat: add widget list"
```

This appends a `Signed-off-by` trailer confirming that you have the right to contribute
the code and that it will be licensed under `MIT OR Apache-2.0` (both options, as declared
in `pyproject.toml`).

---

## Docs are part of done

A change is **not complete** until its documentation is updated in the same commit or PR.
This is a non-negotiable policy, not a suggestion.

When you change any public surface, update the matching page:

| Changed surface | Doc page to update |
|---|---|
| CLI commands or subcommands | [Reference: Commands](/reference/commands/) |
| Global flags | [Reference: Global flags](/reference/global-flags/) |
| Exit codes (`errors.py`) | [Reference: Exit codes](/reference/exit-codes/) |
| Inventory keys | [Reference: Inventory schema](/reference/inventory-schema/) |
| Environment variables | [Reference: Environment variables](/reference/environment-variables/) |
| Transport or auth behavior | [Authentication guide](/guides/authentication/), [Transports & parsing](/concepts/transports-and-parsing/) |
| Fan-out or inventory targeting | [Inventory & fan-out guide](/guides/inventory-and-fanout/) |
| Output format, `--select`, `--limit` | [Output & filtering guide](/guides/output-and-filtering/) |
| New curated command | [Gathering state guide](/guides/gathering-state/) + `SKILL.md` |

When cutting a release, also run `cd docs-site && pnpm build` so `llms.txt` and
`llms-full.txt` regenerate and ship with the release.

---

## Reporting bugs and security issues

Use the GitHub issue forms for bugs and feature requests. **Do not file security
vulnerabilities publicly** — see `SECURITY.md` for the private disclosure process.

---

## What makes a good first contribution

If you are looking for a place to start:

- **Add a curated command** — pick a `show` command you use regularly (e.g.,
  `show ip ospf neighbors`, `show spanning-tree`), follow the checklist above, and open a
  PR. The test stub pattern is well established and the diff is usually small.
- **Improve a TextFSM/Genie parser fallback** — if a command produces raw text on a
  particular NX-OS version, contributing a TextFSM template fix upstream (ntc-templates)
  or opening an issue with the raw output helps everyone.
- **Sharpen a docs page** — if something was unclear when you first read it, fix it. Docs
  PRs are fast to review and have real impact for users.

When in doubt, open an issue first to discuss the approach. That saves everyone time.
