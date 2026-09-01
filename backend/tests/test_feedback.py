from io import BytesIO

from flask import g
from sqlalchemy import BigInteger

from app.extensions import db
from app.models.feedback import Feedback, FeedbackAttachment, FeedbackReply
from app.models.user import User


def _login(client, username, password="password123"):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def _create_user(app, username):
    with app.app_context():
        user = User(username=username, role="user", status="active", auth_source="local")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()


def test_feedback_user_foreign_keys_match_mysql_bigint_user_id():
    assert isinstance(Feedback.__table__.c.user_id.type, BigInteger)
    assert isinstance(FeedbackReply.__table__.c.admin_id.type, BigInteger)


def test_feedback_image_upload_is_stored_locally_and_scoped(app, client, tmp_path):
    app.config["FEEDBACK_IMAGE_DIR"] = str(tmp_path / "feedback-images")
    _create_user(app, "feedback-image-user")
    _create_user(app, "feedback-other-user")
    owner = _login(client, "feedback-image-user")
    other = _login(client, "feedback-other-user")

    png = b"\x89PNG\r\n\x1a\n" + b"test-image-content"
    created = client.post(
        "/api/v1/feedback",
        data={
            "subject": "截图反馈",
            "content": "问题截图如下。",
            "images": (BytesIO(png), "clipboard.png", "image/png"),
        },
        headers=owner,
        content_type="multipart/form-data",
    )
    assert created.status_code == 201
    payload = created.get_json()["data"]
    assert len(payload["attachments"]) == 1
    attachment = payload["attachments"][0]
    assert attachment["mime_type"] == "image/png"
    assert attachment["original_name"] == "clipboard.png"

    with app.app_context():
        stored = FeedbackAttachment.query.get(attachment["id"])
        stored_path = tmp_path / "feedback-images" / str(payload["id"]) / stored.stored_name
        assert stored_path.read_bytes() == png

    g.pop("current_user", None)
    image_response = client.get(attachment["url"], headers=owner)
    assert image_response.status_code == 200
    assert image_response.data == png
    assert image_response.mimetype == "image/png"

    g.pop("current_user", None)
    assert client.get(attachment["url"], headers=other).status_code == 404


def test_feedback_image_upload_rejects_non_image(app, client):
    _create_user(app, "feedback-invalid-image-user")
    headers = _login(client, "feedback-invalid-image-user")
    response = client.post(
        "/api/v1/feedback",
        data={
            "subject": "无效附件",
            "content": "不应接受文本文件。",
            "images": (BytesIO(b"plain text"), "fake.png", "image/png"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "PNG" in response.get_json()["message"]


def test_feedback_is_scoped_and_admin_can_reply(app, client):
    _create_user(app, "feedback-user-a")
    _create_user(app, "feedback-user-b")
    user_a = _login(client, "feedback-user-a")
    user_b = _login(client, "feedback-user-b")
    admin = _login(client, "admin", "admin123")

    created = client.post(
        "/api/v1/feedback",
        json={"subject": "查询页面异常", "content": "执行查询后结果区为空。"},
        headers=user_a,
    )
    assert created.status_code == 201
    feedback_id = created.get_json()["data"]["id"]

    own_list = client.get("/api/v1/feedback", headers=user_a).get_json()["data"]
    assert own_list["total"] == 1
    assert own_list["items"][0]["subject"] == "查询页面异常"
    g.pop("current_user", None)
    assert client.get("/api/v1/feedback", headers=user_b).get_json()["data"]["total"] == 0
    g.pop("current_user", None)
    assert client.patch(f"/api/v1/feedback/{feedback_id}/read", headers=user_b).status_code == 404

    g.pop("current_user", None)
    admin_summary = client.get("/api/v1/feedback/summary", headers=admin).get_json()["data"]
    assert admin_summary == {"pending": 1, "unread": 1}
    replied = client.post(
        f"/api/v1/feedback/{feedback_id}/replies",
        json={"content": "已收到，我们会检查该查询。"},
        headers=admin,
    )
    assert replied.status_code == 201
    assert replied.get_json()["data"]["status"] == "replied"
    assert replied.get_json()["data"]["replies"][0]["admin_name"] == "admin"

    g.pop("current_user", None)
    user_summary = client.get("/api/v1/feedback/summary", headers=user_a).get_json()["data"]
    assert user_summary == {"pending": 0, "unread": 1}
    read = client.patch(f"/api/v1/feedback/{feedback_id}/read", headers=user_a)
    assert read.status_code == 200
    assert client.get("/api/v1/feedback/summary", headers=user_a).get_json()["data"]["unread"] == 0


def test_feedback_validation_and_reply_requires_admin(app, client):
    _create_user(app, "feedback-user")
    headers = _login(client, "feedback-user")

    assert client.post("/api/v1/feedback", json={"subject": "", "content": "内容"}, headers=headers).status_code == 400
    created = client.post(
        "/api/v1/feedback",
        json={"subject": "建议", "content": "希望增加操作提示。"},
        headers=headers,
    )
    feedback_id = created.get_json()["data"]["id"]
    denied = client.post(
        f"/api/v1/feedback/{feedback_id}/replies",
        json={"content": "不能自行回复"},
        headers=headers,
    )
    assert denied.status_code == 403
