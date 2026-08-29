from unittest.mock import patch

from app.extensions import db
from app.models.aliyun_dns import AliyunDomainConfig
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.services.mysql_ha_switch import _run_aliyun_dns_switch


def _admin_headers(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    token = response.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _cluster(name, domain="ha.example.com"):
    row = DatabaseCluster(
        name=name,
        db_type="mysql",
        namespace="team-ha",
        business_line="team-ha",
        environment="prod",
        ha_domain=domain,
        ha_mode="dbms",
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_aliyun_domain_switch_updates_a_record_without_changing_status(app):
    cluster = _cluster("mysql-a")
    target = DatabaseInstance(
        name="mysql-a-2",
        db_type="mysql",
        host_input="mysql-a-2.internal",
        resolved_ip="10.10.0.22",
        port=3306,
        cluster_id=cluster.id,
    )
    config = AliyunDomainConfig(
        name="aliyun-prod",
        access_key="ak",
        secret_key="sk",
        domains=["example.com"],
        enabled=True,
    )
    db.session.add_all([target, config])
    db.session.commit()

    calls = []

    def fake_call(_config, action, params, timeout=10):
        calls.append((action, params))
        if action == "DescribeDomainRecords":
            return {
                "DomainRecords": {
                    "Record": [{
                        "RecordId": "record-1",
                        "RR": "ha",
                        "Type": "A",
                        "Value": "10.10.0.11",
                        "TTL": 60,
                        "Line": "default",
                        "Status": "Disable",
                    }]
                }
            }
        return {"RecordId": "record-1"}

    with patch("app.services.mysql_ha_switch.call_alidns_api", side_effect=fake_call):
        result = _run_aliyun_dns_switch(cluster, target)

    assert [item[0] for item in calls] == ["DescribeDomainRecords", "UpdateDomainRecord"]
    assert calls[1][1]["Value"] == "10.10.0.22"
    assert "Status" not in calls[1][1]
    assert result["record_status_changed"] is False


def test_ha_switch_marks_dns_propagation_pending(client):
    cluster = _cluster("mysql-dns-pending")
    headers = _admin_headers(client)

    with patch(
        "app.api.routes.clusters.normal_switch",
        return_value={
            "cluster_id": cluster.id,
            "new_master_instance_id": 22,
            "domain_switch": {"method": "aliyun", "target_ip": "10.10.0.22"},
        },
    ), patch("app.api.routes.clusters.notify_ha_switch_completion", return_value={"ok": False}):
        response = client.post(
            f"/api/v1/clusters/{cluster.id}/ha/switch",
            json={"switch_type": "normal", "target_instance_id": 22},
            headers=headers,
        )

    assert response.status_code == 200
    db.session.refresh(cluster)
    assert cluster.ha_status_json["dns_propagation_pending"] is True
    assert cluster.ha_status_json["dns_propagation_target_ip"] == "10.10.0.22"


def test_ha_check_clears_dns_pending_after_target_resolves(client):
    cluster = _cluster("mysql-dns-effective")
    cluster.ha_status_json = {
        "dns_propagation_pending": True,
        "dns_propagation_target_ip": "10.10.0.22",
        "dns_propagation_started_at": "2026-08-30T01:02:03",
    }
    db.session.commit()

    with patch("app.api.routes.clusters.list_host_addresses", return_value=["10.10.0.22"]):
        response = client.post(f"/api/v1/clusters/{cluster.id}/ha/check", headers=_admin_headers(client))

    assert response.status_code == 200
    status = response.get_json()["data"]
    assert status["actual_resolved_addresses"] == ["10.10.0.22"]
    assert status["dns_propagation_pending"] is False


def test_ha_config_defaults_to_aliyun_and_does_not_require_script(client):
    response = client.post(
        "/api/v1/ha/configs",
        json={"name": "默认域名切换", "is_default": True},
        headers=_admin_headers(client),
    )

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["domain_switch_method"] == "aliyun"
    assert payload["script_path"] is None


def test_batch_switch_executes_each_selected_cluster(client):
    first = _cluster("mysql-batch-1")
    second = _cluster("mysql-batch-2")
    headers = _admin_headers(client)

    def fake_execute(**kwargs):
        return {"cluster_id": kwargs["cluster_id"], "new_master_instance_id": kwargs["target_instance_id"]}

    with patch("app.api.routes.clusters._execute_ha_switch", side_effect=fake_execute) as execute:
        response = client.post(
            "/api/v1/clusters/mysql/ha/batch-switch",
            json={
                "items": [
                    {"cluster_id": first.id, "switch_type": "normal", "target_instance_id": 101},
                    {"cluster_id": second.id, "switch_type": "normal", "target_instance_id": 202},
                ]
            },
            headers=headers,
        )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["success_count"] == 2
    assert data["failed_count"] == 0
    assert execute.call_count == 2
