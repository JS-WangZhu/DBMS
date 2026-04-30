from flask import Blueprint

from app.utils.response import ok_response

bp = Blueprint("health", __name__, url_prefix="/health")


@bp.get("")
def health():
    return ok_response(data={"status": "ok"})
