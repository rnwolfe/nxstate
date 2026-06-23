import json

import pytest

from nxstate.cli import run


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    for var in (
        "NXSTATE_PASSWORD",
        "NXSTATE_HOST",
        "NXSTATE_USERNAME",
        "NXSTATE_TRANSPORT",
        "NXSTATE_PORT",
        "NXSTATE_INVENTORY",
    ):
        monkeypatch.delenv(var, raising=False)


def _inventory(tmp_path):
    p = tmp_path / "inv.yaml"
    p.write_text(
        "defaults: {username: u, transport: ssh}\n"
        "groups: {dc: {}}\n"
        "hosts:\n"
        "  a: {host: 10.0.0.1, groups: [dc]}\n"
        "  b: {host: 10.0.0.2, groups: [dc]}\n"
    )
    return str(p)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Never touch the network in tests: stub the client's run_show."""
    from nxstate import client as clientmod

    def fake_run_show(self, command, parse=True):
        return {
            "command": command,
            "parsed": None,
            "raw": f"<stub {command} on {self.host}>",
            "parser": "text",
        }

    monkeypatch.setattr(clientmod.NexusClient, "run_show", fake_run_show)


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


def test_parsed_output_normalized_with_select_limit(capsys, monkeypatch):
    # Parsed NX-OS TABLE_/ROW_ data is normalized to a clean array and --select/--limit apply.
    from nxstate import client as clientmod

    table = {
        "TABLE_interface": {
            "ROW_interface": [
                {"interface": f"Eth1/{i}", "state": "down", "vlan": "1"} for i in range(1, 11)
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
    code = run(
        ["interface", "list", "--host", "sw1", "--json", "--limit", "3", "--select", "interface"]
    )
    out = capsys.readouterr().out
    assert code == 0
    rows = json.loads(out)
    assert isinstance(rows, list) and len(rows) == 3
    assert rows[0] == {"interface": "Eth1/1"}


def test_fanout_ndjson(capsys, tmp_path, monkeypatch):
    from nxstate import client as clientmod

    monkeypatch.setattr(
        clientmod.NexusClient,
        "run_show",
        lambda self, command, parse=True: {
            "command": command,
            "parsed": [{"host": self.host}],
            "raw": None,
            "parser": "json",
        },
    )
    code = run(
        ["interface", "list", "--group", "dc", "--inventory", _inventory(tmp_path), "--json"]
    )
    lines = [json.loads(x) for x in capsys.readouterr().out.strip().splitlines()]
    assert code == 0
    assert {d["device"] for d in lines} == {"a", "b"}
    assert all(d["ok"] for d in lines)


def test_fanout_partial_exit(capsys, tmp_path, monkeypatch):
    from nxstate import client as clientmod
    from nxstate.errors import unreachable

    def rs(self, command, parse=True):
        if self.host == "10.0.0.2":
            raise unreachable(self.host, "down")
        return {"command": command, "parsed": [{"ok": 1}], "raw": None, "parser": "json"}

    monkeypatch.setattr(clientmod.NexusClient, "run_show", rs)
    code = run(["mac", "list", "--group", "dc", "--inventory", _inventory(tmp_path), "--json"])
    lines = [json.loads(x) for x in capsys.readouterr().out.strip().splitlines()]
    assert code == 15  # PARTIAL
    assert {d["device"]: d["ok"] for d in lines} == {"a": True, "b": False}


def test_single_device_from_inventory_is_clean(capsys, tmp_path, monkeypatch):
    # One resolved device → normal (non-NDJSON) output, not a fan-out envelope.
    from nxstate import client as clientmod

    monkeypatch.setattr(
        clientmod.NexusClient,
        "run_show",
        lambda self, command, parse=True: {
            "command": command,
            "parsed": [{"id": "1"}],
            "raw": None,
            "parser": "json",
        },
    )
    code = run(["vlan", "list", "--device", "a", "--inventory", _inventory(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    assert json.loads(out) == [{"id": "1"}]  # bare list, no per-device wrapper


def test_flag_after_subcommand_position(capsys):
    # Global flags must work in any position (the kong-parity requirement).
    code = run(["system", "version", "--host", "sw1", "--format", "tsv"])
    assert code == 0


def test_auth_logout_no_entry(capsys, monkeypatch):
    import keyring

    monkeypatch.setattr(keyring, "get_password", lambda *a, **k: None)
    code = run(["auth", "logout", "--host", "sw1", "-u", "netops", "--json"])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True and payload["removed"] is False
