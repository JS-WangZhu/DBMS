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
    MONGODUMP_PATH = os.getenv("MONGODUMP_PATH", "mongodump")

    # Backup Agent configuration
    BACKUP_AGENT_URL = os.getenv("BACKUP_AGENT_URL", "http://localhost:5001")
    ENABLE_REMOTE_AGENT = _as_bool(os.getenv("ENABLE_REMOTE_AGENT", "false"), default=False)


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    ENABLE_SCHEDULER = False
    AUTO_BOOTSTRAP_ADMIN = False
