from datetime import datetime, timedelta
import json

from app.services.collectors.node_exporter import collect_node_exporter_metrics


def _bson_to_json(value):
    try:
        from bson.json_util import dumps as bson_dumps
        return json.loads(bson_dumps(value))
    except Exception:
        return value


def _calc_repl_lag_seconds(repl_status, host_identity):
    try:
        members = repl_status.get("members") or []
        primary_optime = None
        self_optime = None
        for member in members:
            if member.get("stateStr") == "PRIMARY":
                primary_optime = member.get("optimeDate") or member.get("optime", {}).get("ts")
            if member.get("self") is True or member.get("name") == host_identity:
                self_optime = member.get("optimeDate") or member.get("optime", {}).get("ts")
        if primary_optime and self_optime:
            # optimeDate is datetime, otherwise treat as 0
            if isinstance(primary_optime, datetime) and isinstance(self_optime, datetime):
                return int((primary_optime - self_optime).total_seconds())
    except Exception:
        return None
    return None


def _extract_wt_cache_pct(status):
    cache = (status.get("wiredTiger") or {}).get("cache") or {}
    used = cache.get("bytes currently in the cache")
    max_bytes = cache.get("maximum bytes configured")
    try:
        used_val = float(used)
        max_val = float(max_bytes)
        if max_val > 0:
            return round(used_val / max_val * 100, 2)
    except Exception:
        return None
    return None


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return default


def _normalize_auth_mechanism(value):
    mech = str(value or "").strip()
    if not mech:
        return None
    lower = mech.lower()
    if lower in {"auto", "default", "none"}:
        return None
    return mech


def _try_collect_arbiter_without_auth(instance):
    from pymongo import MongoClient

    host = instance.resolved_ip or instance.host_input
    client = MongoClient(
        host,
        instance.port,
        serverSelectionTimeoutMS=2000,
        connectTimeoutMS=2000,
        socketTimeoutMS=2000,
        ssl=False,
        appname="dbms-monitor",
    )
    try:
        version = None
        process = "mongod"
        try:
            info = client.server_info() or {}
            version = info.get("version")
        except Exception:
            info = {}
        try:
            hello = client.admin.command("hello")
        except Exception:
            hello = client.admin.command("isMaster")
        process = hello.get("msg") == "isdbgrid" and "mongos" or process
        if not version:
            version = hello.get("version")
        if hello.get("arbiterOnly") is True:
            return {
                "ok": True,
                "ping_ok": True,
                "db_type": "mongodb",
                "collected_at": datetime.now().isoformat(),
                "version": version,
                "process": process,
                "mongo_role": "arbiter",
                "mongo_topology": "replica_set",
                "started_at": None,
                "uptime": None,
                "connections_current": None,
                "connections_max": None,
                "lock_waits": None,
                "repl_lag_seconds": None,
                "op_insert": None,
                "op_query": None,
                "op_update": None,
                "op_delete": None,
                "op_read": None,
                "op_write": None,
                "op_read_pct": None,
                "op_write_pct": None,
                "cache_used_pct": None,
                "connections": {},
                "mem": {},
                "repl": {
                    "set": hello.get("setName"),
                    "myState": 7,
                    "members": len(hello.get("hosts") or []),
                    "rs_status": None,
                    "rs_conf": None,
                },
                "auth_limited": True,
            }
    finally:
        client.close()
    return None


