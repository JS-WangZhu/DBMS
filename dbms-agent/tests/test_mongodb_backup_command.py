from app.api.routes.agent import _build_mongo_command


def test_agent_mongo_full_backup_excludes_local_database():
    command = _build_mongo_command(
        instance={
            "host_input": "mongo-1",
            "resolved_ip": None,
            "port": 27017,
            "username": "backup",
            "password": "secret",
        },
        output_file="/backup/mongo.archive",
        compress=True,
        tool_path="mongodump",
    )

    assert "--nsExclude=local.*" in command


def test_agent_mongo_stdout_archive_backup_excludes_local_database():
    command = _build_mongo_command(
        instance={
            "host_input": "mongo-1",
            "resolved_ip": "10.0.0.5",
            "port": 27017,
        },
        output_file=None,
        compress=False,
        tool_path="mongodump",
        archive_to_stdout=True,
    )

    assert "--nsExclude=local.*" in command
