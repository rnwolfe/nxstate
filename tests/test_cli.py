import json

import pytest

from nxstate.cli import run


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("NXSTATE_PASSWORD", raising=False)


def test_schema_has_safety_and_exit_codes(capsys):
    code = run(["schema"])
    out = capsys.readouterr().out
    assert code == 0
    s = json.loads(out)
    assert s["read_only"] is True
    assert s["safety"]["mutations"].startswith("none")
    assert s["exit_codes"]["write_refused"] == 11


def test_host_required(capsys):
    code = run(["system", "version", "--json"])
    err = capsys.readouterr().err
    assert code == 2
    assert "HOST_REQUIRED" in err


def test_write_refused(capsys):
    # The read-only boundary: non-read input is refused even with a host.
    code = run(["show", "conf t", "--host", "sw1", "--json"])
    cap = capsys.readouterr()
    assert code == 11
    assert "WRITE_REFUSED" in cap.err
    assert cap.out.strip() == ""


def test_write_refused_sneaky_leader(capsys):
    code = run(["show", "reload", "--host", "sw1"])
    assert code == 11


def test_passthrough_read_ok(capsys):
    code = run(["show", "show ip ospf neighbors", "--host", "sw1", "--json"])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["command"] == "show ip ospf neighbors"
    assert payload["untrusted"] is True  # raw device text is fenced/flagged


def test_curated_command_runs_against_stub(capsys):
    code = run(["system", "version", "--host", "sw1", "--json"])
    out = capsys.readouterr().out
    assert code == 0
    assert json.loads(out)["command"] == "show version"


def test_debug_gated(capsys):
    code = run(["debug", "ip ospf", "--host", "sw1"])
    err = capsys.readouterr().err
    assert code == 6
    assert "DEBUG_BLOCKED" in err


def test_debug_allowed(capsys):
    code = run(["debug", "ip ospf", "--host", "sw1", "--allow-debug", "--json"])
    out = capsys.readouterr().out
    assert code == 0
    assert json.loads(out)["command"] == "debug ip ospf"


def test_did_you_mean(capsys):
    code = run(["interfaces", "list"])
    err = capsys.readouterr().err
    assert code == 2
    assert "did you mean" in err and "interface" in err


def test_flag_after_subcommand_position(capsys):
    # Global flags must work in any position (the kong-parity requirement).
    code = run(["system", "version", "--host", "sw1", "--format", "tsv"])
    assert code == 0
