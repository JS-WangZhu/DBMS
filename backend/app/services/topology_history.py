"""
MongoDB / Redis 集群复制拓扑提取、指纹与去重写入（audit_logs）。
拓扑变更历史由定时采集（job_monitor_collect）落盘到 audit_logs，前端从 audit_logs 分页读取。
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.db_asset import DatabaseCluster

MONGO_TOPOLOGY_ACTION = "cluster.mongodb.topology_change"
REDIS_TOPOLOGY_ACTION = "cluster.redis.topology_change"
MYSQL_TOPOLOGY_ACTION = "cluster.mysql.topology_change"

# 拓扑变更时间统一使用北京时间（UTC+8），前端通过 ISO 字符串内的时区后缀识别。
_BEIJING_TZ = timezone(timedelta(hours=8))


def _beijing_now_iso():
    """返回带北京时区后缀的当前时间 ISO 字符串。
    直接取服务器本地挂钟（假定部署环境本地时间即北京时间），附加 +08:00 后缀，
    避免 Unix epoch 被错配为北京时间时再 astimezone 多加一次 8 小时。
    """
    return datetime.now().replace(microsecond=0, tzinfo=_BEIJING_TZ).isoformat()


def _to_str(value):
    if value is None:
        return ""
    return str(value)


def _normalize_role(value):
    text = _to_str(value).strip().upper()
    if not text:
        return "UNKNOWN"
    return text


def extract_mongo_topology(instance_payloads):
    """
    从 MongoDB 集群快照列表聚合拓扑。
    instance_payloads: List[dict]，每项形如 { "instance_id", "instance_name", "host", "port", "payload" }
    """
    members_map = {}
    set_name = None

    for item in instance_payloads or []:
        payload = item.get("payload") if isinstance(item, dict) else None
        payload = payload if isinstance(payload, dict) else {}
        host = _to_str(item.get("host") or "").strip()
        port = item.get("port")
        try:
            port_int = int(port) if port not in (None, "") else None
        except (TypeError, ValueError):
            port_int = None
        self_key = f"{host}:{port_int}" if port_int else host

        repl = payload.get("repl") if isinstance(payload.get("repl"), dict) else {}
        rs_status = repl.get("rs_status") if isinstance(repl.get("rs_status"), dict) else None
        if repl.get("set"):
            set_name = set_name or _to_str(repl.get("set"))

        rs_members = []
        if rs_status and isinstance(rs_status.get("members"), list):
            rs_members = rs_status.get("members") or []
        if not rs_members:
            role_guess = _normalize_role(payload.get("mongo_role"))
            if self_key:
                members_map.setdefault(
                    self_key,
                    {"host": self_key, "role": role_guess, "state": None},
                )
            continue

        for member in rs_members:
            if not isinstance(member, dict):
                continue
            name = _to_str(member.get("name") or "").strip()
            if not name:
                continue
            state_str = _normalize_role(member.get("stateStr"))
            state = member.get("state")
            existing = members_map.get(name)
            if existing is None or existing.get("role") in (None, "UNKNOWN"):
                members_map[name] = {
                    "host": name,
                    "role": state_str,
                    "state": state if isinstance(state, int) else None,
                }

    members = sorted(members_map.values(), key=lambda x: _to_str(x.get("host")))
    primary_count = sum(1 for m in members if m.get("role") == "PRIMARY")
    secondary_count = sum(1 for m in members if m.get("role") == "SECONDARY")
    arbiter_count = sum(1 for m in members if m.get("role") == "ARBITER")
    unknown_count = sum(1 for m in members if m.get("role") not in ("PRIMARY", "SECONDARY", "ARBITER"))

    return {
        "set_name": set_name,
        "members": members,
        "primary_count": primary_count,
        "secondary_count": secondary_count,
        "arbiter_count": arbiter_count,
        "unknown_count": unknown_count,
        "total_members": len(members),
    }


def extract_redis_topology(instance_payloads):
    """从 Redis 集群快照列表聚合拓扑。"""
    nodes = []
    mode_set = set()
    cluster_state_set = set()

    for item in instance_payloads or []:
        payload = item.get("payload") if isinstance(item, dict) else None
        payload = payload if isinstance(payload, dict) else {}
        host = _to_str(item.get("host") or "").strip()
        port = item.get("port")
        try:
            port_int = int(port) if port not in (None, "") else None
        except (TypeError, ValueError):
            port_int = None
        self_key = f"{host}:{port_int}" if port_int else host

        role = _to_str(payload.get("role") or "unknown").strip().lower()
        mode = _to_str(payload.get("redis_mode") or "").strip().lower()
        if mode:
            mode_set.add(mode)
        replication_source = _to_str(payload.get("replication_source") or "").strip() or None

        cluster_info = payload.get("cluster_info")
        if isinstance(cluster_info, dict):
            state = _to_str(cluster_info.get("cluster_state") or "").strip().lower()
            if state:
                cluster_state_set.add(state)

        nodes.append({
            "host": self_key,
            "role": role,
            "master_host": replication_source,
        })

    nodes.sort(key=lambda x: _to_str(x.get("host")))
    master_count = sum(1 for n in nodes if n.get("role") == "master")
    slave_count = sum(1 for n in nodes if n.get("role") in {"slave", "replica"})

    mode = next(iter(mode_set), None) if len(mode_set) == 1 else (None if not mode_set else "mixed")
    cluster_state = next(iter(cluster_state_set), None) if len(cluster_state_set) == 1 else (
        None if not cluster_state_set else "mixed"
    )

    return {
        "mode": mode,
        "cluster_state": cluster_state,
        "nodes": nodes,
        "master_count": master_count,
        "slave_count": slave_count,
        "total_nodes": len(nodes),
    }


def extract_mysql_topology(instance_payloads, ha_domain=None):
    """从 MySQL 集群快照列表聚合拓扑。
    保留稳定字段：ha_domain、members:[{host, role, replica_source, effective_read_only}]，
    role 来源于 payload.replication_role（master/slave/read_only/unknown）。
    """
    members = []
    for item in instance_payloads or []:
        payload = item.get("payload") if isinstance(item, dict) else None
        payload = payload if isinstance(payload, dict) else {}
        host = _to_str(item.get("host") or "").strip()
        port = item.get("port")
        try:
            port_int = int(port) if port not in (None, "") else None
        except (TypeError, ValueError):
            port_int = None
        self_key = f"{host}:{port_int}" if port_int else host

        role = _to_str(payload.get("replication_role") or "unknown").strip().lower() or "unknown"
        effective_read_only = payload.get("effective_read_only")
        src_host = _to_str(payload.get("replica_source_host") or "").strip() or None
        src_port = payload.get("replica_source_port")
        try:
            src_port_int = int(src_port) if src_port not in (None, "") else None
        except (TypeError, ValueError):
            src_port_int = None
        replica_source = None
        if src_host:
            replica_source = f"{src_host}:{src_port_int}" if src_port_int else src_host

        members.append({
            "host": self_key,
            "role": role,
            "replica_source": replica_source,
            "effective_read_only": bool(effective_read_only) if effective_read_only is not None else None,
        })

    members.sort(key=lambda x: _to_str(x.get("host")))
    master_count = sum(1 for m in members if m.get("role") == "master")
    slave_count = sum(1 for m in members if m.get("role") in {"slave", "replica"})
    read_only_count = sum(1 for m in members if m.get("role") == "read_only")

    return {
        "ha_domain": _to_str(ha_domain or "") or None,
        "members": members,
        "master_count": master_count,
        "slave_count": slave_count,
        "read_only_count": read_only_count,
        "total_members": len(members),
    }


def compute_topology_fingerprint(topology):
    if topology is None:
        return ""
    try:
        serialized = json.dumps(topology, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        serialized = repr(topology)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _fingerprint_for_dedup(topology, db_type):
    """
    只保留稳定字段作为去重指纹，剔除易抖动字段（如 state 数值、link_status 瞬态值）。
    """
    if db_type == "mongodb":
        stable = {
            "set_name": topology.get("set_name"),
            "members": [
                {"host": m.get("host"), "role": m.get("role")}
                for m in (topology.get("members") or [])
            ],
        }
    elif db_type == "redis":
        stable = {
            "mode": topology.get("mode"),
            "cluster_state": topology.get("cluster_state"),
            "nodes": [
                {"host": n.get("host"), "role": n.get("role"), "master_host": n.get("master_host")}
                for n in (topology.get("nodes") or [])
            ],
        }
    elif db_type == "mysql":
        stable = {
            "ha_domain": topology.get("ha_domain"),
            "members": [
                {
                    "host": m.get("host"),
                    "role": m.get("role"),
                    "replica_source": m.get("replica_source"),
                }
                for m in (topology.get("members") or [])
            ],
        }
    else:
        stable = topology
    return compute_topology_fingerprint(stable)


def _topology_summary(topology, db_type):
    if db_type == "mongodb":
        return topology.get("total_members") or 0
    if db_type == "redis":
        return topology.get("total_nodes") or 0
    if db_type == "mysql":
        return topology.get("total_members") or 0
    return 0


def _action_for_db_type(db_type):
    if db_type == "mongodb":
        return MONGO_TOPOLOGY_ACTION
    if db_type == "redis":
        return REDIS_TOPOLOGY_ACTION
    if db_type == "mysql":
        return MYSQL_TOPOLOGY_ACTION
    return None


def _latest_fingerprint(cluster):
    """读取该集群最新一条拓扑变更记录，作为去重基线。"""
    action = _action_for_db_type(cluster.db_type)
    if not action:
        return None, None
    row = (
        AuditLog.query
        .filter(
            AuditLog.action == action,
            AuditLog.target_type == "database_cluster",
            AuditLog.target_id == str(cluster.id),
        )
        .order_by(AuditLog.id.desc())
        .first()
    )
    if not row:
        return None, None
    detail = row.detail_json if isinstance(row.detail_json, dict) else {}
    return detail.get("fingerprint"), detail.get("topology")


def record_topology_change_if_diff(cluster, topology):
    """
    与上一次拓扑对比，指纹不同则写入 audit_logs。total_members/total_nodes == 0 不写基线，避免噪声。
    """
    if not cluster or cluster.db_type not in ("mongodb", "redis", "mysql"):
        return False
    action = _action_for_db_type(cluster.db_type)
    if not action:
        return False
    if not _topology_summary(topology, cluster.db_type):
        return False

    fingerprint = _fingerprint_for_dedup(topology, cluster.db_type)
    if not fingerprint:
        return False

    previous_fingerprint, previous_topology = _latest_fingerprint(cluster)
    if previous_fingerprint == fingerprint:
        return False

    detail = {
        "cluster_id": cluster.id,
        "cluster_name": cluster.name,
        "db_type": cluster.db_type,
        "fingerprint": fingerprint,
        "previous_fingerprint": previous_fingerprint,
        "topology": topology,
        "previous_topology": previous_topology,
        "changed_at": _beijing_now_iso(),
    }
    db.session.add(
        AuditLog(
            user_id=None,
            action=action,
            target_type="database_cluster",
            target_id=str(cluster.id),
            detail_json=detail,
        )
    )
    return True


def list_topology_history(cluster_id, page=1, page_size=10):
    """从 audit_logs 分页读取集群拓扑变更历史（按时间倒序）。"""
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(200, int(page_size)))
    except (TypeError, ValueError):
        page_size = 10

    cluster = DatabaseCluster.query.get(cluster_id)
    if not cluster or cluster.db_type not in ("mongodb", "redis", "mysql"):
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    action = _action_for_db_type(cluster.db_type)
    base_query = (
        AuditLog.query
        .filter(
            AuditLog.action == action,
            AuditLog.target_type == "database_cluster",
            AuditLog.target_id == str(cluster.id),
        )
    )
    total = base_query.count()
    rows = (
        base_query
        .order_by(AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for row in rows:
        detail = row.detail_json if isinstance(row.detail_json, dict) else {}
        items.append({
            "id": row.id,
            "action": row.action,
            "cluster_id": cluster.id,
            "cluster_name": cluster.name,
            "db_type": cluster.db_type,
            "fingerprint": detail.get("fingerprint"),
            "previous_fingerprint": detail.get("previous_fingerprint"),
            "topology": detail.get("topology"),
            "previous_topology": detail.get("previous_topology"),
            "changed_at": detail.get("changed_at") or (row.created_at.isoformat() if row.created_at else None),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