def collect_mongodb_status(instance, password):
    host_metrics = collect_node_exporter_metrics(instance)
    try:
        from pymongo import MongoClient
        host = instance.resolved_ip or instance.host_input
        extra = instance.extra_json if isinstance(instance.extra_json, dict) else {}
        client_opts = {
            "serverSelectionTimeoutMS": 2000,
            "connectTimeoutMS": 2000,
            "socketTimeoutMS": 2000,
            "ssl": False,
            "appname": "dbms-monitor",
        }

        auth_mech = _normalize_auth_mechanism(extra.get("auth_mechanism"))
        auth_source = (extra.get("auth_source") or extra.get("auth_db") or "").strip() or None
        auth_sources = []
        if auth_source:
            auth_sources.append(auth_source)
        if "admin" not in auth_sources:
            auth_sources.append("admin")
        if "local" not in auth_sources:
            auth_sources.append("local")
        if instance.username and password:
            last_error = None
            client = None
            if not auth_sources:
                auth_sources.append("admin")
            
            for source in auth_sources:
                try:
                    kwargs = dict(
                        username=instance.username,
                        password=password,
                        authSource=source,
                        **client_opts,
                    )
                    if auth_mech:
                        kwargs["authMechanism"] = auth_mech
                    client = MongoClient(host, instance.port, **kwargs)
                    client.admin.command("ping")
                    break
                except Exception as exc:
                    last_error = exc
                    client = None
                    if auth_mech:
                        # Retry once without explicit mechanism to let server negotiate.
                        try:
                            kwargs = dict(
                                username=instance.username,
                                password=password,
                                authSource=source,
                                **client_opts,
                            )
                            client = MongoClient(host, instance.port, **kwargs)
                            client.admin.command("ping")
                            break
                        except Exception as retry_exc:
                            last_error = retry_exc
                            client = None
                            continue
                    continue
                if client:
                    break
            if client is None:
                raise last_error or Exception("mongo auth failed")
        else:
            client = MongoClient(host, instance.port, **client_opts)

        client.admin.command("ping")
        # In PyMongo 3.x, use server_info() or run isMaster
        info = client.server_info()
        status = client.admin.command("serverStatus")

        hello = {}
        try:
            # hello command is MongoDB 4.4+, fallback to isMaster for older versions
            try:
                hello = client.admin.command("hello")
            except Exception:
                hello = client.admin.command("isMaster")
        except Exception:
            hello = {}

        connections = status.get("connections", {})
        connections_current = connections.get("current")
        connections_available = connections.get("available")
        connections_max = None
        if connections_current is not None and connections_available is not None:
            try:
                connections_max = int(connections_current) + int(connections_available)
            except Exception:
                connections_max = None

        opcounters = status.get("opcounters", {})
        op_insert = opcounters.get("insert")
        op_query = opcounters.get("query")
        op_update = opcounters.get("update")
        op_delete = opcounters.get("delete")
        op_getmore = opcounters.get("getmore")

        op_read = None
        op_write = None
        read_pct = None
        write_pct = None
        try:
            op_read = (op_query or 0) + (op_getmore or 0)
            op_write = (op_insert or 0) + (op_update or 0) + (op_delete or 0)
            total_ops = op_read + op_write
            if total_ops > 0:
                read_pct = round(op_read / total_ops * 100, 2)
                write_pct = round(op_write / total_ops * 100, 2)
        except Exception:
            pass

        lock_waits = None
        try:
            lock_waits = status.get("globalLock", {}).get("currentQueue", {}).get("total")
        except Exception:
            lock_waits = None

        cache_used_pct = _extract_wt_cache_pct(status)

        role = None
        topology = None
        if hello.get("msg") == "isdbgrid" or status.get("process") == "mongos":
            role = "mongos"
            topology = "mongos"
        elif hello.get("configsvr"):
            role = "configsvr"
            topology = "configsvr"
        elif hello.get("arbiterOnly") is True:
            role = "arbiter"
        elif hello.get("isWritablePrimary") is True or hello.get("ismaster") is True:
            role = "primary"
        elif hello.get("secondary") is True:
            role = "secondary"

        if topology is None and hello.get("setName"):
            topology = "shard"
            if role is None:
                role = "shard"

        repl_summary = {"set": hello.get("setName"), "myState": None, "members": 0}
        rs_status = None
        rs_conf = None
        repl_lag_seconds = None
        try:
            hosts = hello.get("hosts") or []
            repl_summary["members"] = len(hosts)
        except Exception:
            repl_summary["members"] = 0

        # Use rs.status() to match current node and derive role.
        try:
            repl = client.admin.command("replSetGetStatus")
            rs_status = _bson_to_json(repl)
            repl_summary["set"] = repl.get("set") or repl_summary["set"]
            repl_summary["myState"] = repl.get("myState")
            members = repl.get("members") or []
            repl_summary["members"] = len(members)

            target_host = f"{host}:{instance.port}"
            domain_host = None
            if isinstance(extra, dict):
                domain_host = str(extra.get("domain") or "").strip()
            target_domain = f"{domain_host}:{instance.port}" if domain_host else None
            matched_member = None
            for member in members:
                name = member.get("name")
                if name == target_host:
                    matched_member = member
                    break
                if target_domain and name == target_domain:
                    matched_member = member
                    break

            if matched_member:
                state_str = (matched_member.get("stateStr") or "").upper()
                if state_str == "PRIMARY":
                    role = "primary"
                elif state_str == "SECONDARY":
                    role = "secondary"
                elif state_str == "ARBITER":
                    role = "arbiter"

            repl_lag_seconds = _calc_repl_lag_seconds(repl, target_host)
        except Exception:
            pass

        client.close()

        uptime = status.get("uptime")
        started_at = None
        if uptime is not None:
            try:
                started_at = (datetime.now() - timedelta(seconds=int(uptime))).isoformat()
            except Exception:
                started_at = None

        return {
            "ok": True,
            "ping_ok": True,
            "db_type": "mongodb",
            "collected_at": datetime.now().isoformat(),
            "version": info.get("version"),
            "process": status.get("process"),
            "mongo_role": role,
            "mongo_topology": topology,
            "started_at": started_at,
            "uptime": uptime,
            "connections_current": connections_current,
            "connections_max": connections_max,
            "lock_waits": lock_waits,
            "repl_lag_seconds": repl_lag_seconds,
            "op_insert": op_insert,
            "op_query": op_query,
            "op_update": op_update,
            "op_delete": op_delete,
            "op_read": op_read,
            "op_write": op_write,
            "op_read_pct": read_pct,
            "op_write_pct": write_pct,
            "cache_used_pct": cache_used_pct,
            "connections": connections,
            "mem": status.get("mem", {}),
            "repl": {
                **repl_summary,
                "rs_status": rs_status,
                "rs_conf": rs_conf,
            },
            **host_metrics,
        }
    except Exception as exc:
        exc_text = str(exc)
        if "Authentication failed" in exc_text:
            try:
                arbiter_payload = _try_collect_arbiter_without_auth(instance)
                if arbiter_payload:
                    host_metrics = collect_node_exporter_metrics(instance)
                    arbiter_payload.update(host_metrics)
                    return arbiter_payload
            except Exception:
                pass
        extra = instance.extra_json if isinstance(instance.extra_json, dict) else {}
        auth_source = (extra.get("auth_source") or extra.get("auth_db") or "admin").strip()
        auth_mech = _normalize_auth_mechanism(extra.get("auth_mechanism")) or "auto"
        direct_connection = _as_bool(extra.get("direct_connection"), default=False)
        host = instance.resolved_ip or instance.host_input
        user = instance.username or ""
        raw_password = password or ""
        safe_user = user if user else "<empty>"
        safe_password = raw_password if raw_password else "<empty>"
        conn_parts = [f"authSource={auth_source}", f"directConnection={direct_connection}", "tls=false"]
        if auth_mech and auth_mech != "auto":
            conn_parts.append(f"authMechanism={auth_mech}")
        conn_query = "&".join(conn_parts)
        conn_hint = f"mongodb://{safe_user}:{safe_password}@{host}:{instance.port}/?{conn_query}"

        detail_text = ""
        try:
            detail = getattr(exc, "details", None)
            if detail:
                detail_text = f", details={detail}"
        except Exception:
            detail_text = ""

        error_text = f"mongodb collect failed: {exc}{detail_text} (conn={conn_hint})"
        try:
            from flask import current_app

            current_app.logger.warning(
                "mongodb collect failed: instance_id=%s user=%s host=%s port=%s authSource=%s authMechanism=%s directConnection=%s tls=%s err=%s details=%s conn=%s",
                instance.id,
                instance.username,
                host,
                instance.port,
                auth_source,
                auth_mech,
                direct_connection,
                False,
                exc,
                getattr(exc, "details", None),
                conn_hint,
            )
        except Exception:
            pass
        return {"ok": False, "error": error_text}
