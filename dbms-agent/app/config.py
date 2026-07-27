import os


class Config:
    """Base configuration for dbms-agent - No database dependency"""

    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

    # API Key for authentication (must match main server)
    AGENT_API_KEY = os.environ.get("AGENT_API_KEY", "")

    # Agent settings
    AGENT_HOST = os.environ.get("AGENT_HOST", "0.0.0.0")
    AGENT_PORT = int(os.environ.get("AGENT_PORT", 5001))
    AGENT_DEBUG = os.environ.get("AGENT_DEBUG", "false").lower() == "true"

    # Optional restart recovery. Existing agents that do not configure these
    # values keep the original in-memory execution path unchanged.
    AGENT_RECOVERY_ENABLED = os.environ.get("AGENT_RECOVERY_ENABLED", "false").lower() == "true"
    DBMS_SERVER_URL = os.environ.get("DBMS_SERVER_URL", "").strip()
    DBMS_AGENT_ID = os.environ.get("DBMS_AGENT_ID", "").strip()
    AGENT_TASK_STATE_DIR = os.environ.get("AGENT_TASK_STATE_DIR", "/tmp/dbms-agent-tasks").strip()

    # Logging
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


def get_config():
    """Get configuration based on environment"""
    env = os.environ.get("FLASK_ENV", "development")
    return config_by_name.get(env, config_by_name["default"])
