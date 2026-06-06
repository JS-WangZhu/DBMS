from app.extensions import db
from app.models.aliyun_dns import AliyunDomainConfig


def _admin_headers(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    token = resp.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_aliyun_domain_config_masks_secret_key(client):
    headers = _admin_headers(client)

    resp = client.post(
        "/api/v1/aliyun-dns/configs",
        json={
            "name": "prod",
            "access_key": "ak",
            "secret_key": "sk",
            "domains": ["example.com", "example.net"],
            "enabled": True,
        },
        headers=headers,
    )

    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["domains"] == ["example.com", "example.net"]
    assert data["secret_key_set"] is True
    assert "secret_key" not in data


def test_aliyun_dns_rejects_domain_not_in_config(client, monkeypatch):
    headers = _admin_headers(client)
    with client.application.app_context():
        db.session.add(
            AliyunDomainConfig(
                name="prod",
                access_key="ak",
                secret_key="sk",
                domains=["example.com"],
                enabled=True,
            )
        )
        db.session.commit()

    def fail_call(*args, **kwargs):
        raise AssertionError("Aliyun API should not be called")

    monkeypatch.setattr("app.api.routes.aliyun_dns.call_alidns_api", fail_call)

    resp = client.get(
        "/api/v1/aliyun-dns/records?config_id=1&domain=other.com",
        headers=headers,
    )

    assert resp.status_code == 400
    assert "not managed" in resp.get_json()["message"]


def test_aliyun_dns_record_actions_send_expected_parameters(client, monkeypatch):
    headers = _admin_headers(client)
    with client.application.app_context():
        db.session.add(
            AliyunDomainConfig(
                name="prod",
                access_key="ak",
                secret_key="sk",
                domains=["example.com"],
                enabled=True,
            )
        )
        db.session.commit()

    calls = []

    def fake_call(config, action, params):
        calls.append((action, params))
        return {"RequestId": "req", "RecordId": params.get("RecordId") or "new-id"}

    monkeypatch.setattr("app.api.routes.aliyun_dns.call_alidns_api", fake_call)

    add_resp = client.post(
        "/api/v1/aliyun-dns/records",
        json={
            "config_id": 1,
            "domain": "example.com",
            "rr": "www",
            "type": "A",
            "value": "192.0.2.10",
            "ttl": 600,
        },
        headers=headers,
    )
    update_resp = client.patch(
        "/api/v1/aliyun-dns/records/old-id",
        json={
            "config_id": 1,
            "domain": "example.com",
            "rr": "@",
            "type": "CNAME",
            "value": "target.example.com",
            "ttl": 600,
        },
        headers=headers,
    )
    delete_resp = client.delete(
        "/api/v1/aliyun-dns/records/old-id?config_id=1&domain=example.com",
        headers=headers,
    )

    assert add_resp.status_code == 201
    assert update_resp.status_code == 200
    assert delete_resp.status_code == 200
    assert calls == [
        (
            "AddDomainRecord",
            {"DomainName": "example.com", "RR": "www", "Type": "A", "Value": "192.0.2.10", "TTL": 600},
        ),
        (
            "UpdateDomainRecord",
            {"RecordId": "old-id", "RR": "@", "Type": "CNAME", "Value": "target.example.com", "TTL": 600},
        ),
        ("DeleteDomainRecord", {"RecordId": "old-id"}),
    ]
