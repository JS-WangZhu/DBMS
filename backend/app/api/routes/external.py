from uuid import uuid4
from flask import Blueprint, request
from app.api.routes.common import api_key_required, list_allowed_cluster_ids, require_cluster_permission, get_current_user
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.ai_config import AIModelConfig
from app.services.ai_service import get_mysql_metadata, get_mongodb_metadata, analyze_sql_with_ai
from app.services.data_access import (
    pick_instance, 
    list_mysql_databases, 
    list_mongo_databases, 
    register_execution, 
    set_execution_cancel_callback, 
    finish_execution
)
from app.services.audit import log_audit
from app.utils.response import ok_response, error_response

# 这里的导入需要根据 data_access.py 中的私有方法进行调整，或者在 external.py 中重新实现逻辑
# 为了保持代码整洁和独立性，我们将外部接口所需的辅助逻辑也整合进来

bp = Blueprint("external", __name__, url_prefix="/external")

def _validate_scope(payload, cluster: DatabaseCluster):
    line = (payload.get("business_line") or payload.get("product") or "").strip()
    env = (payload.get("environment") or "").strip()
    if line and (cluster.business_line or cluster.namespace) != line:
        return f"product mismatch: expected {cluster.business_line or cluster.namespace}, got {line}"
    if env and (cluster.environment or "") != env:
        return f"environment mismatch: expected {cluster.environment}, got {env}"
    return None

def _build_audit_detail(payload, db_type, cluster_id, instance_id, timeout_seconds, success, error_message=None, current_user=None):
    statement = str(payload.get("statement") or "")[:1000]
    return {
        "db_type": db_type,
        "business_line": payload.get("business_line") or payload.get("product"),
        "environment": payload.get("environment"),
        "cluster_id": cluster_id,
        "instance_id": instance_id,
        "timeout_seconds": timeout_seconds,
        "success": success,
        "error": error_message,
        "statement": statement,
        "operator_username": current_user.username if current_user else None,
    }

@bp.post("/execute")
@api_key_required
def external_data_execute():
    """
    外部系统执行数据变更/命令执行
    """
    from app.api.routes.data_access import _normalize_change_payload, _resolve_cluster_instance, _execute
    
    payload = _normalize_change_payload(request.get_json(silent=True) or {})
    db_type = payload.get("db_type")
    if db_type not in {"mysql", "mongodb", "redis"}:
        return error_response("db_type invalid", code=400)
        
    cluster, instance, err = _resolve_cluster_instance(payload)
    if err: return error_response(err, code=400)
    
    scope_err = _validate_scope(payload, cluster)
    if scope_err: return error_response(scope_err, code=400)
    
    if not require_cluster_permission(cluster.id, "change"):
        return error_response("permission denied for this cluster", code=403)

    timeout_seconds = int(payload.get("timeout_seconds") or 86400)
    chosen = pick_instance(db_type, cluster.id, None, for_change=True)
    if not chosen: chosen = instance
    if not chosen: return error_response("no available instance", code=400)

    current_user = get_current_user()
    execution_id = str(payload.get("execution_id") or "").strip() or uuid4().hex
    register_execution(execution_id, current_user.id if current_user else None, db_type)
    
    if db_type != "mysql":
        set_execution_cancel_callback(execution_id, None)
        
    try:
        ok, err, result = _execute(db_type, chosen, payload, timeout_seconds, for_change=True, execution_id=execution_id)
        if not ok:
            log_audit(
                user_id=current_user.id if current_user else None,
                action="external.execute",
                target_type="cluster",
                target_id=str(cluster.id),
                detail=_build_audit_detail(payload, db_type, cluster.id, chosen.id, timeout_seconds, success=False, error_message=err, current_user=current_user),
            )
            return error_response(err, code=400)
            
        log_audit(
            user_id=current_user.id if current_user else None,
            action="external.execute",
            target_type="cluster",
            target_id=str(cluster.id),
            detail=_build_audit_detail(payload, db_type, cluster.id, chosen.id, timeout_seconds, success=True, current_user=current_user),
        )
        return ok_response(data={
            "cluster_id": cluster.id,
            "instance_id": chosen.id,
            "result": result,
            "execution_id": execution_id
        })
    except Exception as exc:
        err_msg = str(exc)
        log_audit(
            user_id=current_user.id if current_user else None,
            action="external.execute",
            target_type="cluster",
            target_id=str(cluster.id),
            detail=_build_audit_detail(payload, db_type, cluster.id, chosen.id, timeout_seconds, success=False, error_message=err_msg, current_user=current_user),
        )
        return error_response(err_msg, code=500)
    finally:
        finish_execution(execution_id)

