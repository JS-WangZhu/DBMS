from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.user import User


def _admin_headers(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_delete_user_unbinds_audit_logs(client):
    headers = _admin_headers(client)

    target = User(username="to-delete", role="user", status="active", auth_source="local")
    target.set_password("target123")
    db.session.add(target)
    db.session.commit()

    audit = AuditLog(user_id=target.id, action="demo.action", target_type="user", target_id=str(target.id), detail_json={})
    db.session.add(audit)
    db.session.commit()

    resp = client.delete(f"/api/v1/users/{target.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    assert User.query.get(target.id) is None
    kept_audit = AuditLog.query.get(audit.id)
    assert kept_audit is not None
    assert kept_audit.user_id is None

