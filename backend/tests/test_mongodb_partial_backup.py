import pytest

from app.api.routes.backups import _normalize_mongo_backup
from app.extensions import db
from app.models.backup import BackupPolicy
from app.models.db_asset import DatabaseInstance
from app.services import backup_agent_client
from app.services import backup_executor


def test_normalize_mongo_partial_backup_supports_one_database_and_collection_exclusions():
    value, error = _normalize_mongo_backup(
        "mongodb",
        {
            "mode": "partial",
            "database": " app ",
            "excluded_collections": [" audit_events ", " temporary_data "],
        },
    )

    assert error is None
    assert value == {
        "mode": "partial",
        "database": "app",
        "excluded_collections": ["audit_events", "temporary_data"],
    }


def test_normalize_mongo_full_backup_clears_partial_scope():
    value, error = _normalize_mongo_backup(
        "mongodb",
        {"mode": "full", "database": "app", "excluded_collections": ["audit"]},
    )

    assert error is None
    assert value == {"mode": "full", "database": "", "excluded_collections": []}


def test_normalize_mongo_partial_backup_converts_unambiguous_legacy_scope():
    value, error = _normalize_mongo_backup(
        "mongodb",
        {"mode": "partial", "exclusions": [
            {"database": " app ", "collection": " audit_events "},
            {"database": "app", "collection": "temporary_data"},
        ]},
    )

    assert error is None
    assert value == {
        "mode": "partial",
        "database": "app",
        "excluded_collections": ["audit_events", "temporary_data"],
    }


@pytest.mark.parametrize("config", [
    {"mode": "partial", "database": "", "excluded_collections": []},
    {"mode": "partial", "database": "app", "excluded_collections": [""]},
    {"mode": "partial", "database": "app", "excluded_collections": ["events", " events "]},
    {"mode": "partial", "exclusions": [{"database": "app", "collection": ""}]},
    {"mode": "partial", "exclusions": [
        {"database": "app", "collection": "events"},
        {"database": "logs", "collection": "events"},
    ]},
])
def test_normalize_mongo_partial_backup_rejects_invalid_scope(config):
    _value, error = _normalize_mongo_backup("mongodb", config)
    assert error


def test_build_partial_mongo_command_targets_one_database_and_excludes_collections(tmp_path):
    instance = type("Instance", (), {
        "resolved_ip": "10.0.0.8", "host_input": "mongo", "port": 27017,
        "username": "backup",
    })()
    output_file = str(tmp_path / "mongo.archive")

    command = backup_executor._build_partial_mongo_command(
        instance,
        "secret",
        output_file,
        True,
        "mongodump",
        "app",
        ["audit", "temporary_data"],
    )

    assert command[0] == "mongodump"
    assert f"--archive={output_file}" in command
    assert command.count("--db=app") == 1
    assert "--excludeCollection=audit" in command
    assert "--excludeCollection=temporary_data" in command
    assert "--gzip" in command
    assert "--authenticationDatabase=admin" in command
    assert all(isinstance(argument, str) for argument in command)


def test_backup_timeout_is_seven_days():
    assert backup_executor.BACKUP_TIMEOUT_SECONDS == 604_800


def test_partial_mongo_dry_run_returns_one_command_without_database_discovery(app, tmp_path, monkeypatch):
    with app.app_context():
        instance = DatabaseInstance(
            name="mongo-1",
            db_type="mongodb",
            host_input="mongo.internal",
            resolved_ip="10.0.0.8",
            port=27017,
            username="backup",
            extra_json={"auth_source": "backup_auth"},
        )
        db.session.add(instance)
        db.session.flush()
        policy = BackupPolicy(
            name="mongo-partial",
            target_type="instance",
            target_id=instance.id,
            db_type="mongodb",
            backup_type="full",
            tool_name="mongodump",
            cron_expr="0 2 * * *",
            storage_path=str(tmp_path),
            retain_days=7,
            compress=True,
            enabled=True,
            extra_json={
                "compress_method": "gzip",
                "mongo_backup": {
                    "mode": "partial",
                    "database": "app",
                    "excluded_collections": ["audit", "temporary_data"],
                },
            },
        )
        db.session.add(policy)
        db.session.commit()
        monkeypatch.setattr(backup_executor, "_ensure_disk_space", lambda _path: True)
        monkeypatch.setattr(backup_executor, "_get_tool_path", lambda _policy: "mongodump")

        result = backup_executor.run_backup_policy(policy.id, dry_run=True)

    assert result["ok"] is True
    assert result["command"].count("--db=app") == 1
    assert "--excludeCollection=audit" in result["command"]
    assert "--excludeCollection=temporary_data" in result["command"]
    assert "--authenticationDatabase=backup_auth" in result["command"]
    assert all(isinstance(argument, str) for argument in result["command"])


def test_remote_backup_payload_uses_asset_connection_auth_database():
    instance = DatabaseInstance(
        name="mongo-remote",
        db_type="mongodb",
        host_input="mongo.internal",
        port=27017,
        username="backup",
        extra_json={"auth_db": "asset_auth"},
    )
    policy = BackupPolicy(
        name="mongo-remote-policy",
        target_type="instance",
        target_id=1,
        db_type="mongodb",
        backup_type="full",
        tool_name="mongodump",
        cron_expr="0 2 * * *",
        storage_path="/tmp",
        retain_days=7,
        extra_json={"mongo_backup": {"mode": "full", "auth_database": "policy_auth"}},
    )

    payload = backup_agent_client._build_payload_from_policy(policy, instance)

    assert payload["policy"]["mongo_backup"]["auth_database"] == "asset_auth"
