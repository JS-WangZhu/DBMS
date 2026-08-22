from datetime import datetime

from flask import g
from flask import has_app_context
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from app.api.routes.user_permissions import MENU_KEY_SET
from app.extensions import db
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.diagnosis import ParameterCollectionSnapshot
from app.models.user import User
from app.models.user_permission import UserClusterPermission, UserMenuPermission
from app.services.diagnosis import get_or_create_parameter_collection_config, run_parameter_collection
from app.services.parameter_collector import _item


def _login(client, username, password="password123"):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def test_diagnosis_permissions_are_assignable():
    assert "diagnosis_parameter_check" in MENU_KEY_SET
    assert "diagnosis_slow_query" in MENU_KEY_SET


def test_parameter_snapshot_mysql_foreign_key_matches_bigint_instance_id():
    ddl = str(CreateTable(ParameterCollectionSnapshot.__table__).compile(dialect=mysql.dialect()))
    assert "instance_id BIGINT NOT NULL" in ddl
    assert "FOREIGN KEY(instance_id) REFERENCES db_instances (id)" in ddl


def test_sensitive_parameter_names_are_masked_before_storage():
    assert _item("require_secure_transport", "ON")["value"] == "ON"
    assert _item("cloud_secret_token", "not-safe")["value"] == "******"
    assert _item("security", {"privateKey": "not-safe", "mode": "enabled"})["value"] == {
        "privateKey": "******", "mode": "enabled",
    }


def test_default_parameter_collection_job_runs_at_midnight(app):
    from app.tasks.scheduler import sync_parameter_collection_job

    class FakeScheduler:
        def __init__(self):
            self.jobs = {}

        def get_job(self, job_id):
            return self.jobs.get(job_id)

        def remove_job(self, job_id):
            self.jobs.pop(job_id, None)

        def add_job(self, **kwargs):
            self.jobs[kwargs["id"]] = kwargs

    fake = FakeScheduler()
    sync_parameter_collection_job(fake, app)
    job = fake.jobs["diagnosis_parameter_collection"]
    assert "hour='0'" in str(job["trigger"])
    assert "minute='0'" in str(job["trigger"])
    assert job["max_instances"] == 1


def test_parameter_collection_config_api_is_admin_writable(app, client):
    with app.app_context():
        user = User(username="diagnosis-config-reader", role="user", status="active", auth_source="local")
        user.set_password("password123")
        cluster = DatabaseCluster(name="retention-config-cluster", db_type="mysql")
        db.session.add_all([user, cluster])
        db.session.flush()
        instance = DatabaseInstance(
            name="retention-config-instance", db_type="mysql", host_input="127.0.0.1",
            port=3306, cluster_id=cluster.id,
        )
        db.session.add(instance)
        db.session.flush()
        db.session.add_all([
            UserMenuPermission(user_id=user.id, menu_key="diagnosis_parameter_check"),
            *[
                ParameterCollectionSnapshot(
                    instance_id=instance.id, collected_at=datetime.utcnow(), status="success",
                    parameter_count=1, parameters_json=[{"name": "version", "value": str(index)}],
                )
                for index in range(4)
            ],
        ])
        db.session.commit()
        instance_id = instance.id

    admin_headers = _login(client, "admin", "admin123")
    loaded = client.get("/api/v1/diagnosis/parameter-check/config", headers=admin_headers)
    updated = client.put(
        "/api/v1/diagnosis/parameter-check/config",
        headers=admin_headers,
        json={"cron_expr": "30 1 * * *", "db_types": ["mysql", "redis"], "timeout_seconds": 20, "max_workers": 4, "retention_versions": 2},
    )
    g.pop("current_user", None)
    reader_update = client.put(
        "/api/v1/diagnosis/parameter-check/config",
        headers=_login(client, "diagnosis-config-reader"),
        json={"enabled": False},
    )

    assert loaded.status_code == 200
    assert loaded.get_json()["data"]["retention_versions"] == 3
    assert updated.status_code == 200
    assert updated.get_json()["data"]["db_types"] == ["mysql", "redis"]
    assert updated.get_json()["data"]["retention_versions"] == 2
    assert reader_update.status_code == 403
    with app.app_context():
        assert ParameterCollectionSnapshot.query.filter_by(instance_id=instance_id).count() == 2


