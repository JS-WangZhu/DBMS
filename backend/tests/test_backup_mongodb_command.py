from types import SimpleNamespace

from app.services.backup_executor import _build_mongo_command


def test_mongo_full_backup_excludes_local_database():
    instance = SimpleNamespace(
        resolved_ip=None,
        host_input="mongo-1",
        port=27017,
        username="backup",
    )

    command = _build_mongo_command(
        instance=instance,
        password="secret",
        output_file="/backup/mongo.archive",
        compress=True,
        tool_path="mongodump",
    )

    assert "--nsExclude=local.*" in command


def test_mongo_stdout_archive_backup_excludes_local_database():
    instance = SimpleNamespace(
        resolved_ip="10.0.0.5",
        host_input="mongo-1",
        port=27017,
        username=None,
    )

    command = _build_mongo_command(
        instance=instance,
        password="",
        output_file=None,
        compress=False,
        tool_path="mongodump",
        archive_to_stdout=True,
    )

    assert "--nsExclude=local.*" in command
