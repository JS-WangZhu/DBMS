import pytest

from app.api.routes.backups import _normalize_mongo_backup
from app.services import backup_executor


def test_normalize_mongo_partial_backup_supports_database_and_collection_exclusions():
    value, error = _normalize_mongo_backup(
        "mongodb",
        {"mode": "partial", "exclusions": [
            {"database": " logs ", "collection": ""},
            {"database": "app", "collection": " audit_events "},
        ]},
    )

    assert error is None
    assert value == {"mode": "partial", "exclusions": [
        {"database": "logs", "collection": ""},
        {"database": "app", "collection": "audit_events"},
    ]}


@pytest.mark.parametrize("config", [
    {"mode": "partial", "exclusions": []},
    {"mode": "partial", "exclusions": [{"database": "", "collection": "events"}]},
    {"mode": "partial", "exclusions": [
        {"database": "app", "collection": "events"},
        {"database": "app", "collection": "events"},
    ]},
    {"mode": "partial", "exclusions": [
        {"database": "app", "collection": ""},
        {"database": "app", "collection": "events"},
    ]},
])
def test_normalize_mongo_partial_backup_rejects_invalid_exclusions(config):
    _value, error = _normalize_mongo_backup("mongodb", config)
    assert error


def test_build_partial_mongo_commands_skips_database_and_excludes_collection(tmp_path):
    instance = type("Instance", (), {
        "resolved_ip": "10.0.0.8", "host_input": "mongo", "port": 27017,
        "username": "backup",
    })()
    commands, skipped = backup_executor._build_partial_mongo_commands(
        instance, "secret", str(tmp_path), "mongodump", ["admin", "app", "logs"],
        [{"database": "logs", "collection": ""}, {"database": "app", "collection": "audit"}],
    )

    assert skipped == ["logs"]
    assert len(commands) == 2
    app_command = next(command for command in commands if "--db=app" in command)
    assert "--excludeCollection=audit" in app_command
    assert all("--db=logs" not in command for command in commands)


def test_backup_timeout_is_thirty_days():
    assert backup_executor.BACKUP_TIMEOUT_SECONDS == 2_592_000
