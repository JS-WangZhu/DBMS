from sqlalchemy import String, cast, or_

from app.extensions import db
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.services.dns_resolver import resolve_and_update_instance, resolve_host
from app.utils.crypto import encrypt_secret

VALID_DB_TYPES = {"mysql", "mongodb", "redis", "doris"}


def _to_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_node_exporter(node_exporter):
    raw = node_exporter if isinstance(node_exporter, dict) else {}
    mode = str(raw.get("mode") or "same_host").strip().lower()
    if mode not in {"same_host", "custom"}:
        mode = "same_host"

    normalized = {
        "enabled": _to_bool(raw.get("enabled"), default=True),
        "mode": mode,
    }

    if mode == "custom":
        normalized["address"] = str(raw.get("address") or "").strip()
    else:
        normalized["port"] = max(1, min(_to_int(raw.get("port"), 9100), 65535))

    return normalized


def _normalize_extra_json(extra_json):
    normalized = dict(extra_json) if isinstance(extra_json, dict) else {}
    domain = str(normalized.get("domain") or "").strip()
    if domain:
        normalized["domain"] = domain
    else:
        normalized.pop("domain", None)
    physical_address = str(normalized.get("physical_address") or "").strip()
    if physical_address:
        normalized["physical_address"] = physical_address
    else:
        normalized.pop("physical_address", None)
    normalized["node_exporter"] = _normalize_node_exporter(normalized.get("node_exporter"))
    return normalized


def _canonical_host(host_input, resolved_ip=None, extra_json=None):
    domain = ""
    if isinstance(extra_json, dict):
        domain = str(extra_json.get("domain") or "").strip()
    target = domain or host_input
    host = (resolved_ip or resolve_host(target) or target or "").strip().lower()
    return host


def _validate_instance_uniqueness_in_cluster(db_type, cluster_id, host_input, port, extra_json=None, exclude_id=None):
    if cluster_id in (None, ""):
        return None

    try:
        cluster_id_int = int(cluster_id)
        port_int = int(port)
    except (TypeError, ValueError):
        return "cluster_id and port must be valid integers"

    current_host = _canonical_host(host_input=host_input, extra_json=extra_json)
    query = DatabaseInstance.query.filter_by(db_type=db_type, cluster_id=cluster_id_int, port=port_int)
    if exclude_id is not None:
        query = query.filter(DatabaseInstance.id != int(exclude_id))

    rows = query.all()
    for row in rows:
        existing_host = _canonical_host(host_input=row.host_input, resolved_ip=row.resolved_ip, extra_json=row.extra_json)
        if existing_host == current_host:
            return f"duplicate instance in cluster by ip+port: {current_host}:{port_int}"

    return None


def _validate_cluster_binding(cluster_id, db_type):
    if cluster_id in (None, ""):
        return None, None

    try:
        cluster_id_int = int(cluster_id)
    except (TypeError, ValueError):
        return None, "cluster_id must be an integer"

    cluster = DatabaseCluster.query.get(cluster_id_int)
    if not cluster:
        return None, "cluster not found"
    if cluster.db_type != db_type:
        return None, f"cluster db_type mismatch: expected {db_type}, got {cluster.db_type}"

    return cluster_id_int, None


def list_instances(db_type=None, enabled=None):
    query = DatabaseInstance.query
    if db_type:
        query = query.filter_by(db_type=db_type)
    if enabled is not None:
        query = query.filter_by(enabled=enabled)
    return query.order_by(DatabaseInstance.id.desc()).all()


