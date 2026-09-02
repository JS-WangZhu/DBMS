from app.extensions import db
from app.models.sql_release_config import SqlReleaseConfig


def get_or_create_sql_release_config():
    config = SqlReleaseConfig.query.order_by(SqlReleaseConfig.id.asc()).first()
    if config:
        return config
    config = SqlReleaseConfig(ai_review_enabled=True)
    db.session.add(config)
    db.session.commit()
    return config


def is_sql_release_ai_review_enabled():
    return bool(get_or_create_sql_release_config().ai_review_enabled)
