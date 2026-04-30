import os
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.models.user import User


@pytest.fixture
def app():
    app = create_app(config_object=TestingConfig)
    with app.app_context():
        db.create_all()

        admin = User(username="admin", role="admin", status="active", auth_source="local")
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()

        yield app

        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
