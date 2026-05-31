import json
import subprocess
import sys
from datetime import datetime

import requests

from app.api.routes.data_access import _execute, pick_instance
from app.extensions import db
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.task_management import ScheduledTask, ScheduledTaskRun


VALID_TASK_TYPES = {"shell", "python", "http", "sql"}
VALID_SQL_DB_TYPES = {"mysql", "mongodb", "redis"}


def _truncate(value, limit=60000):
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_sql_payload(content: dict, instance: DatabaseInstance):
    db_type = instance.db_type
    if db_type == "mysql":
        return {
            "db_type": "mysql",
            "database": (content.get("database") or "").strip(),
            "sql": content.get("sql") or "",
        }
    if db_type == "mongodb":
        return {
            "db_type": "mongodb",
            "mongo_database": (content.get("database") or content.get("mongo_database") or "admin").strip() or "admin",
            "mongo_command": content.get("mongo_command") or content.get("sql") or "",
        }
    if db_type == "redis":
        query = content.get("query")
        if isinstance(query, dict):
            redis_query = query
        else:
            tokens = str(content.get("redis_command") or content.get("sql") or "").strip().split()
            redis_query = {"command": tokens[0].upper(), "args": tokens[1:]} if tokens else {}
        return {"db_type": "redis", "query": redis_query}
    return {}


def _run_shell(content: dict, timeout_seconds: int):
    script = content.get("script") or ""
    if not script.strip():
        raise ValueError("shell script is required")
    proc = subprocess.run(
        script,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "result": {"return_code": proc.returncode},
        "error": None if proc.returncode == 0 else f"shell exit code {proc.returncode}",
    }


def _run_python(content: dict, timeout_seconds: int):
    script = content.get("script") or ""
    if not script.strip():
        raise ValueError("python script is required")
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "result": {"return_code": proc.returncode},
        "error": None if proc.returncode == 0 else f"python exit code {proc.returncode}",
    }


def _run_http(content: dict, timeout_seconds: int):
    method = str(content.get("method") or "GET").strip().upper()
    url = str(content.get("url") or "").strip()
    if not url:
        raise ValueError("http url is required")
    headers = content.get("headers") if isinstance(content.get("headers"), dict) else {}
    body = content.get("body")
    kwargs = {"headers": headers, "timeout": timeout_seconds}
    if body not in (None, ""):
        if isinstance(body, (dict, list)):
            kwargs["json"] = body
        else:
            kwargs["data"] = str(body)
    response = requests.request(method, url, **kwargs)
    text = response.text or ""
    return {
        "ok": 200 <= response.status_code < 400,
        "stdout": _truncate(text),
        "stderr": "",
        "result": {
            "status_code": response.status_code,
            "headers": dict(response.headers),
        },
        "error": None if 200 <= response.status_code < 400 else f"http status {response.status_code}",
    }


def _target_sql_instances(content: dict):
    db_type = str(content.get("db_type") or "").strip().lower()
    if db_type not in VALID_SQL_DB_TYPES:
        raise ValueError("sql db_type must be mysql/mongodb/redis")
    target_mode = str(content.get("target_mode") or "cluster").strip().lower()
    if target_mode == "all":
        return DatabaseInstance.query.filter_by(db_type=db_type, enabled=True).order_by(DatabaseInstance.id.asc()).all()
    if target_mode == "instance":
        instance_id = _safe_int(content.get("instance_id"))
        instance = DatabaseInstance.query.get(instance_id)
        if not instance or instance.db_type != db_type:
            raise ValueError("target instance not found")
        return [instance]
    cluster_id = _safe_int(content.get("cluster_id"))
    cluster = DatabaseCluster.query.get(cluster_id)
    if not cluster or cluster.db_type != db_type:
        raise ValueError("target cluster not found")
    route_mode = str(content.get("route_mode") or "auto").strip().lower()
    instance = pick_instance(db_type, cluster.id, content.get("instance_id"), for_change=content.get("sql_operation") == "change", route_mode=route_mode)
    if not instance:
        raise ValueError("no available instance")
    return [instance]


