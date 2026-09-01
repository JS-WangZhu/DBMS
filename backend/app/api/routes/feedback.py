import os
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, g, request, send_file

from app.api.routes.common import active_user_required, admin_required
from app.extensions import db
from app.models.feedback import Feedback, FeedbackAttachment, FeedbackReply
from app.services.audit import log_audit
from app.utils.response import error_response, ok_response


bp = Blueprint("feedback", __name__, url_prefix="/feedback")

IMAGE_SIGNATURES = (
    ("image/png", ".png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    ("image/jpeg", ".jpg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ("image/gif", ".gif", lambda data: data.startswith((b"GIF87a", b"GIF89a"))),
    (
        "image/webp",
        ".webp",
        lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
    ),
)


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


def _feedback_image_root():
    configured = Path(current_app.config["FEEDBACK_IMAGE_DIR"])
    if not configured.is_absolute():
        configured = Path(current_app.root_path).parent / configured
    return configured.resolve()


def _detect_image(data):
    for mime_type, extension, matches in IMAGE_SIGNATURES:
        if matches(data):
            return mime_type, extension
    return None


def _read_uploaded_images():
    uploads = [upload for upload in request.files.getlist("images") if upload and upload.filename]
    max_count = current_app.config["FEEDBACK_IMAGE_MAX_COUNT"]
    max_bytes = current_app.config["FEEDBACK_IMAGE_MAX_BYTES"]
    if len(uploads) > max_count:
        return None, error_response(f"每次最多上传{max_count}张图片", code=400)

    images = []
    for upload in uploads:
        raw = upload.stream.read(max_bytes + 1)
        if len(raw) > max_bytes:
            return None, error_response(f"单张图片不能超过{max_bytes // 1024 // 1024}MB", code=413)
        detected = _detect_image(raw)
        if not detected:
            return None, error_response("仅支持 PNG、JPG、GIF、WEBP 图片", code=400)
        mime_type, extension = detected
        original_name = os.path.basename(upload.filename).strip()[:255] or f"image{extension}"
        images.append(
            {
                "raw": raw,
                "mime_type": mime_type,
                "extension": extension,
                "original_name": original_name,
            }
        )
    return images, None


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
    payload = request.form if request.mimetype == "multipart/form-data" else (request.get_json(silent=True) or {})
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

    images, upload_error = _read_uploaded_images()
    if upload_error:
        return upload_error

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
    written_paths = []
    try:
        db.session.flush()
        if images:
            item_dir = _feedback_image_root() / str(item.id)
            item_dir.mkdir(parents=True, exist_ok=True)
            for image in images:
                stored_name = f"{uuid4().hex}{image['extension']}"
                file_path = item_dir / stored_name
                file_path.write_bytes(image["raw"])
                written_paths.append(file_path)
                db.session.add(
                    FeedbackAttachment(
                        feedback_id=item.id,
                        original_name=image["original_name"],
                        stored_name=stored_name,
                        mime_type=image["mime_type"],
                        size_bytes=len(image["raw"]),
                    )
                )
        db.session.commit()
    except Exception:
        db.session.rollback()
        for file_path in written_paths:
            try:
                file_path.unlink(missing_ok=True)
            except OSError:
                current_app.logger.warning("Failed to remove feedback image after rollback: %s", file_path)
        raise
    log_audit(
        user_id=g.current_user.id,
        action="feedback.create",
        target_type="feedback",
        target_id=str(item.id),
        detail={"subject": subject},
    )
    return ok_response(data=item.to_dict(), message="反馈已提交", code=201)


@bp.get("/<int:feedback_id>/attachments/<int:attachment_id>")
@active_user_required
def get_feedback_attachment(feedback_id, attachment_id):
    item = _visible_feedback_or_none(feedback_id)
    if not item:
        return error_response("反馈不存在", code=404)
    attachment = FeedbackAttachment.query.filter_by(id=attachment_id, feedback_id=item.id).first()
    if not attachment:
        return error_response("图片不存在", code=404)

    image_root = _feedback_image_root()
    file_path = (image_root / str(item.id) / attachment.stored_name).resolve()
    try:
        file_path.relative_to(image_root)
    except ValueError:
        return error_response("图片不存在", code=404)
    if not file_path.is_file():
        return error_response("图片不存在", code=404)
    return send_file(
        file_path,
        mimetype=attachment.mime_type,
        download_name=attachment.original_name,
        conditional=True,
        max_age=3600,
    )


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
