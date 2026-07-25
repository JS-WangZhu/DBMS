def test_login_errors_are_returned_in_chinese(client):
    missing = client.post("/api/v1/auth/login", json={"username": "admin", "password": ""})
    assert missing.status_code == 400
    assert missing.get_json()["message"] == "请输入用户名和密码"

    invalid = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong-password"})
    assert invalid.status_code == 401
    assert invalid.get_json()["message"] == "用户名或密码错误"
