import json

from app.extensions import db
from app.models.backup_agent import BackupAgent
from app.models.db_asset import DatabaseInstance


def test_mcp_status_includes_whitelisted_instance_and_physical_machine_metadata(app, monkeypatch):
    from app.services import mcp_status

    monkeypatch.setattr(mcp_status, "latest_snapshots_by_instance_ids", lambda *_args: {})

    with app.app_context():
        agent = BackupAgent(name="probe-a", url="http://agent.example", api_key="agent-secret")
        db.session.add(agent)
        db.session.flush()
        instance = DatabaseInstance(
            name="mysql-a",
            db_type="mysql",
            host_input="db.example.com",
            resolved_ip="10.20.1.8",
            port=3306,
            access_mode="agent",
            probe_agent_id=agent.id,
            extra_json={
                "domain": "db.example.com",
                "physical_address": "192.0.2.10",
                "physical_discovery_mode": "auto",
                "physical_discovery_source": "vc-a",
                "physical_discovered_at": "2026-07-08T01:02:03",
                "internal_secret": "must-not-leak",
            },
        )
        db.session.add(instance)
        db.session.commit()

        row = mcp_status.build_mcp_instance_status()["instances"][0]

        assert row["host_domain"] == "db.example.com"
        assert row["access_mode"] == "agent"
        assert row["probe_agent"] == {"id": agent.id, "name": "probe-a"}
        assert row["created_at"] == instance.created_at.isoformat()
        assert row["physical_machine"] == {
            "address": "192.0.2.10",
            "discovery_mode": "auto",
            "discovery_source": "vc-a",
            "discovered_at": "2026-07-08T01:02:03",
        }
        assert "extra_json" not in row
        assert "must-not-leak" not in json.dumps(row)
        assert "agent-secret" not in json.dumps(row)


def test_mcp_status_has_stable_physical_machine_defaults(app, monkeypatch):
    from app.services import mcp_status

    monkeypatch.setattr(mcp_status, "latest_snapshots_by_instance_ids", lambda *_args: {})

    with app.app_context():
        instance = DatabaseInstance(
            name="redis-a",
            db_type="redis",
            host_input="10.20.1.9",
            port=6379,
            extra_json={"physical_discovery_mode": "unexpected"},
        )
        db.session.add(instance)
        db.session.commit()

        row = mcp_status.build_mcp_instance_status()["instances"][0]

        assert row["host_domain"] is None
        assert row["probe_agent"] is None
        assert row["physical_machine"] == {
            "address": None,
            "discovery_mode": "auto",
            "discovery_source": None,
            "discovered_at": None,
        }
