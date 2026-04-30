import json
import re
import shlex
import string
import subprocess
import time
from datetime import datetime
from typing import Optional
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.ha_config import HAConfig
from app.services.dns_resolver import list_host_addresses, resolve_host
from app.utils.crypto import decrypt_secret


def get_ha_switch_script_config():
    config = HAConfig.query.filter_by(enabled=True, is_default=True).order_by(HAConfig.id.desc()).first()
    if config:
        return config
    return HAConfig.query.filter_by(enabled=True).order_by(HAConfig.id.desc()).first()


def _instance_password(instance: DatabaseInstance):
    return decrypt_secret(instance.password_encrypted) if instance.password_encrypted else ""


def _instance_connect(instance: DatabaseInstance):
    import pymysql

    return pymysql.connect(
        host=instance.resolved_ip or instance.host_input,
        port=instance.port,
        user=instance.username,
        password=_instance_password(instance),
        connect_timeout=5,
        read_timeout=5,
        write_timeout=5,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def _query_one(cursor, sql: str):
    cursor.execute(sql)
    return cursor.fetchone()


def _to_bool(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "on", "yes", "true"}:
        return True
    if text in {"0", "off", "no", "false"}:
        return False
    return None


def _to_int(value):
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _step_timestamp():
    return datetime.now().isoformat()


def _emit_step(steps: list, progress_callback=None, **payload):
    step = {"timestamp": _step_timestamp(), **payload}
    steps.append(step)
    if callable(progress_callback):
        progress_callback(dict(step))
    return step


def _fetch_replica_status(cursor):
    for sql in ("SHOW REPLICA STATUS", "SHOW SLAVE STATUS"):
        try:
            cursor.execute(sql)
            row = cursor.fetchone()
            if row:
                return row
        except Exception:
            continue
    return None


def _fetch_master_status(cursor):
    try:
        cursor.execute("SHOW MASTER STATUS")
        return cursor.fetchone() or {}
    except Exception:
        return {}


def _status_value(row: dict, *keys):
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return None


def _collect_instance_topology(instance: DatabaseInstance):
    connection = _instance_connect(instance)
    try:
        with connection.cursor() as cursor:
            read_only_row = _query_one(cursor, "SHOW GLOBAL VARIABLES LIKE 'read_only'")
            super_read_only_row = _query_one(cursor, "SHOW GLOBAL VARIABLES LIKE 'super_read_only'")
            gtid_mode_row = _query_one(cursor, "SHOW GLOBAL VARIABLES LIKE 'gtid_mode'")
            server_uuid_row = _query_one(cursor, "SHOW GLOBAL VARIABLES LIKE 'server_uuid'")
            server_id_row = _query_one(cursor, "SHOW GLOBAL VARIABLES LIKE 'server_id'")
            version_row = _query_one(cursor, "SELECT VERSION() AS version")
            replica_status = _fetch_replica_status(cursor) or {}
            master_status = _fetch_master_status(cursor) or {}

        read_only = _to_bool(read_only_row.get("Value") if read_only_row else None)
        super_read_only = _to_bool(super_read_only_row.get("Value") if super_read_only_row else None)
        effective_read_only = None if read_only is None and super_read_only is None else bool(read_only or super_read_only)
        replica_source_host = _status_value(replica_status, "Source_Host", "Master_Host")
        replica_source_port = _to_int(_status_value(replica_status, "Source_Port", "Master_Port"))
        replica_source_resolved_ip = resolve_host(replica_source_host) if replica_source_host else None
        seconds_behind = _to_int(_status_value(replica_status, "Seconds_Behind_Source", "Seconds_Behind_Master"))
        replica_io_running = _to_bool(_status_value(replica_status, "Replica_IO_Running", "Slave_IO_Running"))
        replica_sql_running = _to_bool(_status_value(replica_status, "Replica_SQL_Running", "Slave_SQL_Running"))
        auto_position = _to_bool(_status_value(replica_status, "Auto_Position", "Auto_Position"))

        if replica_status:
            replication_role = "slave"
        elif effective_read_only is True:
            replication_role = "read_only"
        elif effective_read_only is False:
            replication_role = "master"
        else:
            replication_role = "unknown"

        return {
            "instance_id": instance.id,
            "instance_name": instance.name,
            "host": instance.host_input,
            "resolved_ip": instance.resolved_ip,
            "port": instance.port,
            "username": instance.username,
            "ok": True,
            "error": None,
            "version": version_row.get("version") if version_row else None,
            "read_only": read_only,
            "super_read_only": super_read_only,
            "effective_read_only": effective_read_only,
            "replication_role": replication_role,
            "seconds_behind_master": seconds_behind,
            "replica_io_running": replica_io_running,
            "replica_sql_running": replica_sql_running,
            "replica_source_host": replica_source_host,
            "replica_source_port": replica_source_port,
            "replica_source_resolved_ip": replica_source_resolved_ip,
            "gtid_mode": str(gtid_mode_row.get("Value") or "").upper() if gtid_mode_row else "",
            "server_uuid": server_uuid_row.get("Value") if server_uuid_row else None,
            "server_id": _to_int(server_id_row.get("Value") if server_id_row else None),
            "master_status_file": _status_value(master_status, "File"),
            "master_status_position": _to_int(_status_value(master_status, "Position")),
            "master_status_executed_gtid_set": _status_value(master_status, "Executed_Gtid_Set"),
            "executed_gtid_set": _status_value(replica_status, "Executed_Gtid_Set"),
            "retrieved_gtid_set": _status_value(replica_status, "Retrieved_Gtid_Set"),
            "relay_master_log_file": _status_value(replica_status, "Relay_Source_Log_File", "Relay_Master_Log_File"),
            "exec_master_log_pos": _to_int(_status_value(replica_status, "Exec_Source_Log_Pos", "Exec_Master_Log_Pos")),
            "source_log_file": _status_value(replica_status, "Source_Log_File", "Master_Log_File"),
            "read_source_log_pos": _to_int(_status_value(replica_status, "Read_Source_Log_Pos", "Read_Master_Log_Pos")),
            "source_user": _status_value(replica_status, "Source_User", "Master_User"),
            "auto_position": auto_position,
        }
    finally:
        connection.close()


def _gtid_interval_total(gtid_set: str):
    text = str(gtid_set or "").strip()
    if not text:
        return 0
    total = 0
    for server_part in text.split(","):
        sections = server_part.split(":")
        for section in sections[1:]:
            if "-" in section:
                start_text, end_text = section.split("-", 1)
                start_num = _to_int(start_text)
                end_num = _to_int(end_text)
                if start_num is not None and end_num is not None and end_num >= start_num:
                    total += end_num - start_num + 1
            else:
                number = _to_int(section)
                if number is not None:
                    total += 1
    return total


def _binlog_sort_key(log_file: str):
    text = str(log_file or "").strip()
    if not text:
        return ("", -1)
    matched = re.search(r"^(.*?)(\d+)$", text)
    if not matched:
        return (text, -1)
    return (matched.group(1), int(matched.group(2)))


def _switch_label(mode: str):
    return {
        "normal": "在线切换",
        "failure": "故障切换",
        "promote": "推广",
        "repair": "集群修复",
    }.get(mode, mode or "未知动作")


def _failure_priority(node: dict):
    gtid_score = _gtid_interval_total(node.get("executed_gtid_set"))
    retrieved_gtid_score = _gtid_interval_total(node.get("retrieved_gtid_set"))
    relay_file_key = _binlog_sort_key(node.get("relay_master_log_file"))
    source_file_key = _binlog_sort_key(node.get("source_log_file"))
    return (
        1 if gtid_score > 0 else 0,
        gtid_score,
        retrieved_gtid_score,
        relay_file_key[1],
        node.get("exec_master_log_pos") or -1,
        source_file_key[1],
        node.get("read_source_log_pos") or -1,
    )


def _failure_reason(node: dict):
    if node.get("is_current_master"):
        return "当前主库不能作为故障切换目标"
    if not node.get("ok"):
        return f"实例不可连接: {node.get('error') or '连接失败'}"
    if node.get("replication_role") != "slave":
        return f"当前角色为 {node.get('replication_role') or '未知'}，仅从库可参与故障切换"

    reasons = []
    if node.get("recommended_for_failure"):
        reasons.append("复制进度在可用从库中最靠前")
    if node.get("gtid_mode"):
        reasons.append(f"GTID={node.get('gtid_mode')}")
    lag = node.get("seconds_behind_master")
    if lag is not None:
        reasons.append(f"延迟 {lag}s")
    if node.get("replica_io_running") is False or node.get("replica_sql_running") is False:
        reasons.append("复制线程存在异常")
    return "；".join(reasons) if reasons else "满足故障切换条件"


def _failure_switch_block_reason(topology: dict):
    nodes = topology.get("nodes") or []
    current_master_id = topology.get("current_master_instance_id")
    if not nodes or not current_master_id:
        return None

    current_master = next((node for node in nodes if node.get("instance_id") == current_master_id), None)
    if not current_master:
        return None

    master_healthy = (
        current_master.get("ok") is True
        and current_master.get("replication_role") == "master"
        and current_master.get("effective_read_only") is False
    )
    if not master_healthy:
        return None

    for node in nodes:
        if node.get("ok") is not True:
            return None
        if node.get("instance_id") == current_master_id:
            continue
        if node.get("replication_role") != "slave":
            return None
        if node.get("replica_io_running") is False or node.get("replica_sql_running") is False:
            return None

    return "当前集群所有节点状态正常，请使用在线切换"


def _resolve_replication_credentials(source_instance: DatabaseInstance, source_node: dict):
    extra = source_instance.extra_json if isinstance(source_instance.extra_json, dict) else {}
    replication_password = (
        extra.get("replication_password")
        or extra.get("repl_password")
        or _instance_password(source_instance)
    )
    replication_user = (
        extra.get("replication_user")
        or extra.get("repl_user")
        or source_node.get("source_user")
        or source_instance.username
    )
    return str(replication_user or "").strip(), str(replication_password or "")


def _set_read_only(instance: DatabaseInstance, enabled: bool):
    connection = _instance_connect(instance)
    try:
        with connection.cursor() as cursor:
            flag = "ON" if enabled else "OFF"
            cursor.execute(f"SET GLOBAL read_only = {flag}")
            try:
                cursor.execute(f"SET GLOBAL super_read_only = {flag}")
            except Exception:
                pass
    finally:
        connection.close()


def _stop_and_reset_replica(instance: DatabaseInstance):
    connection = _instance_connect(instance)
    try:
        with connection.cursor() as cursor:
            for sql in (
                "STOP REPLICA",
                "STOP SLAVE",
                "RESET REPLICA ALL",
                "RESET SLAVE ALL",
            ):
                try:
                    cursor.execute(sql)
                except Exception:
                    continue
    finally:
        connection.close()


def _wait_replica_catch_up(instance: DatabaseInstance, timeout_seconds: int, interval_seconds: int = 2):
    deadline = time.time() + max(timeout_seconds, 1)
    last_status = None
    while time.time() <= deadline:
        last_status = _collect_instance_topology(instance)
        lag = last_status.get("seconds_behind_master")
        io_running = last_status.get("replica_io_running")
        sql_running = last_status.get("replica_sql_running")
        if last_status.get("replication_role") == "slave" and lag == 0 and io_running is True and sql_running is True:
            return last_status
        time.sleep(interval_seconds)
    raise RuntimeError(
        f"等待复制追平超时，最后状态: lag={last_status.get('seconds_behind_master') if last_status else 'unknown'}"
    )


def _sql_literal(connection, value):
    return connection.escape("" if value is None else value)


def _configure_replica(
    replica: DatabaseInstance,
    source: DatabaseInstance,
    source_node: dict,
    use_gtid: bool,
    steps: list,
    force_auto_position: bool = False,
    progress_callback=None,
):
    replication_user, replication_password = _resolve_replication_credentials(source, source_node)
    if not replication_user:
        raise RuntimeError("未找到复制用户，无法重建主从关系")

    new_source_host = source.resolved_ip or source.host_input
    connection = _instance_connect(replica)
    try:
        with connection.cursor() as cursor:
            for sql in ("STOP REPLICA", "STOP SLAVE", "RESET REPLICA ALL", "RESET SLAVE ALL"):
                try:
                    cursor.execute(sql)
                except Exception:
                    continue

            if use_gtid or force_auto_position:
                change_sql = (
                    "CHANGE REPLICATION SOURCE TO "
                    f"SOURCE_HOST={_sql_literal(connection, new_source_host)}, "
                    f"SOURCE_PORT={int(source.port)}, "
                    f"SOURCE_USER={_sql_literal(connection, replication_user)}, "
                    f"SOURCE_PASSWORD={_sql_literal(connection, replication_password)}, "
                    "SOURCE_AUTO_POSITION=1"
                )
                legacy_sql = (
                    "CHANGE MASTER TO "
                    f"MASTER_HOST={_sql_literal(connection, new_source_host)}, "
                    f"MASTER_PORT={int(source.port)}, "
                    f"MASTER_USER={_sql_literal(connection, replication_user)}, "
                    f"MASTER_PASSWORD={_sql_literal(connection, replication_password)}, "
                    "MASTER_AUTO_POSITION=1"
                )
            else:
                master_status = source_node.get("master_status_file"), source_node.get("master_status_position")
                if not master_status[0] or not master_status[1]:
                    raise RuntimeError("新主库未获取到 binlog 位点，无法重建非 GTID 复制")
                change_sql = (
                    "CHANGE REPLICATION SOURCE TO "
                    f"SOURCE_HOST={_sql_literal(connection, new_source_host)}, "
                    f"SOURCE_PORT={int(source.port)}, "
                    f"SOURCE_USER={_sql_literal(connection, replication_user)}, "
                    f"SOURCE_PASSWORD={_sql_literal(connection, replication_password)}, "
                    f"SOURCE_LOG_FILE={_sql_literal(connection, master_status[0])}, "
                    f"SOURCE_LOG_POS={int(master_status[1])}"
                )
                legacy_sql = (
                    "CHANGE MASTER TO "
                    f"MASTER_HOST={_sql_literal(connection, new_source_host)}, "
                    f"MASTER_PORT={int(source.port)}, "
                    f"MASTER_USER={_sql_literal(connection, replication_user)}, "
                    f"MASTER_PASSWORD={_sql_literal(connection, replication_password)}, "
                    f"MASTER_LOG_FILE={_sql_literal(connection, master_status[0])}, "
                    f"MASTER_LOG_POS={int(master_status[1])}"
                )
            try:
                cursor.execute(change_sql)
            except Exception:
                cursor.execute(legacy_sql)
            try:
                cursor.execute("START REPLICA")
            except Exception:
                cursor.execute("START SLAVE")
    finally:
        connection.close()
    _emit_step(
        steps,
        progress_callback=progress_callback,
        step="rebuild_replication",
        message=f"已将 {replica.name} 绑定到新主库 {source.name}",
        use_gtid=bool(use_gtid or force_auto_position),
        auto_position=bool(use_gtid or force_auto_position),
        source_host=new_source_host,
    )


def _rebuild_other_replicas(
    cluster_id: int,
    topology_nodes: list,
    source: DatabaseInstance,
    source_node: dict,
    steps: list,
    skip_instance_ids=None,
    progress_callback=None,
):
    skip_ids = set(skip_instance_ids or [])
    candidates = []
    for node in topology_nodes or []:
        instance_id = node.get("instance_id")
        if not instance_id or instance_id in skip_ids:
            continue
        if not node.get("ok") or node.get("replication_role") != "slave":
            continue
        candidates.append(node)

    if not candidates:
        _emit_step(
            steps,
            progress_callback=progress_callback,
            step="rebuild_other_replicas",
            message="没有需要重挂到新主库的其他从库",
            rebuilt_count=0,
            failed_count=0,
        )
        return {"rebuilt": [], "failed": []}

    use_gtid = str(source_node.get("gtid_mode") or "").upper() == "ON" and bool(
        source_node.get("master_status_executed_gtid_set") or source_node.get("executed_gtid_set")
    )
    result = {"rebuilt": [], "failed": []}
    for node in candidates:
        instance = DatabaseInstance.query.get(node["instance_id"])
        if not instance:
            result["failed"].append(
                {
                    "instance_id": node["instance_id"],
                    "instance_name": node.get("instance_name"),
                    "error": "实例不存在",
                }
            )
            continue
        try:
            _configure_replica(
                instance,
                source,
                source_node,
                use_gtid=use_gtid,
                steps=steps,
                progress_callback=progress_callback,
            )
            _set_read_only(instance, True)
            _emit_step(
                steps,
                progress_callback=progress_callback,
                step="lock_rebuilt_replica",
                message=f"已开启重挂从库 {instance.name} 的 read_only/super_read_only",
            )
            result["rebuilt"].append(
                {
                    "instance_id": instance.id,
                    "instance_name": instance.name,
                }
            )
        except Exception as exc:
            error_text = str(exc)
            result["failed"].append(
                {
                    "instance_id": instance.id,
                    "instance_name": instance.name,
                    "error": error_text,
                }
            )
            _emit_step(
                steps,
                progress_callback=progress_callback,
                step="rebuild_replication_failed",
                message=f"重挂从库 {instance.name} 失败: {error_text}",
                instance_id=instance.id,
            )

    _emit_step(
        steps,
        progress_callback=progress_callback,
        step="rebuild_other_replicas",
        message=f"其余从库重挂完成，成功 {len(result['rebuilt'])} 台，失败 {len(result['failed'])} 台",
        rebuilt=result["rebuilt"],
        failed=result["failed"],
        rebuilt_count=len(result["rebuilt"]),
        failed_count=len(result["failed"]),
    )
    return result


def _safe_text(value):
    return "" if value in (None, "") else str(value)


def _build_switch_context(cluster: DatabaseCluster, source: Optional[DatabaseInstance], target: DatabaseInstance, mode: str, extra=None):
    source_host = source.host_input if source else ""
    source_ip = (source.resolved_ip or source.host_input) if source else ""
    source_port = source.port if source else ""
    source_name = source.name if source else ""
    target_host = target.host_input if target else ""
    target_ip = (target.resolved_ip or target.host_input) if target else ""
    target_port = target.port if target else ""
    target_name = target.name if target else ""
    switch_label = _switch_label(mode)
    payload = {
        "switch_mode": _safe_text(mode),
        "switch_label": switch_label,
        "cluster_id": _safe_text(cluster.id),
        "cluster_name": _safe_text(cluster.name),
        "business_line": _safe_text(cluster.business_line or cluster.namespace),
        "environment": _safe_text(cluster.environment),
        "ha_domain": _safe_text(cluster.ha_domain),
        "source_name": _safe_text(source_name),
        "source_host": _safe_text(source_host),
        "source_ip": _safe_text(source_ip),
        "source_port": _safe_text(source_port),
        "source_address": _safe_text(f"{source_ip}:{source_port}" if source_ip and source_port else source_ip or ""),
        "target_name": _safe_text(target_name),
        "target_host": _safe_text(target_host),
        "target_ip": _safe_text(target_ip),
        "target_port": _safe_text(target_port),
        "target_address": _safe_text(f"{target_ip}:{target_port}" if target_ip and target_port else target_ip or ""),
    }
    switch_info = {
        "switch_mode": payload["switch_mode"],
        "switch_label": payload["switch_label"],
        "cluster": {
            "id": cluster.id,
            "name": cluster.name,
            "business_line": cluster.business_line or cluster.namespace,
            "environment": cluster.environment,
            "ha_domain": cluster.ha_domain,
        },
        "source": {
            "id": source.id if source else None,
            "name": source.name if source else None,
            "host": source_host or None,
            "ip": source_ip or None,
            "port": source_port or None,
        },
        "target": {
            "id": target.id if target else None,
            "name": target.name if target else None,
            "host": target_host or None,
            "ip": target_ip or None,
            "port": target_port or None,
        },
        "extra": extra or {},
    }
    payload["switch_info_json"] = json.dumps(switch_info, ensure_ascii=False)
    return payload


def _render_command_template(command_template: str, context: dict):
    text = str(command_template or "").strip()
    if not text:
        return []
    rendered = string.Template(text).safe_substitute(context)
    return shlex.split(rendered, posix=True)


def _run_switch_script(cluster: DatabaseCluster, source: Optional[DatabaseInstance], target: DatabaseInstance, mode: str, extra=None):
    config = get_ha_switch_script_config()
    if not config:
        raise RuntimeError("未配置高可用切换脚本，请先在配置管理/高可用配置管理中配置")
    command_context = _build_switch_context(cluster, source=source, target=target, mode=mode, extra=extra)
    command_context["script_path"] = config.script_path
    template_tokens = _render_command_template(getattr(config, "command_template", None), command_context)
    if template_tokens:
        command = [config.script_path, *template_tokens]
    else:
        command = [
            config.script_path,
            "--mode",
            str(mode),
            "--cluster",
            str(cluster.name or ""),
            "--domain",
            str(cluster.ha_domain or ""),
            "--source-host",
            command_context["source_host"],
            "--source-ip",
            command_context["source_ip"],
            "--source-port",
            command_context["source_port"],
            "--target-host",
            command_context["target_host"],
            "--target-ip",
            command_context["target_ip"],
            "--target-port",
            command_context["target_port"],
            "--switch-info",
            command_context["switch_info_json"],
        ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or f"切换脚本执行失败，exit_code={result.returncode}")
    return {
        "script_config_id": config.id,
        "script_name": config.name,
        "script_path": config.script_path,
        "command_template": getattr(config, "command_template", None),
        "command_context": command_context,
        "stdout": (result.stdout or "").strip(),
        "stderr": (result.stderr or "").strip(),
        "command": command,
    }


def _repair_target_candidates(topology_nodes: list, current_master_id):
    candidates = []
    for node in topology_nodes or []:
        if not node.get("instance_id") or node.get("instance_id") == current_master_id:
            continue
        if not node.get("ok"):
            continue
        if node.get("ha_domain_matched"):
            continue
        candidates.append(node)
    return candidates


def _repair_cluster_replicas(
    topology_nodes: list,
    source: DatabaseInstance,
    source_node: dict,
    target_instance_ids,
    steps: list,
    progress_callback=None,
):
    target_ids = {int(item) for item in (target_instance_ids or [])}
    candidates = [node for node in _repair_target_candidates(topology_nodes, source.id) if node.get("instance_id") in target_ids]
    candidate_ids = {node.get("instance_id") for node in candidates}
    invalid_ids = sorted(target_ids - candidate_ids)
    if invalid_ids:
        raise RuntimeError(f"以下节点不允许执行集群修复: {', '.join(str(item) for item in invalid_ids)}")
    if not candidates:
        raise RuntimeError("未找到可用于集群修复的节点")

    gtid_enabled = str(source_node.get("gtid_mode") or "").upper() == "ON"
    if not gtid_enabled:
        raise RuntimeError("集群修复要求当前主库开启 GTID，复制位点将使用 AUTO_POSITION")
    result = {"rebuilt": [], "failed": []}
    for node in candidates:
        instance = DatabaseInstance.query.get(node["instance_id"])
        if not instance:
            result["failed"].append(
                {
                    "instance_id": node["instance_id"],
                    "instance_name": node.get("instance_name"),
                    "error": "实例不存在",
                }
            )
            continue
        try:
            _configure_replica(
                instance,
                source,
                source_node,
                use_gtid=True,
                steps=steps,
                force_auto_position=True,
                progress_callback=progress_callback,
            )
            _set_read_only(instance, True)
            _emit_step(
                steps,
                progress_callback=progress_callback,
                step="repair_replica_lock",
                message=f"已完成 {instance.name} 复制重建，使用 AUTO_POSITION 并启动复制",
                instance_id=instance.id,
            )
            result["rebuilt"].append(
                {
                    "instance_id": instance.id,
                    "instance_name": instance.name,
                }
            )
        except Exception as exc:
            error_text = str(exc)
            result["failed"].append(
                {
                    "instance_id": instance.id,
                    "instance_name": instance.name,
                    "error": error_text,
                }
            )
            _emit_step(
                steps,
                progress_callback=progress_callback,
                step="repair_replica_failed",
                message=f"修复节点 {instance.name} 失败: {error_text}",
                instance_id=instance.id,
            )

    _emit_step(
        steps,
        progress_callback=progress_callback,
        step="repair_cluster",
        message=f"集群修复完成，成功 {len(result['rebuilt'])} 台，失败 {len(result['failed'])} 台",
        rebuilt=result["rebuilt"],
        failed=result["failed"],
        rebuilt_count=len(result["rebuilt"]),
        failed_count=len(result["failed"]),
    )
    return result


def build_cluster_topology(cluster_id: int):
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    if cluster.db_type != "mysql":
        raise ValueError("only mysql cluster supports ha switch")

    instances = DatabaseInstance.query.filter_by(cluster_id=cluster.id, db_type="mysql", enabled=True).order_by(DatabaseInstance.id.asc()).all()
    if not instances:
        raise ValueError("cluster has no enabled mysql instances")

    resolved_servers = list_host_addresses(cluster.ha_domain) if cluster.ha_domain else []
    nodes = []
    for instance in instances:
        try:
            node = _collect_instance_topology(instance)
        except Exception as exc:
            node = {
                "instance_id": instance.id,
                "instance_name": instance.name,
                "host": instance.host_input,
                "resolved_ip": instance.resolved_ip,
                "port": instance.port,
                "username": instance.username,
                "ok": False,
                "error": str(exc),
                "replication_role": "unknown",
                "read_only": None,
                "super_read_only": None,
                "effective_read_only": None,
                "seconds_behind_master": None,
                "replica_io_running": None,
                "replica_sql_running": None,
                "replica_source_host": None,
                "replica_source_port": None,
                "replica_source_resolved_ip": None,
                "gtid_mode": "",
                "executed_gtid_set": None,
                "retrieved_gtid_set": None,
                "relay_master_log_file": None,
                "exec_master_log_pos": None,
                "source_log_file": None,
                "read_source_log_pos": None,
                "master_status_file": None,
                "master_status_position": None,
                "master_status_executed_gtid_set": None,
                "source_user": None,
                "auto_position": None,
            }
        node["ha_domain_matched"] = bool(node.get("resolved_ip") and node["resolved_ip"] in resolved_servers)
        nodes.append(node)

    current_master = None
    for node in nodes:
        if node.get("ha_domain_matched") and node.get("replication_role") == "master" and node.get("effective_read_only") is False:
            current_master = node
            break
    if current_master is None:
        for node in nodes:
            if node.get("replication_role") == "master" and node.get("effective_read_only") is False:
                current_master = node
                break

    failure_candidates = []
    current_master_id = current_master.get("instance_id") if current_master else None
    for node in nodes:
        node["is_current_master"] = node.get("instance_id") == current_master_id
        node["failure_priority"] = None
        node["recommended_for_failure"] = False
        node["failure_reason"] = None
        if node.get("is_current_master") or not node.get("ok") or node.get("replication_role") != "slave":
            continue
        priority = _failure_priority(node)
        node["failure_priority"] = list(priority)
        failure_candidates.append((priority, node))

    failure_candidates.sort(key=lambda item: item[0], reverse=True)
    if failure_candidates:
        failure_candidates[0][1]["recommended_for_failure"] = True

    for node in nodes:
        node["failure_reason"] = _failure_reason(node)

    return {
        "cluster": cluster.to_dict(),
        "ha_domain": cluster.ha_domain,
        "ha_resolved_servers": resolved_servers,
        "current_master_instance_id": current_master_id,
        "current_master_instance_name": current_master.get("instance_name") if current_master else None,
        "switch_script_configured": bool(get_ha_switch_script_config()),
        "nodes": nodes,
    }


def normal_switch(cluster_id: int, target_instance_id: int, lag_timeout_seconds: int = 60, progress_callback=None):
    topology = build_cluster_topology(cluster_id)
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    nodes_by_id = {node["instance_id"]: node for node in topology["nodes"]}
    current_master_id = topology.get("current_master_instance_id")
    if not current_master_id:
        raise RuntimeError("未识别到当前主库，无法执行在线切换")
    if target_instance_id == current_master_id:
        raise RuntimeError("不能选择当前主库作为新主库")
    current_master = DatabaseInstance.query.get(current_master_id)
    new_master = DatabaseInstance.query.get(target_instance_id)
    if not current_master or not new_master:
        raise RuntimeError("集群实例不存在")

    target_node = nodes_by_id.get(target_instance_id) or {}
    if target_node.get("replication_role") != "slave":
        raise RuntimeError("在线切换只能选择从库作为新主库")

    steps = []
    _set_read_only(current_master, True)
    _emit_step(
        steps,
        progress_callback=progress_callback,
        step="freeze_old_master",
        message=f"已开启原主库 {current_master.name} 只读",
    )

    target_node = _wait_replica_catch_up(new_master, lag_timeout_seconds)
    _emit_step(
        steps,
        progress_callback=progress_callback,
        step="wait_replica",
        message=f"新主候选 {new_master.name} 复制延迟已追平",
        lag=0,
    )

    _stop_and_reset_replica(new_master)
    _emit_step(
        steps,
        progress_callback=progress_callback,
        step="promote_new_master",
        message=f"已断开 {new_master.name} 的复制关系",
    )

    _set_read_only(new_master, False)
    _emit_step(
        steps,
        progress_callback=progress_callback,
        step="enable_new_master_write",
        message=f"已解除新主库 {new_master.name} 只读",
    )

    refreshed_new_master = _collect_instance_topology(new_master)
    use_gtid = str(refreshed_new_master.get("gtid_mode") or "").upper() == "ON" and bool(target_node.get("executed_gtid_set"))
    _configure_replica(
        current_master,
        new_master,
        refreshed_new_master,
        use_gtid=use_gtid,
        steps=steps,
        progress_callback=progress_callback,
    )
    _set_read_only(current_master, True)
    _emit_step(
        steps,
        progress_callback=progress_callback,
        step="lock_new_slave",
        message=f"已开启新从库 {current_master.name} 的 read_only/super_read_only",
    )
    rebuild_result = _rebuild_other_replicas(
        cluster.id,
        topology["nodes"],
        source=new_master,
        source_node=refreshed_new_master,
        steps=steps,
        skip_instance_ids={new_master.id, current_master.id},
        progress_callback=progress_callback,
    )

    script_result = _run_switch_script(
        cluster,
        source=current_master,
        target=new_master,
        mode="normal",
        extra={
            "old_master_instance_id": current_master.id,
            "new_master_instance_id": new_master.id,
            "rebuilt_count": len(rebuild_result.get("rebuilt") or []),
            "failed_count": len(rebuild_result.get("failed") or []),
        },
    )
    _emit_step(
        steps,
        progress_callback=progress_callback,
        step="switch_dns",
        message="已完成高可用域名切换",
        script=script_result,
    )
    return {
        "mode": "normal",
        "cluster_id": cluster.id,
        "old_master_instance_id": current_master.id,
        "new_master_instance_id": new_master.id,
        "other_replica_rebuild": rebuild_result,
        "switch_script": script_result,
        "steps": steps,
    }


def failure_switch(cluster_id: int, target_instance_id: Optional[int] = None, progress_callback=None):
    topology = build_cluster_topology(cluster_id)
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    nodes = topology.get("nodes") or []
    current_master_id = topology.get("current_master_instance_id")
    block_reason = _failure_switch_block_reason(topology)
    if block_reason:
        raise RuntimeError(block_reason)
    recommended = next((node for node in nodes if node.get("recommended_for_failure")), None)
    if target_instance_id is None:
        target_instance_id = recommended.get("instance_id") if recommended else None
    if not target_instance_id:
        raise RuntimeError("未找到可用于故障切换的从库")
    if recommended and target_instance_id != recommended.get("instance_id"):
        raise RuntimeError("故障切换必须选择应用日志最新的从库")

    target = DatabaseInstance.query.get(target_instance_id)
    if not target:
        raise RuntimeError("目标实例不存在")

    steps = []
    _stop_and_reset_replica(target)
    _emit_step(
        steps,
        progress_callback=progress_callback,
        step="detach_replica",
        message=f"已断开 {target.name} 的复制关系",
    )
    _set_read_only(target, False)
    _emit_step(
        steps,
        progress_callback=progress_callback,
        step="promote_master",
        message=f"已提升 {target.name} 为主库并关闭只读",
    )
    refreshed_target = _collect_instance_topology(target)
    rebuild_result = _rebuild_other_replicas(
        cluster.id,
        nodes,
        source=target,
        source_node=refreshed_target,
        steps=steps,
        skip_instance_ids={target.id, current_master_id},
        progress_callback=progress_callback,
    )
    current_master = DatabaseInstance.query.get(current_master_id) if current_master_id else None
    script_result = _run_switch_script(
        cluster,
        source=current_master,
        target=target,
        mode="failure",
        extra={
            "old_master_instance_id": current_master_id,
            "new_master_instance_id": target.id,
            "recommended_target_instance_id": recommended.get("instance_id") if recommended else target.id,
            "rebuilt_count": len(rebuild_result.get("rebuilt") or []),
            "failed_count": len(rebuild_result.get("failed") or []),
        },
    )
    _emit_step(
        steps,
        progress_callback=progress_callback,
        step="switch_dns",
        message="已完成高可用域名切换",
        script=script_result,
    )

    return {
        "mode": "failure",
        "cluster_id": cluster.id,
        "new_master_instance_id": target.id,
        "other_replica_rebuild": rebuild_result,
        "switch_script": script_result,
        "steps": steps,
        "recommended_target_instance_id": recommended.get("instance_id") if recommended else target.id,
    }


def promote_current_master(cluster_id: int, progress_callback=None):
    topology = build_cluster_topology(cluster_id)
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    current_master_id = topology.get("current_master_instance_id")
    if not current_master_id:
        raise RuntimeError("未识别到当前主库，无法执行推广")

    current_master = DatabaseInstance.query.get(current_master_id)
    current_master_node = next((node for node in topology.get("nodes") or [] if node.get("instance_id") == current_master_id), None)
    if not current_master or not current_master_node:
        raise RuntimeError("当前主库不存在，无法执行推广")
    if current_master_node.get("replication_role") != "master" or current_master_node.get("effective_read_only") is not False:
        raise RuntimeError("当前主库不可写，无法执行推广")

    steps = []
    _emit_step(
        steps,
        progress_callback=progress_callback,
        step="promote_dns_target",
        message=f"准备将当前主库 {current_master.name} 推广为 DNS 解析节点",
        instance_id=current_master.id,
    )
    script_result = _run_switch_script(
        cluster,
        source=current_master,
        target=current_master,
        mode="promote",
        extra={
            "promoted_instance_id": current_master.id,
            "dns_already_matched": bool(current_master_node.get("ha_domain_matched")),
        },
    )
    _emit_step(
        steps,
        progress_callback=progress_callback,
        step="switch_dns",
        message="已完成主库推广，DNS 已指向当前主库",
        script=script_result,
    )
    return {
        "mode": "promote",
        "cluster_id": cluster.id,
        "old_master_instance_id": current_master.id,
        "new_master_instance_id": current_master.id,
        "switch_script": script_result,
        "steps": steps,
    }


def repair_cluster(cluster_id: int, target_instance_ids=None, progress_callback=None):
    topology = build_cluster_topology(cluster_id)
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    current_master_id = topology.get("current_master_instance_id")
    if not current_master_id:
        raise RuntimeError("未识别到当前主库，无法执行集群修复")

    current_master = DatabaseInstance.query.get(current_master_id)
    current_master_node = next((node for node in topology.get("nodes") or [] if node.get("instance_id") == current_master_id), None)
    if not current_master or not current_master_node:
        raise RuntimeError("当前主库不存在，无法执行集群修复")
    if current_master_node.get("replication_role") != "master" or current_master_node.get("effective_read_only") is not False:
        raise RuntimeError("当前主库不可写，无法执行集群修复")

    default_target_ids = [node.get("instance_id") for node in _repair_target_candidates(topology.get("nodes") or [], current_master_id)]
    selected_target_ids = target_instance_ids or default_target_ids
    if not selected_target_ids:
        raise RuntimeError("没有可用于集群修复的非 DNS 节点")

    steps = []
    refreshed_master = _collect_instance_topology(current_master)
    _emit_step(
        steps,
        progress_callback=progress_callback,
        step="repair_prepare",
        message=f"准备将所选节点重建为当前主库 {current_master.name} 的从库",
        current_master_instance_id=current_master.id,
        target_instance_ids=selected_target_ids,
    )
    repair_result = _repair_cluster_replicas(
        topology_nodes=topology.get("nodes") or [],
        source=current_master,
        source_node=refreshed_master,
        target_instance_ids=selected_target_ids,
        steps=steps,
        progress_callback=progress_callback,
    )
    return {
        "mode": "repair",
        "cluster_id": cluster.id,
        "old_master_instance_id": current_master.id,
        "new_master_instance_id": current_master.id,
        "repair_target_instance_ids": list(selected_target_ids),
        "other_replica_rebuild": repair_result,
        "steps": steps,
    }
