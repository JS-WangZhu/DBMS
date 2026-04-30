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