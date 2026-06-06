import os
import threading

from dotenv import load_dotenv
from flask import Flask

from app.api import register_blueprints
from app.extensions import db, jwt, migrate, scheduler


def create_app(config_object=None):
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    load_dotenv(dotenv_path=env_path, override=True)

    # Config reads env at import time; import it only after load_dotenv.
    from app.config import Config

    app = Flask(__name__)
    app.config.from_object(config_object or Config)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    register_blueprints(app)

    with app.app_context():
        from app import models  # noqa: F401
        from app.services.bootstrap import ensure_admin_user, ensure_backup_extra_columns, seed_data_query_operations

        db.create_all()
        ensure_backup_extra_columns()
        seed_data_query_operations()
        if app.config.get("AUTH_MODE") == "local" and app.config.get("AUTO_BOOTSTRAP_ADMIN"):
            ensure_admin_user(
                username=app.config.get("BOOTSTRAP_ADMIN_USERNAME", "admin"),
                password=app.config.get("BOOTSTRAP_ADMIN_PASSWORD", "admin123"),
            )

    if app.config.get("ENABLE_SCHEDULER") and not app.config.get("TESTING"):
        from app.tasks.scheduler import job_warm_redis_cache, register_jobs

        scheduler.init_app(app)
        register_jobs(scheduler, app)

        if not scheduler.running:
            # Avoid double start in flask debug reloader.
            if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
                scheduler.start()
                threading.Thread(
                    target=job_warm_redis_cache,
                    kwargs={"app": app},
                    name="redis-cache-warm-startup",
                    daemon=True,
                ).start()

    return app