def _run_sql(content: dict, timeout_seconds: int):
    sql_operation = str(content.get("sql_operation") or "query").strip().lower()
    for_change = sql_operation == "change"
    rows = []
    success = 0
    failed = 0
    for index, instance in enumerate(_target_sql_instances(content), start=1):
        started_at = datetime.utcnow()
        ok = False
        err = None
        result = None
        try:
            payload = _build_sql_payload(content, instance)
            ok, err, result = _execute(instance.db_type, instance, payload, timeout_seconds, for_change=for_change)
        except Exception as exc:
            err = str(exc) or "execute failed"
        finished_at = datetime.utcnow()
        item = {
            "index": index,
            "instance_id": instance.id,
            "instance_name": instance.name,
            "db_type": instance.db_type,
            "host": instance.resolved_ip or instance.host_input,
            "port": instance.port,
            "ok": bool(ok),
            "error": err,
            "result": result,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
        }
        rows.append(item)
        if ok:
            success += 1
        else:
            failed += 1
        db.session.rollback()
    return {
        "ok": failed == 0,
        "stdout": json.dumps({"total": len(rows), "success": success, "failed": failed}, ensure_ascii=False),
        "stderr": "",
        "result": {"items": rows, "total": len(rows), "success": success, "failed": failed},
        "error": None if failed == 0 else f"{failed} sql target(s) failed",
    }


def run_scheduled_task(task_id: int, trigger_type: str = "manual", retry_of_id: int = None):
    task = ScheduledTask.query.get(task_id)
    if not task:
        return {"ok": False, "message": "task not found"}
    retry_of = ScheduledTaskRun.query.get(retry_of_id) if retry_of_id else None
    attempt = (retry_of.attempt + 1) if retry_of else 1
    started = datetime.utcnow()
    run = ScheduledTaskRun(
        task_id=task.id,
        status="running",
        trigger_type=trigger_type,
        retry_of_id=retry_of_id,
        attempt=attempt,
        started_at=started,
    )
    db.session.add(run)
    db.session.commit()

    content = task.content_json if isinstance(task.content_json, dict) else {}
    timeout_seconds = max(1, min(_safe_int(task.timeout_seconds, 300), 86400))
    try:
        if task.task_type == "shell":
            outcome = _run_shell(content, timeout_seconds)
        elif task.task_type == "python":
            outcome = _run_python(content, timeout_seconds)
        elif task.task_type == "http":
            outcome = _run_http(content, timeout_seconds)
        elif task.task_type == "sql":
            outcome = _run_sql(content, timeout_seconds)
        else:
            raise ValueError("unsupported task type")
        run.status = "success" if outcome.get("ok") else "failed"
        run.stdout = _truncate(outcome.get("stdout"))
        run.stderr = _truncate(outcome.get("stderr"))
        run.error_message = _truncate(outcome.get("error"), 4000) if outcome.get("error") else None
        run.result_json = outcome.get("result") if isinstance(outcome.get("result"), dict) else {"result": outcome.get("result")}
    except subprocess.TimeoutExpired as exc:
        run.status = "failed"
        run.stdout = _truncate(exc.stdout)
        run.stderr = _truncate(exc.stderr)
        run.error_message = f"task timeout after {timeout_seconds}s"
        run.result_json = {"timeout_seconds": timeout_seconds}
    except Exception as exc:
        run.status = "failed"
        run.error_message = _truncate(str(exc), 4000)
        run.result_json = {}
    finally:
        finished = datetime.utcnow()
        run.finished_at = finished
        run.duration_ms = int((finished - started).total_seconds() * 1000)
        task.last_run_at = finished
        task.last_status = run.status
        task.last_message = run.error_message or (run.stdout[:512] if run.stdout else None)
        db.session.commit()

    return {"ok": run.status == "success", "data": run.to_dict(), "message": run.error_message or "ok"}
