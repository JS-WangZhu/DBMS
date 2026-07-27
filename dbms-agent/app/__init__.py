import logging
import os
import threading

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

    recovery_process = os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.config.get("AGENT_DEBUG")
    if app.config.get("AGENT_RECOVERY_ENABLED") and not app.config.get("TESTING") and recovery_process:
        from app.api.routes.agent import recover_backup_tasks_on_startup

        threading.Thread(
            target=recover_backup_tasks_on_startup,
            args=(app,),
            name="backup-task-recovery",
            daemon=True,
        ).start()

    return app
