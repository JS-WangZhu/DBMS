import csv
import io

from app.models.audit_log import AuditLog
from app.models.db_asset import DatabaseInstance
from app.models.jumpserver_config import JumpServerConfig
from app.models.user import User
from app.models.user_permission import UserMenuPermission


def _admin_headers(client):
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    token = response.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_config(client, headers, **overrides):
    payload = {
        "name": "生产 JumpServer",
        "base_url": "https://jump.example.com/",
        "web_url_template": "{base_url}/luna/?asset={asset_id}",
        "verify_ssl": True,
        "enabled": True,
    }
    payload.update(overrides)
    return client.post("/api/v1/jumpserver-configs", json=payload, headers=headers)


def _mapping_csv(rows):
    fields = [
        "instance_id",
        "db_type",
        "instance_name",
        "host",
        "port",
        "jumpserver_config_id",
        "jumpserver_config_name",
        "jumpserver_asset_id",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def test_jumpserver_config_binding_and_access_url(client):
    headers = _admin_headers(client)
    config_response = _create_config(client, headers)
    assert config_response.status_code == 201
    config = config_response.get_json()["data"]
    assert config["base_url"] == "https://jump.example.com"

    options_response = client.get("/api/v1/jumpserver-configs/options", headers=headers)
    assert options_response.status_code == 200
    assert options_response.get_json()["data"] == [{"id": config["id"], "name": "生产 JumpServer"}]

    create_response = client.post(
        "/api/v1/mysql/instances",
        json={
            "name": "mysql-jumpserver-test",
            "host_input": "127.0.0.1",
            "port": 3306,
            "jumpserver_config_id": config["id"],
            "jumpserver_asset_id": "asset/abc",
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    instance_data = create_response.get_json()["data"]
    assert instance_data["jumpserver_config_name"] == "生产 JumpServer"
    assert instance_data["jumpserver_config_enabled"] is True

    access_response = client.post(
        f"/api/v1/instances/{instance_data['id']}/jumpserver-access",
        headers=headers,
    )
    assert access_response.status_code == 200
    assert access_response.get_json()["data"]["url"] == "https://jump.example.com/luna/?asset=asset%2Fabc"

    audit = AuditLog.query.filter_by(action="instance.jumpserver.access", target_id=str(instance_data["id"])).first()
    assert audit is not None
    assert audit.detail_json["jumpserver_asset_id"] == "asset/abc"

    delete_response = client.delete(f"/api/v1/jumpserver-configs/{config['id']}", headers=headers)
    assert delete_response.status_code == 409


def test_jumpserver_binding_requires_config_and_asset_together(client):
    headers = _admin_headers(client)
    config = _create_config(client, headers).get_json()["data"]

    response = client.post(
        "/api/v1/mongodb/instances",
        json={
            "name": "mongodb-invalid-binding",
            "host_input": "127.0.0.1",
            "port": 27017,
            "jumpserver_config_id": config["id"],
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert "jumpserver_asset_id is required" in response.get_json()["message"]


def test_jumpserver_template_cannot_redirect_to_another_host(client):
    headers = _admin_headers(client)
    response = _create_config(
        client,
        headers,
        web_url_template="https://evil.example/{base_url}?asset={asset_id}",
    )
    assert response.status_code == 400
    assert "configured JumpServer host" in response.get_json()["message"]
    assert JumpServerConfig.query.count() == 0


def test_disabled_jumpserver_cannot_be_newly_bound_or_opened(client):
    headers = _admin_headers(client)
    config = _create_config(client, headers).get_json()["data"]
    instance = DatabaseInstance(
        name="existing-disabled-binding",
        db_type="redis",
        host_input="127.0.0.1",
        port=6379,
        jumpserver_config_id=config["id"],
        jumpserver_asset_id="asset-disabled",
    )
    from app.extensions import db

    db.session.add(instance)
    db.session.commit()

    update_response = client.patch(
        f"/api/v1/jumpserver-configs/{config['id']}",
        json={"enabled": False},
        headers=headers,
    )
    assert update_response.status_code == 200

    access_response = client.post(f"/api/v1/instances/{instance.id}/jumpserver-access", headers=headers)
    assert access_response.status_code == 409

    create_response = client.post(
        "/api/v1/redis/instances",
        json={
            "name": "redis-new-disabled-binding",
            "host_input": "127.0.0.1",
            "port": 6379,
            "jumpserver_config_id": config["id"],
            "jumpserver_asset_id": "asset-new",
        },
        headers=headers,
    )
    assert create_response.status_code == 400
    assert "disabled" in create_response.get_json()["message"]


def test_jumpserver_access_requires_database_menu_permission(client):
    headers = _admin_headers(client)
    config = _create_config(client, headers).get_json()["data"]
    instance = DatabaseInstance(
        name="permission-test-instance",
        db_type="mysql",
        host_input="127.0.0.1",
        port=3306,
        jumpserver_config_id=config["id"],
        jumpserver_asset_id="asset-permission",
    )
    user = User(username="jump-user", role="user", status="active", auth_source="local")
    user.set_password("jump-password")
    from app.extensions import db

    db.session.add_all([instance, user])
    db.session.commit()

    login = client.post("/api/v1/auth/login", json={"username": "jump-user", "password": "jump-password"})
    assert login.get_json()["data"]["user"]["role"] == "user"
    user_headers = {"Authorization": f"Bearer {login.get_json()['data']['access_token']}"}
    # The shared test app context keeps flask.g between requests; production request
    # contexts do not. Clear the preceding admin request's cached user explicitly.
    from flask import g

    g.pop("current_user", None)
    denied = client.post(f"/api/v1/instances/{instance.id}/jumpserver-access", headers=user_headers)
    assert denied.status_code == 403

    db.session.add(UserMenuPermission(user_id=user.id, menu_key="mysql_instances"))
    db.session.commit()
    allowed = client.post(f"/api/v1/instances/{instance.id}/jumpserver-access", headers=user_headers)
    assert allowed.status_code == 200


def test_download_template_and_import_instance_mappings(client):
    headers = _admin_headers(client)
    config = _create_config(client, headers).get_json()["data"]
    first = DatabaseInstance(name="csv-mysql", db_type="mysql", host_input="10.0.0.1", port=3306)
    second = DatabaseInstance(name="csv-redis", db_type="redis", host_input="10.0.0.2", port=6379)
    from app.extensions import db

    db.session.add_all([first, second])
    db.session.commit()

    template_response = client.get("/api/v1/jumpserver-configs/mapping-template", headers=headers)
    assert template_response.status_code == 200
    template_text = template_response.data.decode("utf-8-sig")
    assert "instance_id,db_type,instance_name,host,port" in template_text
    assert f"{first.id},mysql,csv-mysql,10.0.0.1,3306" in template_text

    content = _mapping_csv(
        [
            {
                "instance_id": first.id,
                "db_type": "mysql",
                "instance_name": "csv-mysql",
                "host": "10.0.0.1",
                "port": 3306,
                "jumpserver_config_id": config["id"],
                "jumpserver_asset_id": "mysql-asset-id",
            },
            {
                "instance_id": second.id,
                "db_type": "redis",
                "instance_name": "csv-redis",
                "host": "10.0.0.2",
                "port": 6379,
                "jumpserver_config_name": "生产 JumpServer",
                "jumpserver_asset_id": "redis-asset-id",
            },
        ]
    )
    response = client.post(
        "/api/v1/jumpserver-configs/mapping-import",
        data={"file": (io.BytesIO(content), "mapping.csv")},
        content_type="multipart/form-data",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["imported_count"] == 2
    db.session.refresh(first)
    db.session.refresh(second)
    assert (first.jumpserver_config_id, first.jumpserver_asset_id) == (config["id"], "mysql-asset-id")
    assert (second.jumpserver_config_id, second.jumpserver_asset_id) == (config["id"], "redis-asset-id")
    audit = AuditLog.query.filter_by(action="jumpserver.mapping.import").first()
    assert audit is not None
    assert audit.detail_json["count"] == 2


def test_mapping_csv_validation_is_atomic(client):
    headers = _admin_headers(client)
    config = _create_config(client, headers).get_json()["data"]
    instance = DatabaseInstance(name="csv-atomic", db_type="postgresql", host_input="10.0.0.3", port=5432)
    from app.extensions import db

    db.session.add(instance)
    db.session.commit()
    content = _mapping_csv(
        [
            {
                "instance_id": instance.id,
                "db_type": "postgresql",
                "instance_name": "csv-atomic",
                "host": "10.0.0.3",
                "port": 5432,
                "jumpserver_config_id": config["id"],
                "jumpserver_asset_id": "would-have-been-imported",
            },
            {
                "instance_id": 999999,
                "db_type": "mysql",
                "instance_name": "missing",
                "host": "10.0.0.99",
                "port": 3306,
                "jumpserver_config_id": config["id"],
                "jumpserver_asset_id": "missing-asset",
            },
        ]
    )
    response = client.post(
        "/api/v1/jumpserver-configs/mapping-import",
        data={"file": (io.BytesIO(content), "mapping.csv")},
        content_type="multipart/form-data",
        headers=headers,
    )
    assert response.status_code == 400
    result = response.get_json()
    assert result["data"]["error_count"] == 1
    assert result["data"]["errors"][0]["row"] == 3
    db.session.refresh(instance)
    assert instance.jumpserver_config_id is None
    assert instance.jumpserver_asset_id is None