def list_instances_paginated(db_type=None, enabled=None, page=1, page_size=20, keyword=None, cluster_id=None, namespace=None):
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(page_size)
    except (TypeError, ValueError):
        page_size = 20

    page = max(page, 1)
    page_size = max(1, min(page_size, 200))

    query = DatabaseInstance.query
    if db_type:
        query = query.filter_by(db_type=db_type)
    if enabled is not None:
        query = query.filter_by(enabled=enabled)
    if cluster_id not in (None, ""):
        try:
            query = query.filter_by(cluster_id=int(cluster_id))
        except (TypeError, ValueError):
            query = query.filter(DatabaseInstance.id == -1)
    namespace_text = str(namespace or "").strip()
    if namespace_text:
        query = query.join(DatabaseCluster, DatabaseCluster.id == DatabaseInstance.cluster_id).filter(DatabaseCluster.namespace == namespace_text)
    keyword_text = str(keyword or "").strip()
    if keyword_text:
        pattern = f"%{keyword_text}%"
        query = query.filter(
            or_(
                DatabaseInstance.name.ilike(pattern),
                DatabaseInstance.host_input.ilike(pattern),
                DatabaseInstance.resolved_ip.ilike(pattern),
                DatabaseInstance.username.ilike(pattern),
                DatabaseInstance.role_label.ilike(pattern),
                cast(DatabaseInstance.extra_json, String).ilike(pattern),
                cast(DatabaseInstance.port, String).ilike(pattern),
            )
        )

    total = query.count()
    items = query.order_by(DatabaseInstance.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return items, total, page, page_size


def create_instance(payload: dict, db_type: str):
    required = ["name", "host_input", "port"]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        return None, f"missing fields: {', '.join(missing)}"

    if db_type not in VALID_DB_TYPES:
        return None, "invalid db_type"

    cluster_id, cluster_err = _validate_cluster_binding(payload.get("cluster_id"), db_type=db_type)
    if cluster_err:
        return None, cluster_err

    normalized_extra_json = _normalize_extra_json(payload.get("extra_json"))
    uniqueness_err = _validate_instance_uniqueness_in_cluster(
        db_type=db_type,
        cluster_id=cluster_id,
        host_input=payload["host_input"],
        port=payload["port"],
        extra_json=normalized_extra_json,
    )
    if uniqueness_err:
        return None, uniqueness_err

    instance = DatabaseInstance(
        name=payload["name"],
        db_type=db_type,
        host_input=payload["host_input"],
        port=int(payload["port"]),
        username=payload.get("username"),
        password_encrypted=encrypt_secret(payload["password"]) if payload.get("password") else None,
        cluster_id=cluster_id,
        role_label=None if db_type == "mysql" else payload.get("role_label"),
        is_read_only=bool(payload.get("is_read_only", False)),
        enabled=bool(payload.get("enabled", True)),
        extra_json=normalized_extra_json,
    )

    db.session.add(instance)
    db.session.flush()
    resolve_and_update_instance(instance)
    db.session.commit()
    return instance, None


def update_instance(instance: DatabaseInstance, payload: dict):
    if "cluster_id" in payload:
        cluster_id, cluster_err = _validate_cluster_binding(payload.get("cluster_id"), db_type=instance.db_type)
        if cluster_err:
            raise ValueError(cluster_err)
        instance.cluster_id = cluster_id

    for field in ["name", "host_input", "port", "username", "is_read_only", "enabled"]:
        if field in payload:
            setattr(instance, field, payload[field])

    if instance.db_type != "mysql" and "role_label" in payload:
        instance.role_label = payload.get("role_label")

    merged_extra_json = instance.extra_json
    if "extra_json" in payload:
        merged_extra_json = _normalize_extra_json(payload.get("extra_json"))

    target_cluster_id = instance.cluster_id
    target_host_input = payload.get("host_input", instance.host_input)
    target_port = payload.get("port", instance.port)

    uniqueness_err = _validate_instance_uniqueness_in_cluster(
        db_type=instance.db_type,
        cluster_id=target_cluster_id,
        host_input=target_host_input,
        port=target_port,
        extra_json=merged_extra_json,
        exclude_id=instance.id,
    )
    if uniqueness_err:
        raise ValueError(uniqueness_err)

    if "password" in payload:
        instance.password_encrypted = encrypt_secret(payload["password"]) if payload["password"] else None

    domain_changed = False
    if "extra_json" in payload:
        old_extra = instance.extra_json if isinstance(instance.extra_json, dict) else {}
        old_domain = str(old_extra.get("domain") or "").strip()
        new_domain = str((merged_extra_json or {}).get("domain") or "").strip()
        domain_changed = old_domain != new_domain
        instance.extra_json = merged_extra_json

    if "host_input" in payload or domain_changed:
        resolve_and_update_instance(instance)

    db.session.commit()
    return instance
