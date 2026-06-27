from app.extensions import db
from app.models.backup_agent import AgentInspectionStatus, BackupAgent


class _HealthyResponse:
    status_code = 200

    @staticmethod
    def json():
        return {"data": {"status": "healthy", "version": "test"}}


def test_agent_status_is_collected_and_exposed(app, monkeypatch):
    from app.services import inspection_service

    with app.app_context():
        agent = BackupAgent(name="agent-a", url="http://agent-a:5001", enabled=True)
        db.session.add(agent)
        db.session.commit()

        monkeypatch.setattr(inspection_service.requests, "get", lambda *args, **kwargs: _HealthyResponse())
        result = inspection_service.run_inspection_cycle(trigger="test", force=True)

        assert result["ok"] is True
        assert result["data"]["inspected_agents"] == 1
        assert result["data"]["abnormal_agents"] == 0

        saved = AgentInspectionStatus.query.filter_by(agent_id=agent.id).one()
        assert saved.status == "normal"
        overview = inspection_service.inspection_overview(db_type="agent")
        assert overview["total"] == 1
        assert overview["items"][0]["asset_type"] == "agent"
        assert overview["items"][0]["inspection_status"] == "normal"
        assert overview["items"][0]["cluster_name"] == "http://agent-a:5001"


def test_agent_timeout_is_reported_as_abnormal(app, monkeypatch):
    from app.services import inspection_service

    with app.app_context():
        agent = BackupAgent(name="agent-b", url="http://agent-b:5001", enabled=True)
        db.session.add(agent)
        db.session.commit()

        def timeout(*args, **kwargs):
            raise inspection_service.requests.exceptions.Timeout()

        monkeypatch.setattr(inspection_service.requests, "get", timeout)
        result = inspection_service.run_inspection_cycle(trigger="test", force=True)

        assert result["data"]["abnormal_agents"] == 1
        overview = inspection_service.inspection_overview(db_type="agent", status="abnormal")
        assert overview["total"] == 1
        assert overview["items"][0]["issues"][0]["issue_key"] == "agent_health"
