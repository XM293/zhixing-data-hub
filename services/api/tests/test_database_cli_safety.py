from __future__ import annotations

import json

import pytest

from zhixing_api.database_cli import run


def test_demo_retire_requires_backup_id_and_test_database(tmp_path, monkeypatch, capsys):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "version": 1, "enterprise_id": "legal-synthetic", "tables": [],
    }), encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'verify.db'}")

    with pytest.raises(SystemExit):
        run(["demo-retire", "--manifest", str(manifest), "--dry-run"])
    assert "backup-id" in capsys.readouterr().err

    assert (
        run(
            [
                "demo-retire",
                "--backup-id",
                "backup-synthetic-001",
                "--manifest",
                str(manifest),
                "--dry-run",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["backup_id"] == "backup-synthetic-001"
    assert payload["impact"]["tables"] == []


def test_bootstrap_rejects_non_test_database(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'local.db'}")
    assert run(["production-bootstrap", "--manifest", str(manifest), "--dry-run"]) == 1
