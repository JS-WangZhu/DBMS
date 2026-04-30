import logging

from flask import Flask

from app.config import get_config
from app.api.routes import agent_bp


def create_app(config_class=None):
    """Create and configure the Flask application"""
    app = Flask(__name__)

    if config_class is None:
        config_class = get_config()

    app.config.from_object(config_class)

    logging.basicConfig(
        level=getattr(logging, app.config.get("LOG_LEVEL", "INFO")),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    app.register_blueprint(agent_bp)

    return app