from flask import Blueprint, g, request

from app.api.routes.common import active_user_required, admin_required
from app.extensions import db
from app.models.feedback import Feedback, FeedbackReply
from app.services.audit import log_audit
from app.utils.response import error_response, ok_response


bp = Blueprint("feedback", __name__, url_prefix="/feedback")


def _positive_int(value, default, maximum=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(parsed, 1)
    return min(parsed, maximum) if maximum else parsed


def _visible_feedback_or_none(feedback_id):
    item = Feedback.query.get(feedback_id)
    if not item:
        return None
    if g.current_user.role != "admin" and item.user_id != g.current_user.id:
        return None
    return item


@bp.get("")
@active_user_required
def list_feedback():
    page = _positive_int(request.args.get("page"), 1)
    page_size = _positive_int(request.args.get("page_size"), 20, 100)
    status = (request.args.get("status") or "").strip()

    query = Feedback.query
    if g.current_user.role != "admin":
        query = query.filter_by(user_id=g.current_user.id)
    if status in {"pending", "replied"}:
        query = query.filter_by(status=status)

    total = query.count()
    items = (
        query.order_by(Feedback.updated_at.desc(), Feedback.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ok_response(
        data={
            "items": [item.to_dict() for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@bp.get("/summary")
@active_user_required
def feedback_summary():
    if g.current_user.role == "admin":
        unread = Feedback.query.filter_by(admin_unread=True).count()
        pending = Feedback.query.filter_by(status="pending").count()
    else:
        unread = Feedback.query.filter_by(user_id=g.current_user.id, user_unread=True).count()
        pending = Feedback.query.filter_by(user_id=g.current_user.id, status="pending").count()
    return ok_response(data={"unread": unread, "pending": pending})


@bp.post("")
@active_user_required
def create_feedback():
    payload = request.get_json(silent=True) or {}
    subject = str(payload.get("subject") or "").strip()
    content = str(payload.get("content") or "").strip()
    if not subject:
        return error_response("请输入反馈主题", code=400)
    if len(subject) > 120:
        return error_response("反馈主题不能超过120个字符", code=400)
    if not content:
        return error_response("请输入反馈内容", code=400)
    if len(content) > 4000:
        return error_response("反馈内容不能超过4000个字符", code=400)

    display_name = (g.current_user.display_name or "").strip()
    item = Feedback(
        user_id=g.current_user.id,
        username=display_name or g.current_user.username,
        subject=subject,
        content=content,
        status="pending",
        admin_unread=True,
        user_unread=False,
    )
    db.session.add(item)
    db.session.commit()
    log_audit(
        user_id=g.current_user.id,
        action="feedback.create",
        target_type="feedback",
        target_id=str(item.id),
        detail={"subject": subject},
    )
    return ok_response(data=item.to_dict(), message="反馈已提交", code=201)


@bp.patch("/<int:feedback_id>/read")
@active_user_required
def mark_feedback_read(feedback_id):
    item = _visible_feedback_or_none(feedback_id)
    if not item:
        return error_response("反馈不存在", code=404)
    if g.current_user.role == "admin":
        item.admin_unread = False
    else:
        item.user_unread = False
    db.session.commit()
    return ok_response(data=item.to_dict())


@bp.post("/<int:feedback_id>/replies")
@admin_required
def reply_feedback(feedback_id):
    item = Feedback.query.get(feedback_id)
    if not item:
        return error_response("反馈不存在", code=404)
    payload = request.get_json(silent=True) or {}
    content = str(payload.get("content") or "").strip()
    if not content:
        return error_response("请输入回复内容", code=400)
    if len(content) > 4000:
        return error_response("回复内容不能超过4000个字符", code=400)

    admin_name = (g.current_user.display_name or "").strip() or g.current_user.username
    db.session.add(
        FeedbackReply(
            feedback_id=item.id,
            admin_id=g.current_user.id,
            admin_name=admin_name,
            content=content,
        )
    )
    item.status = "replied"
    item.admin_unread = False
    item.user_unread = True
    db.session.commit()
    log_audit(
        user_id=g.current_user.id,
        action="feedback.reply",
        target_type="feedback",
        target_id=str(item.id),
        detail={"feedback_user_id": item.user_id},
    )
    return ok_response(data=item.to_dict(), message="回复已发送", code=201)
