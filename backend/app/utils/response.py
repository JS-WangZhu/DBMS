from flask import jsonify


def ok_response(data=None, message="ok", code=200):
    return jsonify({"ok": True, "message": message, "data": data}), code


def error_response(message, code=400, data=None):
    return jsonify({"ok": False, "message": message, "data": data}), code
