"""Detached backup worker used only when Agent restart recovery is enabled."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from app import create_app
from app.api.routes import agent as agent_routes
from app.config import get_config


def _write_json_atomic(path: Path, payload: dict):
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def main(task_dir_value: str) -> int:
    task_dir = Path(task_dir_value).resolve()
    spec_path = task_dir / "input.json"
    result_path = task_dir / "result.json"
    try:
        with spec_path.open("r", encoding="utf-8") as handle:
            spec = json.load(handle)
        base_config = get_config()

        class WorkerConfig(base_config):
            AGENT_RECOVERY_ENABLED = False

        app = create_app(WorkerConfig)
        with app.app_context():
            result = agent_routes._run_backup(
                spec["policy"],
                spec["instance"],
                False,
                task_id=None,
            )
    except Exception as exc:
        result = {"ok": False, "message": str(exc)}

    _write_json_atomic(
        result_path,
        {
            "task_id": task_dir.name,
            "finished_at": datetime.utcnow().isoformat() + "Z",
            "result": result,
        },
    )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m app.services.backup_task_worker TASK_DIR")
    raise SystemExit(main(sys.argv[1]))
