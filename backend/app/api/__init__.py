from flask import Blueprint

from app.api.routes.ai_routes import bp as ai_bp
from app.api.routes.auth import bp as auth_bp
from app.api.routes.backups import bp as backups_bp
from app.api.routes.backup_agents import bp as backup_agents_bp
from app.api.routes.backup_tools import bp as backup_tools_bp
from app.api.routes.backup_keys import bp as backup_keys_bp
from app.api.routes.clusters import bp as clusters_bp
from app.api.routes.doris import bp as doris_bp
from app.api.routes.dns import bp as dns_bp
from app.api.routes.data_access import bp as data_access_bp
from app.api.routes.data_query_ops import bp as data_query_ops_bp
from app.api.routes.health import bp as health_bp
from app.api.routes.ha_configs import bp as ha_configs_bp
from app.api.routes.instances import bp as instances_bp
from app.api.routes.inspection import bp as inspection_bp
from app.api.routes.metrics import bp as metrics_bp
from app.api.routes.mongodb import bp as mongodb_bp
from app.api.routes.monitoring import bp as monitoring_bp
from app.api.routes.mysql import bp as mysql_bp
from app.api.routes.redis import bp as redis_bp
from app.api.routes.s3_storage import bp as s3_storage_bp
from app.api.routes.sso_config import bp as sso_config_bp
from app.api.routes.users import bp as users_bp
from app.api.routes.user_permissions import bp as user_permissions_bp
from app.api.routes.doc import bp as doc_bp
from app.api.routes.external import bp as external_bp


def register_blueprints(app):
    api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")
    api_v1.register_blueprint(health_bp)
    api_v1.register_blueprint(ha_configs_bp)
    api_v1.register_blueprint(auth_bp)
    api_v1.register_blueprint(users_bp)
    api_v1.register_blueprint(user_permissions_bp)
    api_v1.register_blueprint(clusters_bp)
    api_v1.register_blueprint(instances_bp)
    api_v1.register_blueprint(inspection_bp)
    api_v1.register_blueprint(mysql_bp)
    api_v1.register_blueprint(mongodb_bp)
    api_v1.register_blueprint(redis_bp)
    api_v1.register_blueprint(doris_bp)
    api_v1.register_blueprint(monitoring_bp)
    api_v1.register_blueprint(metrics_bp)
    api_v1.register_blueprint(backups_bp)
    api_v1.register_blueprint(backup_agents_bp)
    api_v1.register_blueprint(backup_tools_bp)
    api_v1.register_blueprint(backup_keys_bp)
    api_v1.register_blueprint(dns_bp)
    api_v1.register_blueprint(data_access_bp)
    api_v1.register_blueprint(data_query_ops_bp)
    api_v1.register_blueprint(s3_storage_bp)
    api_v1.register_blueprint(sso_config_bp)
    api_v1.register_blueprint(ai_bp)
    api_v1.register_blueprint(doc_bp)
    api_v1.register_blueprint(external_bp)

    app.register_blueprint(api_v1)
