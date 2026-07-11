from app.api.routes import agent


def test_agent_builds_partial_mongo_commands_and_skips_database(tmp_path):
    instance = {"resolved_ip": "10.0.0.8", "host_input": "mongo", "port": 27017, "username": "backup", "password": "secret"}
    commands, skipped = agent._build_partial_mongo_commands(
        instance, str(tmp_path), "mongodump", ["app", "logs"],
        [{"database": "logs", "collection": ""}, {"database": "app", "collection": "audit"}],
    )

    assert skipped == ["logs"]
    assert len(commands) == 1
    assert "--db=app" in commands[0]
    assert "--excludeCollection=audit" in commands[0]


def test_agent_backup_timeout_is_thirty_days():
    assert agent.BACKUP_TIMEOUT_SECONDS == 2_592_000
