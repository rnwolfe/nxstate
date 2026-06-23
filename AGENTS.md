# AGENTS.md

Guidance for AI agents working **in this repository** (engineering on nxstate itself). To
*use* the built tool, run `nxstate agent` for the runtime usage guide instead.

## What this is
A read-only Cisco Nexus (NX-OS) state-gathering CLI (Python/Click). Read-only is a hard
invariant — see "Guardrails".

## Setup / build / test
```bash
uv sync --extra dev
uv run pytest -q          # offline; network is stubbed, no device needed
uv run ruff check .       # lint
uv run ruff format .      # format
```

## Layout
- `src/nxstate/cli.py` — Click grammar, runtime, targeting/fan-out, exit mapping.
- `src/nxstate/client.py` — scrapli SSH + NX-API client, NX-OS JSON normalization, parsing.
- `src/nxstate/inventory.py` — inventory load/resolve (defaults←groups←host).
- `src/nxstate/output.py` — output contract (json/plain/tsv, select, limit).
- `src/nxstate/errors.py` — exit-code table + structured errors.
- `src/nxstate/safety.py` — the `WRITE_REFUSED` read-only validator.
- `src/nxstate/wrap.py` — untrusted-output fencing.

## Guardrails (do not violate)
- **Read-only only.** Never add configuration/mutation commands; the `show`/`debug` passthrough
  must keep refusing non-read input (`assert_read_command`).
- **No secrets** in code, tests, fixtures, or the inventory format. Passwords resolve from
  stdin/env/keyring only — never argv.
- Keep device output **fenced as untrusted** for raw text.
- Output goes to stdout; diagnostics/notes to stderr. `--select`/`--limit`/`--format` must keep
  working — route parsed data through the `output.Writer`, don't bypass it.

## Conventions
- Conventional Commits; update `CHANGELOG.md` `[Unreleased]`; tests must pass offline.
- List commands use `rt.show(..., rows=True)` so the primary table is extracted.