def test_parameter_collection_uses_configured_retention_versions(app, monkeypatch):
    with app.app_context():
        cluster = DatabaseCluster(name="diagnosis-cluster", db_type="mysql")
        db.session.add(cluster)
        db.session.flush()
        instance = DatabaseInstance(
            name="diagnosis-mysql", db_type="mysql", host_input="127.0.0.1", port=3306,
            cluster_id=cluster.id, enabled=True, access_mode="server", password_encrypted="encrypted-value",
        )
        db.session.add(instance)
        config = get_or_create_parameter_collection_config()
        config.db_types_json = ["mysql"]
        config.retention_versions = 2
        db.session.commit()

        counter = {"value": 0}

        def fake_collect(_instance, _password, _timeout):
            counter["value"] += 1
            return [{"name": "max_connections", "value": str(counter["value"])}]

        def fake_decrypt(_encrypted):
            assert has_app_context() is True
            return "plain-password"

        monkeypatch.setattr("app.services.diagnosis.collect_database_parameters", fake_collect)
        monkeypatch.setattr("app.services.diagnosis.decrypt_secret", fake_decrypt)
        for _ in range(4):
            result = run_parameter_collection()
            assert result["success"] == 1

        versions = (
            ParameterCollectionSnapshot.query.filter_by(instance_id=instance.id)
            .order_by(ParameterCollectionSnapshot.id.asc())
            .all()
        )
        assert len(versions) == 2
        assert [row.parameters_json[0]["value"] for row in versions] == ["3", "4"]


def test_parameter_results_require_menu_and_cluster_view_scope(app, client):
    with app.app_context():
        user = User(username="diagnosis-reader", role="user", status="active", auth_source="local")
        user.set_password("password123")
        no_menu = User(username="diagnosis-no-menu", role="user", status="active", auth_source="local")
        no_menu.set_password("password123")
        allowed = DatabaseCluster(name="diagnosis-allowed", db_type="mysql", business_line="payment", environment="prod")
        denied = DatabaseCluster(name="diagnosis-denied", db_type="mysql", business_line="payment", environment="test")
        db.session.add_all([user, no_menu, allowed, denied])
        db.session.flush()
        allowed_instance = DatabaseInstance(name="allowed-db", db_type="mysql", host_input="10.0.0.1", port=3306, cluster_id=allowed.id)
        denied_instance = DatabaseInstance(name="denied-db", db_type="mysql", host_input="10.0.0.2", port=3306, cluster_id=denied.id)
        db.session.add_all([allowed_instance, denied_instance])
        db.session.flush()
        db.session.add_all([
            UserMenuPermission(user_id=user.id, menu_key="diagnosis_parameter_check"),
            UserClusterPermission(user_id=user.id, cluster_id=allowed.id, can_view_instance=True),
            UserClusterPermission(user_id=user.id, cluster_id=denied.id, can_query=True),
            UserClusterPermission(user_id=no_menu.id, cluster_id=allowed.id, can_view_instance=True),
            ParameterCollectionSnapshot(instance_id=allowed_instance.id, collected_at=datetime.utcnow(), status="success", parameter_count=1, parameters_json=[{"name": "a", "value": "1"}]),
            ParameterCollectionSnapshot(instance_id=denied_instance.id, collected_at=datetime.utcnow(), status="success", parameter_count=1, parameters_json=[{"name": "b", "value": "2"}]),
        ])
        db.session.commit()
        allowed_id = allowed_instance.id
        denied_id = denied_instance.id
        allowed_cluster_id = allowed.id
        denied_cluster_id = denied.id

    headers = _login(client, "diagnosis-reader")
    listed = client.get("/api/v1/diagnosis/parameter-check/instances", headers=headers)
    allowed_versions = client.get(f"/api/v1/diagnosis/parameter-check/instances/{allowed_id}/versions", headers=headers)
    denied_versions = client.get(f"/api/v1/diagnosis/parameter-check/instances/{denied_id}/versions", headers=headers)
    scoped = client.get(
        f"/api/v1/diagnosis/parameter-check/instances?business_line=payment&environment=prod&cluster_id={allowed_cluster_id}",
        headers=headers,
    )
    forced_denied = client.get(
        f"/api/v1/diagnosis/parameter-check/instances?cluster_id={denied_cluster_id}",
        headers=headers,
    )
    invalid_cluster = client.get(
        "/api/v1/diagnosis/parameter-check/instances?cluster_id=invalid",
        headers=headers,
    )
    assert listed.status_code == 200
    assert [item["instance_id"] for item in listed.get_json()["data"]["items"]] == [allowed_id]
    assert allowed_versions.status_code == 200
    assert allowed_versions.get_json()["data"]["versions"][0]["parameters"][0]["name"] == "a"
    assert denied_versions.status_code == 403
    assert scoped.status_code == 200
    assert scoped.get_json()["data"]["items"][0]["business_line"] == "payment"
    assert scoped.get_json()["data"]["items"][0]["environment"] == "prod"
    assert scoped.get_json()["data"]["items"][0]["cluster_name"] == "diagnosis-allowed"
    assert forced_denied.status_code == 200
    assert forced_denied.get_json()["data"]["items"] == []
    assert invalid_cluster.status_code == 400
    g.pop("current_user", None)
    missing_menu = client.get("/api/v1/diagnosis/parameter-check/instances", headers=_login(client, "diagnosis-no-menu"))
    assert missing_menu.status_code == 403
