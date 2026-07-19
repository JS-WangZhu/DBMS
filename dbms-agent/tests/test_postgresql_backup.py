from app.api.routes import agent as agent_routes


def test_build_postgresql_command_uses_asset_database_without_password():
    instance = {
        "resolved_ip": "10.0.0.9",
        "host_input": "postgres.internal",
        "port": 5432,
        "username": "backup",
        "password": "secret",
        "extra_json": {"database": "app", "sslmode": "verify-full"},
    }

    command = agent_routes._build_postgresql_command(
        instance, "/backup/app.sql", "/usr/bin/pg_dump"
    )
    env = agent_routes._postgresql_env(instance)

    assert "--dbname=app" in command
    assert "--format=custom" in command
    assert not any(item.startswith("--compress=") for item in command)
    assert "--file=/backup/app.sql" in command
    assert "secret" not in " ".join(command)
    assert env["PGPASSWORD"] == "secret"
    assert env["PGSSLMODE"] == "verify-full"


def test_postgresql_agent_dry_run_supports_zstd(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_routes, "_ensure_disk_space", lambda _path: True)
    policy = {
        "db_type": "postgresql",
        "tool_path": "pg_dump",
        "storage_path": str(tmp_path),
        "compress_method": "zstd",
        "postgresql_backup": {
            "format": "custom",
            "databases": [
                {"name": "reporting", "table_filter": {"mode": "exclude", "tables": ["public.events"]}},
                {"name": "archive", "table_filter": {"mode": "all", "tables": []}},
            ],
        },
    }
    instance = {
        "name": "postgresql-1",
        "host_input": "postgres.internal",
        "port": 5432,
        "username": "backup",
        "password": "secret",
        "extra_json": {"dbname": "reporting"},
    }

    result = agent_routes._run_backup(policy, instance, True)

    assert result["ok"] is True
    assert result["command"][0] == "pg_dump"
    assert len(result["commands"]) == 2
    assert "--dbname=reporting" in result["commands"][0]
    assert "--exclude-table=public.events" in result["commands"][0]
    assert "--compress=zstd" in result["commands"][0]
    assert "--dbname=archive" in result["commands"][1]
    assert any(argument.startswith("--file=") and argument.endswith(".dump") for argument in result["command"])
    assert result["output_file"].endswith(".tar")
    assert "secret" not in " ".join(result["command"])


def test_postgresql_agent_supports_pg_dump_lz4_compression():
    command = agent_routes._build_postgresql_command(
        {"host_input": "postgres", "port": 5432, "username": "backup"},
        "/backup/app.dump", "pg_dump", compress_method="lz4",
    )
    assert "--compress=lz4" in command
