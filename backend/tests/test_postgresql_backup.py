from app.api.routes.backups import _normalize_postgresql_backup, _postgresql_role_text, list_managed_instances
from app.extensions import db
from app.models.backup import BackupPolicy
from app.models.db_asset import DatabaseInstance
from app.services import backup_agent_client, backup_executor


def _instance(**overrides):
    values = {
        "name": "postgresql-1",
        "db_type": "postgresql",
        "host_input": "postgres.internal",
        "resolved_ip": "10.0.0.9",
        "port": 5432,
        "username": "backup",
        "extra_json": {"database": "app", "sslmode": "require"},
    }
    values.update(overrides)
    return DatabaseInstance(**values)


def test_build_postgresql_command_uses_asset_database_without_password():
    instance = _instance()

    command = backup_executor._build_postgresql_command(
        instance, "/backup/app.sql", "/usr/bin/pg_dump"
    )
    env = backup_executor._postgresql_env(instance, "secret")

    assert command == [
        "/usr/bin/pg_dump",
        "--host=10.0.0.9",
        "--port=5432",
        "--username=backup",
        "--dbname=app",
        "--format=custom",
        "--no-password",
        "--file=/backup/app.sql",
    ]
    assert "secret" not in " ".join(command)
    assert env["PGPASSWORD"] == "secret"
    assert env["PGSSLMODE"] == "require"


def test_postgresql_dry_run_builds_multi_database_custom_bundle(app, tmp_path, monkeypatch):
    with app.app_context():
        instance = _instance(resolved_ip=None)
        db.session.add(instance)
        db.session.flush()
        policy = BackupPolicy(
            name="postgresql-daily",
            target_type="instance",
            target_id=instance.id,
            db_type="postgresql",
            backup_type="full",
            tool_name="pg_dump",
            cron_expr="0 2 * * *",
            storage_path=str(tmp_path),
            retain_days=7,
            compress=True,
            enabled=True,
            extra_json={
                "compress_method": "gzip",
                "postgresql_backup": {
                    "format": "custom",
                    "databases": [
                        {"name": "app", "table_filter": {"mode": "exclude", "tables": ["public.audit_log"]}},
                        {"name": "reporting", "table_filter": {"mode": "all", "tables": []}},
                    ],
                },
            },
        )
        db.session.add(policy)
        db.session.commit()
        monkeypatch.setattr(backup_executor, "_ensure_disk_space", lambda _path: True)

        result = backup_executor.run_backup_policy(policy.id, dry_run=True)

    assert result["ok"] is True
    assert result["command"][0] == "pg_dump"
    assert "--host=postgres.internal" in result["command"]
    assert len(result["commands"]) == 2
    assert "--dbname=app" in result["commands"][0]
    assert "--exclude-table=public.audit_log" in result["commands"][0]
    assert "--dbname=reporting" in result["commands"][1]
    assert "--format=custom" in result["commands"][0]
    assert "--compress=gzip" in result["commands"][0]
    assert any(argument.startswith("--file=") and argument.endswith(".dump") for argument in result["commands"][0])
    assert result["output_file"].endswith(".tar")
    assert "secret" not in " ".join(result["command"])


def test_remote_postgresql_payload_keeps_asset_connection_options():
    instance = _instance(id=9)
    policy = BackupPolicy(
        name="postgresql-remote",
        target_type="instance",
        target_id=9,
        db_type="postgresql",
        backup_type="full",
        tool_name="pg_dump",
        cron_expr="0 2 * * *",
        storage_path="/backup",
        retain_days=7,
        extra_json={
            "compress_method": "zstd",
            "postgresql_backup": {
                "format": "custom",
                "databases": [{"name": "app", "table_filter": {"mode": "all", "tables": []}}],
            },
        },
    )

    payload = backup_agent_client._build_payload_from_policy(policy, instance)

    assert payload["policy"]["db_type"] == "postgresql"
    assert payload["policy"]["tool_path"] == "pg_dump"
    assert payload["policy"]["compress_method"] == "zstd"
    assert policy.to_dict()["compress_method"] == "zstd"
    assert payload["policy"]["postgresql_backup"]["databases"][0]["name"] == "app"
    assert payload["instance"]["extra_json"] == {"database": "app", "sslmode": "require"}



