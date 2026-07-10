from __future__ import annotations

import json

from als_intel import cli


def test_source_capabilities_json_schema_and_count(capsys, monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["als-intel", "source-capabilities", "--as-json", "--only-public", "--only-runnable"])
    cli.main()
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert isinstance(payload, dict)
    assert int(payload["total"]) == len(payload["rows"])
    assert int(payload["total"]) >= 15

    names = {str(row["source"]) for row in payload["rows"]}
    assert "pubmed" in names
    assert "ctgov" in names
    assert "kegg" in names
    assert "open_targets" in names
    assert "fda_labels" in names

    for row in payload["rows"]:
        assert isinstance(row, dict)
        assert set(row.keys()) == {
            "source",
            "status",
            "stubbed",
            "public",
            "requires_credentials",
            "supports_incremental",
            "supports_metadata_stage",
            "notes",
        }
        assert row["status"] == "runnable"
        assert row["stubbed"] is False
        assert row["public"] is True
        assert row["requires_credentials"] is False
        assert row["supports_incremental"] is True


def test_source_capabilities_plain_text_mode(capsys, monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["als-intel", "source-capabilities", "--only-public"])
    cli.main()
    output = capsys.readouterr().out
    assert "total:" in output
    assert "pubmed: runnable" in output
    assert "public=true" in output
