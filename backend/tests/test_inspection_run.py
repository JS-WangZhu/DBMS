def _admin_headers(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_run_inspection_reports_busy_as_warning(client, monkeypatch):
    from app.api.routes import inspection

    headers = _admin_headers(client)

    def fake_run_inspection_cycle(trigger="manual", force=True):
        return {"ok": False, "message": "inspection is already running", "code": 409}

    monkeypatch.setattr(inspection, "run_inspection_cycle", fake_run_inspection_cycle)

    resp = client.post("/api/v1/inspection/run", headers=headers)

    assert resp.status_code == 202
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["message"] == "巡检正在执行中，请稍后查看结果"
    assert payload["data"]["already_running"] is True


def test_inspection_error_masks_password_head_and_tail():
    from app.services.inspection_service import mask_sensitive_text

    password = "SecretPass123"
    masked = mask_sensitive_text(
        "mysql connect failed: access denied for mysql://ops:SecretPass123@10.0.0.8:3306",
        secrets=[password],
    )

    assert password not in masked
    assert "Se*********23" in masked


def test_inspection_error_masks_url_encoded_password():
    from app.services.inspection_service import mask_sensitive_text

    password = "p@ss/word:123"
    masked = mask_sensitive_text(
        "mongo auth failed: mongodb://ops:p%40ss%2Fword%3A123@10.0.0.9/admin",
        secrets=[password],
    )

    assert "p%40ss%2Fword%3A123" not in masked
    assert "p@ss/word:123" not in masked
    assert "p@*********23" in masked
