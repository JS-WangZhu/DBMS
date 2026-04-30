from flask import jsonify


def ok_response(data=None, message="ok", code=200):
    """成功响应"""
    response = {
        "ok": True,
        "message": message,
    }
    if data is not None:
        response["data"] = data

    return jsonify(response), code


def error_response(message, code=400, data=None):
    """错误响应"""
    response = {
        "ok": False,
        "message": message,
    }
    if data is not None:
        response["data"] = data

    return jsonify(response), code
