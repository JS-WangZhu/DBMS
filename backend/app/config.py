import os
from datetime import timedelta


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=7)
    AUTH_IDLE_TIMEOUT_SECONDS = int(os.getenv("AUTH_IDLE_TIMEOUT_SECONDS", "28800"))
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///dbms_meta.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
        "pool_pre_ping": _as_bool(os.getenv("DB_POOL_PRE_PING", "true"), default=True),
    }

    AUTH_MODE = os.getenv("AUTH_MODE", "local")
    LDAP_SERVER_URI = os.getenv("LDAP_SERVER_URI", "")
    LDAP_BASE_DN = os.getenv("LDAP_BASE_DN", "")
    LDAP_USER_DN_TEMPLATE = os.getenv("LDAP_USER_DN_TEMPLATE", "")
    SSO_ENABLED = _as_bool(os.getenv("SSO_ENABLED", "false"), default=False)
    SSO_PROVIDER_NAME = os.getenv("SSO_PROVIDER_NAME", "SSO")
    SSO_CLIENT_ID = os.getenv("SSO_CLIENT_ID", "")
    SSO_CLIENT_SECRET = os.getenv("SSO_CLIENT_SECRET", "")
    SSO_AUTHORIZE_URL = os.getenv("SSO_AUTHORIZE_URL", "")
    SSO_TOKEN_URL = os.getenv("SSO_TOKEN_URL", "")
    SSO_USERINFO_URL = os.getenv("SSO_USERINFO_URL", "")
    SSO_SCOPE = os.getenv("SSO_SCOPE", "openid profile email")
    SSO_REDIRECT_URI = os.getenv("SSO_REDIRECT_URI", "")
    SSO_USERNAME_FIELD = os.getenv("SSO_USERNAME_FIELD", "preferred_username")
    SSO_EMAIL_FIELD = os.getenv("SSO_EMAIL_FIELD", "email")
    AUTO_BOOTSTRAP_ADMIN = _as_bool(os.getenv("AUTO_BOOTSTRAP_ADMIN", "true"), default=True)
    BOOTSTRAP_ADMIN_USERNAME = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
    BOOTSTRAP_ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "admin123")

    ENABLE_SCHEDULER = _as_bool(os.getenv("ENABLE_SCHEDULER", "true"), default=True)
    SCHEDULER_TIMEZONE = os.getenv("SCHEDULER_TIMEZONE", "Asia/Shanghai")
    MONITOR_COLLECT_WORKERS = int(os.getenv("MONITOR_COLLECT_WORKERS", "8"))

    FEEDBACK_IMAGE_DIR = os.getenv(
        "FEEDBACK_IMAGE_DIR",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "feedback_images")),
    )
    FEEDBACK_IMAGE_MAX_COUNT = int(os.getenv("FEEDBACK_IMAGE_MAX_COUNT", "5"))
    FEEDBACK_IMAGE_MAX_BYTES = int(os.getenv("FEEDBACK_IMAGE_MAX_BYTES", str(5 * 1024 * 1024)))

    REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

    CLICKHOUSE_AUDIT_HOST = os.getenv("CLICKHOUSE_AUDIT_HOST", "")
    CLICKHOUSE_AUDIT_PORT = int(os.getenv("CLICKHOUSE_AUDIT_PORT", "8123"))
    CLICKHOUSE_AUDIT_USER = os.getenv("CLICKHOUSE_AUDIT_USER", os.getenv("CLICKHOUSE_USER", "default"))
    CLICKHOUSE_AUDIT_PASSWORD = os.getenv("CLICKHOUSE_AUDIT_PASSWORD", os.getenv("CLICKHOUSE_PASSWORD", ""))
    CLICKHOUSE_AUDIT_DATABASE = os.getenv("CLICKHOUSE_AUDIT_DATABASE", os.getenv("CLICKHOUSE_DB", "dbms_audit"))
    CLICKHOUSE_AUDIT_TABLE = os.getenv("CLICKHOUSE_AUDIT_TABLE", "query_audit_events")
    CLICKHOUSE_AUDIT_SECURE = _as_bool(os.getenv("CLICKHOUSE_AUDIT_SECURE", "false"))
    CLICKHOUSE_AUDIT_VERIFY = _as_bool(os.getenv("CLICKHOUSE_AUDIT_VERIFY", "true"), default=True)
    CLICKHOUSE_AUDIT_CONNECT_TIMEOUT = int(os.getenv("CLICKHOUSE_AUDIT_CONNECT_TIMEOUT", "5"))
    CLICKHOUSE_AUDIT_QUERY_TIMEOUT = int(os.getenv("CLICKHOUSE_AUDIT_QUERY_TIMEOUT", "15"))

    # Generated from SECRET_KEY when empty
    FERNET_KEY = os.getenv("FERNET_KEY", "")

    WECHAT_WEBHOOK_URL = os.getenv("WECHAT_WEBHOOK_URL", "")
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "25"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_USE_TLS = _as_bool(os.getenv("SMTP_USE_TLS", "true"), default=True)
    SMTP_FROM = os.getenv("SMTP_FROM", "")
    SMTP_TO = os.getenv("SMTP_TO", "")
    BACKUP_NOTIFY_CHANNELS = os.getenv("BACKUP_NOTIFY_CHANNELS", "wecom,email")
    
    # Backup tools configuration
    MYSQLDUMP_PATH = os.getenv("MYSQLDUMP_PATH", "mysqldump")
    SQL_RELEASE_BACKUP_DIR = os.getenv("SQL_RELEASE_BACKUP_DIR", "data/sql_release_backups")
    SQL_RELEASE_ROLLBACK_MAX_ROWS = int(os.getenv("SQL_RELEASE_ROLLBACK_MAX_ROWS", "10000"))
    MONGODUMP_PATH = os.getenv("MONGODUMP_PATH", "mongodump")
    PGDUMP_PATH = os.getenv("PGDUMP_PATH", "pg_dump")

    # Backup Agent configuration
    BACKUP_AGENT_URL = os.getenv("BACKUP_AGENT_URL", "http://localhost:5001")
    ENABLE_REMOTE_AGENT = _as_bool(os.getenv("ENABLE_REMOTE_AGENT", "false"), default=False)


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    ENABLE_SCHEDULER = False
    AUTO_BOOTSTRAP_ADMIN = False
