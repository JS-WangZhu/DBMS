from flask import Blueprint, request, Response, stream_with_context
from app.api.routes.common import active_user_required, require_menu_permission, require_cluster_permission, api_key_required
from app.models.ai_config import AIModelConfig
from app.models.db_asset import DatabaseCluster
from app.services.ai_service import get_mysql_metadata, get_mongodb_metadata, analyze_sql_with_ai, analyze_sql_with_ai_stream
from app.services.data_access import pick_instance
from app.utils.response import ok_response, error_response
from app.extensions import db

bp = Blueprint("ai", __name__, url_prefix="/ai")

@bp.get("/configs")
@require_menu_permission("ai_model_config")
def list_ai_configs():
    try:
        configs = AIModelConfig.query.all()
        return ok_response(data=[c.to_dict() for c in configs])
    except Exception as e:
        # If table doesn't exist, try to create it (safety for new features)
        if "no such table" in str(e).lower():
            try:
                db.create_all()
                return ok_response(data=[])
            except:
                pass
        return error_response(f"Database error: {str(e)}", code=500)

@bp.post("/configs")
@require_menu_permission("ai_model_config")
def create_ai_config():
    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    api_url = payload.get("api_url")
    api_key = payload.get("api_key")
    model_name = payload.get("model_name")
    
    if not all([name, api_url, api_key, model_name]):
        return error_response("missing required fields", code=400)
        
    config = AIModelConfig(
        name=name,
        api_url=api_url,
        api_key=api_key,
        model_name=model_name,
        is_default=payload.get("is_default", False),
        enabled=payload.get("enabled", True)
    )
    
    if config.is_default:
        AIModelConfig.query.update({AIModelConfig.is_default: False})
        
    db.session.add(config)
    db.session.commit()
    return ok_response(data=config.to_dict())

@bp.patch("/configs/<int:config_id>")
@require_menu_permission("ai_model_config")
def update_ai_config(config_id):
    config = AIModelConfig.query.get_or_404(config_id)
    payload = request.get_json(silent=True) or {}
    
    if "name" in payload: config.name = payload["name"]
    if "api_url" in payload: config.api_url = payload["api_url"]
    if "api_key" in payload and payload["api_key"] and "******" not in payload["api_key"]:
        config.api_key = payload["api_key"]
    if "model_name" in payload: config.model_name = payload["model_name"]
    if "is_default" in payload:
        config.is_default = payload["is_default"]
        if config.is_default:
            AIModelConfig.query.filter(AIModelConfig.id != config_id).update({AIModelConfig.is_default: False})
    if "enabled" in payload: config.enabled = payload["enabled"]
    
    db.session.commit()
    return ok_response(data=config.to_dict())

@bp.delete("/configs/<int:config_id>")
@require_menu_permission("ai_model_config")
def delete_ai_config(config_id):
    config = AIModelConfig.query.get_or_404(config_id)
    db.session.delete(config)
    db.session.commit()
    return ok_response()

@bp.post("/analyze")
@require_menu_permission("ai_analysis")
def perform_ai_analysis():
    payload = request.get_json(silent=True) or {}
    db_type = payload.get("db_type")
    cluster_id = payload.get("cluster_id")
    database = payload.get("database")
    statement = payload.get("statement") # Can be multiple sqls separated by newline
    product = payload.get("product") or payload.get("business_line")
    environment = payload.get("environment")
    
    if not all([db_type, cluster_id, database, statement]):
        return error_response("missing required fields", code=400)
        
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    
    # 校验业务线和环境
    if product and (cluster.business_line or cluster.namespace) != product:
        return error_response(f"product mismatch: expected {cluster.business_line or cluster.namespace}, got {product}", code=400)
    if environment and (cluster.environment or "") != environment:
        return error_response(f"environment mismatch: expected {cluster.environment}, got {environment}", code=400)

    if not require_cluster_permission(cluster.id, "query"):
        return error_response("no permission for this cluster", code=403)
        
    # Get AI config
    config = AIModelConfig.query.filter_by(is_default=True, enabled=True).first()
    if not config:
        config = AIModelConfig.query.filter_by(enabled=True).first()
    if not config:
        return error_response("no enabled AI model config found", code=400)
        
    # Get metadata
    instance = pick_instance(db_type, cluster_id, None, for_change=False)
    if not instance:
        return error_response("no available instance to fetch metadata", code=400)
        
    try:
        if db_type == "mysql":
            metadata = get_mysql_metadata(instance, database)
        elif db_type == "mongodb":
            metadata = get_mongodb_metadata(instance, database)
        else:
            return error_response(f"AI analysis not supported for {db_type}", code=400)
            
        sql_list = [s.strip() for s in statement.split("\n") if s.strip()]
        analysis_result = analyze_sql_with_ai(config, db_type, metadata, sql_list)
        
        return ok_response(data={"analysis": analysis_result})
    except Exception as e:
        import traceback
        print(f"[AI Analysis Error] {str(e)}")
        traceback.print_exc()
        return error_response(f"Analysis failed: {str(e)}", code=500)

@bp.post("/analyze/stream")
@require_menu_permission("ai_analysis")
def perform_ai_analysis_stream():
    payload = request.get_json(silent=True) or {}
    db_type = payload.get("db_type")
    cluster_id = payload.get("cluster_id")
    database = payload.get("database")
    statement = payload.get("statement")
    product = payload.get("product") or payload.get("business_line")
    environment = payload.get("environment")
    
    if not all([db_type, cluster_id, database, statement]):
        return error_response("missing required fields", code=400)
        
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    
    # 校验业务线和环境
    if product and (cluster.business_line or cluster.namespace) != product:
        return error_response(f"product mismatch: expected {cluster.business_line or cluster.namespace}, got {product}", code=400)
    if environment and (cluster.environment or "") != environment:
        return error_response(f"environment mismatch: expected {cluster.environment}, got {environment}", code=400)

    if not require_cluster_permission(cluster.id, "query"):
        return error_response("no permission for this cluster", code=403)
        
    config = AIModelConfig.query.filter_by(is_default=True, enabled=True).first()
    if not config:
        config = AIModelConfig.query.filter_by(enabled=True).first()
    if not config:
        return error_response("no enabled AI model config found", code=400)
        
    instance = pick_instance(db_type, cluster_id, None, for_change=False)
    if not instance:
        return error_response("no available instance to fetch metadata", code=400)
        
    try:
        if db_type == "mysql":
            metadata = get_mysql_metadata(instance, database)
        elif db_type == "mongodb":
            metadata = get_mongodb_metadata(instance, database)
        else:
            return error_response(f"AI analysis not supported for {db_type}", code=400)
            
        sql_list = [s.strip() for s in statement.split("\n") if s.strip()]
        
        def generate():
            for chunk in analyze_sql_with_ai_stream(config, db_type, metadata, sql_list):
                yield f"data: {chunk}\n\n"
        
        return Response(
            stream_with_context(generate()), 
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',  # 禁用 Nginx 缓存，确保实时流式输出
                'Connection': 'keep-alive'
            }
        )
    except Exception as e:
        return error_response(f"Analysis failed: {str(e)}", code=500)
