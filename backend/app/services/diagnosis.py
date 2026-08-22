import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from types import SimpleNamespace

from flask import current_app

from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.models.diagnosis import ParameterCollectionConfig, ParameterCollectionSnapshot, SUPPORTED_DIAGNOSIS_DB_TYPES
from app.services.backup_agent_client import collect_parameters_on_agent
from app.services.parameter_collector import collect_database_parameters
from app.utils.crypto import decrypt_secret


_COLLECTION_LOCK = threading.Lock()


def get_or_create_parameter_collection_config():
    config = ParameterCollectionConfig.query.first()
    if config:
        return config
    config = ParameterCollectionConfig(
        enabled=True,
        cron_expr="0 0 * * *",
        db_types_json=list(SUPPORTED_DIAGNOSIS_DB_TYPES),
        timeout_seconds=15,
        max_workers=5,
        retention_versions=3,
    )
    db.session.add(config)
    db.session.commit()
    return config


def update_parameter_collection_config(config, payload):
    if "enabled" in payload:
        config.enabled = bool(payload.get("enabled"))
    if "cron_expr" in payload:
        value = str(payload.get("cron_expr") or "").strip()
        if not value:
            return "cron_expr is required"
        config.cron_expr = value[:64]
    if "db_types" in payload:
        values = payload.get("db_types")
        if not isinstance(values, list):
            return "db_types must be an array"
        selected = [item for item in SUPPORTED_DIAGNOSIS_DB_TYPES if item in values]
        if not selected:
            return "at least one db_type is required"
        config.db_types_json = selected
    for key, minimum, maximum in (
        ("timeout_seconds", 3, 120),
        ("max_workers", 1, 20),
        ("retention_versions", 1, 50),
    ):
        if key not in payload:
            continue
        try:
            value = int(payload.get(key))
        except (TypeError, ValueError):
            return f"{key} must be an integer"
        setattr(config, key, max(minimum, min(value, maximum)))
    return None


def _instance_payload(instance, timeout_seconds):
    return {
        "id": instance.id,
        "db_type": instance.db_type,
        "host_input": instance.host_input,
        "resolved_ip": instance.resolved_ip,
        "port": instance.port,
        "username": instance.username,
        "extra_json": instance.extra_json if isinstance(instance.extra_json, dict) else {},
        "access_mode": instance.access_mode or "server",
        "probe_agent_id": instance.probe_agent_id,
        "probe_agent_url": instance.probe_agent.url if instance.probe_agent else None,
        "probe_agent_api_key": instance.probe_agent.api_key if instance.probe_agent else "",
        "probe_timeout_seconds": timeout_seconds,
    }


def _collect_one(instance_payload, password, timeout_seconds, prepare_error=None):
    started = datetime.utcnow()
    try:
        if prepare_error:
            raise RuntimeError(prepare_error)
        if instance_payload.get("access_mode") == "agent":
            parameters = collect_parameters_on_agent(SimpleNamespace(**instance_payload), password, timeout_seconds)
            source = "agent"
        else:
            parameters = collect_database_parameters(instance_payload, password, timeout_seconds)
            source = "server"
        return {
            "status": "success",
            "parameters": parameters,
            "source": source,
            "error": None,
            "duration_ms": int((datetime.utcnow() - started).total_seconds() * 1000),
        }
    except Exception as exc:
        return {
            "status": "failed",
            "parameters": [],
            "source": "agent" if instance_payload.get("access_mode") == "agent" else "server",
            "error": str(exc)[:4000],
            "duration_ms": int((datetime.utcnow() - started).total_seconds() * 1000),
        }


def _prune_instance_versions(instance_id, retention=3):
    stale = (
        ParameterCollectionSnapshot.query.filter_by(instance_id=instance_id)
        .order_by(ParameterCollectionSnapshot.collected_at.desc(), ParameterCollectionSnapshot.id.desc())
        .offset(max(1, int(retention)))
        .all()
    )
    for row in stale:
        db.session.delete(row)


def prune_parameter_versions(retention):
    retention = max(1, min(int(retention or 3), 50))
    instance_ids = [
        row[0]
        for row in db.session.query(ParameterCollectionSnapshot.instance_id).distinct().all()
    ]
    for instance_id in instance_ids:
        _prune_instance_versions(instance_id, retention)
    return len(instance_ids)


def is_parameter_collection_running():
    acquired = _COLLECTION_LOCK.acquire(blocking=False)
    if acquired:
        _COLLECTION_LOCK.release()
        return False
    return True


def run_parameter_collection():
    if not _COLLECTION_LOCK.acquire(blocking=False):
        return {"ok": False, "message": "parameter collection is already running"}
    try:
        config = get_or_create_parameter_collection_config()
        instances = (
            DatabaseInstance.query.filter(
                DatabaseInstance.enabled.is_(True),
                DatabaseInstance.db_type.in_(config.selected_db_types()),
            )
            .order_by(DatabaseInstance.id.asc())
            .all()
        )
        timeout = max(3, min(int(config.timeout_seconds or 15), 120))
        work = []
        for item in instances:
            prepare_error = None
            try:
                password = decrypt_secret(item.password_encrypted) if item.password_encrypted else ""
            except Exception as exc:
                password = ""
                prepare_error = f"decrypt failed: {exc}"
            work.append((_instance_payload(item, timeout), password, prepare_error))
        results = {}
        executor = ThreadPoolExecutor(max_workers=max(1, min(int(config.max_workers or 5), 20, len(work) or 1)))
        try:
            futures = {
                executor.submit(_collect_one, payload, password, timeout, prepare_error): payload["id"]
                for payload, password, prepare_error in work
            }
            for future in as_completed(futures):
                results[futures[future]] = future.result()
        finally:
            executor.shutdown(wait=True)

        collected_at = datetime.utcnow()
        success = 0
        failed = 0
        for instance in instances:
            result = results.get(instance.id) or {
                "status": "failed", "parameters": [], "source": "server",
                "error": "collector returned no result", "duration_ms": None,
            }
            snapshot = ParameterCollectionSnapshot(
                instance_id=instance.id,
                collected_at=collected_at,
                status=result["status"],
                error_message=result.get("error"),
                parameter_count=len(result.get("parameters") or []),
                parameters_json=result.get("parameters") or [],
                source=result.get("source") or "server",
                duration_ms=result.get("duration_ms"),
            )
            db.session.add(snapshot)
            db.session.flush()
            _prune_instance_versions(instance.id, config.retention_versions or 3)
            if result["status"] == "success":
                success += 1
            else:
                failed += 1

        config.last_run_at = collected_at
        config.last_status = "success" if failed == 0 else ("partial" if success else "failed")
        config.last_message = f"共 {len(instances)} 个实例，成功 {success}，失败 {failed}"
        db.session.commit()
        return {"ok": failed == 0, "total": len(instances), "success": success, "failed": failed}
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("parameter collection failed: %s", exc)
        try:
            config = get_or_create_parameter_collection_config()
            config.last_run_at = datetime.utcnow()
            config.last_status = "failed"
            config.last_message = str(exc)[:512]
            db.session.commit()
        except Exception:
            db.session.rollback()
        return {"ok": False, "message": str(exc)}
    finally:
        _COLLECTION_LOCK.release()