@bp.get("/clusters")
@api_key_required
def list_external_clusters():
    """
    外部系统查询可用集群列表
    """
    allowed_cluster_ids = list_allowed_cluster_ids("change")
    query = DatabaseCluster.query
    if allowed_cluster_ids is not None:
        if not allowed_cluster_ids:
            return ok_response(data={"clusters": [], "count": 0})
        query = query.filter(DatabaseCluster.id.in_(allowed_cluster_ids))
        
    clusters = query.order_by(DatabaseCluster.id.asc()).all()
    cluster_ids = [item.id for item in clusters]
    
    # 获取实例统计和种子节点
    instances = DatabaseInstance.query.filter(
        DatabaseInstance.cluster_id.in_(cluster_ids), 
        DatabaseInstance.enabled.is_(True)
    ).all() if cluster_ids else []
    
    instance_count_map = {}
    seed_node_map = {}
    for row in instances:
        instance_count_map[row.cluster_id] = instance_count_map.get(row.cluster_id, 0) + 1
        host = row.resolved_ip or row.host_input
        if host:
            seed_node_map.setdefault(row.cluster_id, set()).add(f"{host}:{row.port}")
            
    items = []
    for cluster in clusters:
        cluster_nodes = sorted(seed_node_map.get(cluster.id, set()))
        database_names = []
        # 获取库名列表用于外部系统展示
        chosen = pick_instance(cluster.db_type, cluster.id, None, for_change=(cluster.db_type == "mysql"))
        if chosen:
            try:
                if cluster.db_type == "mysql":
                    database_names = list_mysql_databases(chosen)
                elif cluster.db_type == "mongodb":
                    database_names = list_mongo_databases(chosen, seed_nodes=cluster_nodes)
            except:
                pass
                
        items.append({
            "id": cluster.id,
            "name": cluster.name,
            "db_type": cluster.db_type,
            "product": cluster.business_line or cluster.namespace,
            "environment": cluster.environment,
            "instance_count": instance_count_map.get(cluster.id, 0),
            "databases": database_names
        })
    return ok_response(data={"clusters": items, "count": len(items)})

@bp.post("/ai-analyze")
@api_key_required
def external_ai_analyze():
    """
    外部系统执行 AI 智能审计
    """
    payload = request.get_json(silent=True) or {}
    db_type = payload.get("db_type")
    cluster_id = payload.get("cluster_id")
    database = payload.get("database")
    statement = payload.get("statement")
    product = payload.get("product") or payload.get("business_line")
    environment = payload.get("environment")
    
    if not all([db_type, cluster_id, database, statement]):
        return error_response("missing required fields (db_type, cluster_id, database, statement)", code=400)
        
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    
    scope_err = _validate_scope(payload, cluster)
    if scope_err: return error_response(scope_err, code=400)

    if not require_cluster_permission(cluster.id, "query"):
        return error_response("no permission for this cluster", code=403)
        
    config = AIModelConfig.query.filter_by(is_default=True, enabled=True).first()
    if not config: config = AIModelConfig.query.filter_by(enabled=True).first()
    if not config: return error_response("no enabled AI model config found", code=400)
        
    instance = pick_instance(db_type, cluster_id, None, for_change=False)
    if not instance: return error_response("no available instance to fetch metadata", code=400)
        
    try:
        if db_type == "mysql":
            metadata = get_mysql_metadata(instance, database)
        elif db_type == "mongodb":
            metadata = get_mongodb_metadata(instance, database)
        else:
            return error_response(f"AI analysis not supported for {db_type}", code=400)
            
        sql_list = [s.strip() for s in statement.split("\n") if s.strip()]
        analysis_result = analyze_sql_with_ai(config, db_type, metadata, sql_list)
        
        is_allowed = "[建议放行]" in analysis_result
        
        return ok_response(data={
            "analysis": analysis_result,
            "can_release": is_allowed,
            "db_type": db_type,
            "cluster_name": cluster.name,
            "database": database
        })
    except Exception as e:
        return error_response(f"AI Analysis failed: {str(e)}", code=500)