def test_postgresql_backup_instance_role_text():
    assert _postgresql_role_text({"replication_role": "primary"}) == "主库"
    assert _postgresql_role_text({"replication_role": "standby"}) == "从库"
    assert _postgresql_role_text({}, fallback="只读节点") == "只读节点"
    assert _postgresql_role_text({}) == "未知"


def test_managed_postgresql_instances_use_snapshot_role(app, monkeypatch):
    with app.app_context():
        instance = _instance(resolved_ip=None)
        db.session.add(instance)
        db.session.commit()
        monkeypatch.setattr(
            "app.api.routes.backups.latest_payload_by_instance_ids",
            lambda db_type, instance_ids: {
                instance.id: {"ok": True, "ping_ok": True, "replication_role": "primary"}
            },
        )

        with app.test_request_context("/api/v1/backups/managed-instances?db_type=postgresql"):
            response, status_code = list_managed_instances.__wrapped__()

    assert status_code == 200
    assert response.get_json()["data"][0]["label"] == "postgresql-1 [主库] (postgres.internal:5432)"


def test_normalize_postgresql_backup_requires_database_and_deduplicates_tables():
    config, error = _normalize_postgresql_backup("postgresql", {"databases": []})
    assert config is None
    assert "at least one database" in error

    config, error = _normalize_postgresql_backup("postgresql", {
        "databases": [{
            "name": "app",
            "table_filter": {"mode": "exclude", "tables": ["public.audit", "public.audit"]},
        }],
    })
    assert error is None
    assert config == {
        "format": "custom",
        "databases": [{
            "name": "app",
            "table_filter": {"mode": "exclude", "tables": ["public.audit"]},
        }],
    }


def test_postgresql_bundle_contains_one_custom_dump_per_database(tmp_path, monkeypatch):
    staging = tmp_path / ".staging"
    output = tmp_path / "backup.tar"
    dump_one = staging / "001_app.dump"
    dump_two = staging / "002_reporting.dump"
    commands = [
        ["pg_dump", f"--file={dump_one}"],
        ["pg_dump", f"--file={dump_two}"],
    ]

    def fake_run(command, _log_id, env=None):
        target = next(item.split("=", 1)[1] for item in command if item.startswith("--file="))
        Path(target).write_bytes(b"PGDMP")

    from pathlib import Path
    import tarfile
    monkeypatch.setattr(backup_executor, "_run_registered_process", fake_run)
    backup_executor._run_postgresql_bundle(commands, str(staging), str(output), "gzip", 1, {})

    with tarfile.open(output, "r:") as archive:
        assert archive.getnames() == ["001_app.dump", "002_reporting.dump"]
    assert not staging.exists()


def test_postgresql_command_supports_pg_dump_compression_algorithms():
    instance = _instance()
    for method in ["default", "gzip", "lz4", "zstd", "none"]:
        command = backup_executor._build_postgresql_command(
            instance, "/backup/app.dump", "pg_dump", compress_method=method,
        )
        compress_args = [item for item in command if item.startswith("--compress=")]
        if method == "default":
            assert compress_args == []
        else:
            assert compress_args == [f"--compress={method}"]


def test_postgresql_lz4_is_serialized_and_sent_to_agent():
    instance = _instance(id=11)
    policy = BackupPolicy(
        name="postgresql-lz4", target_type="instance", target_id=11,
        db_type="postgresql", backup_type="full", tool_name="pg_dump",
        cron_expr="0 2 * * *", storage_path="/backup", retain_days=7,
        compress=True,
        extra_json={
            "compress_method": "lz4",
            "postgresql_backup": {"databases": [{"name": "app"}]},
        },
    )
    assert policy.to_dict()["compress_method"] == "lz4"
    assert backup_agent_client._build_payload_from_policy(policy, instance)["policy"]["compress_method"] == "lz4"
