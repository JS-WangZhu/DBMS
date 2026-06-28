import threading

from flask import Blueprint, current_app, request

from app.api.routes.common import get_current_user, require_menu_permission
from app.extensions import db, scheduler
from app.models.task_management import ScheduledTask, ScheduledTaskRun
from app.services.audit import log_audit
from app.services.task_management import VALID_TASK_TYPES, run_scheduled_task
from app.tasks.scheduler import _trigger_from_expr, sync_scheduled_task_jobs
from app.utils.response import error_response, ok_response

bp = Blueprint("task_management", __name__, url_prefix="/task-management")


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _validate_cron_expr(expr: str):
    if not (expr or "").strip():
        return False
    try:
        _trigger_from_expr(expr)
        return True
    except Exception:
        return False


def _apply_task_fields(task: ScheduledTask, payload: dict, is_create=False):
    if is_create:
        missing = [key for key in ("name", "task_type", "cron_expr") if payload.get(key) in (None, "")]
        if missing:
            return f"missing fields: {', '.join(missing)}"
    if "task_type" in payload:
        task_type = str(payload.get("task_type") or "").strip().lower()
        if task_type not in VALID_TASK_TYPES:
            return "invalid task_type"
        task.task_type = task_type
    if "cron_expr" in payload or is_create:
        cron_expr = str(payload.get("cron_expr") or task.cron_expr or "").strip()
        if not _validate_cron_expr(cron_expr):
            return "invalid cron_expr, expected 5-field crontab like '0 2 * * *' or 6-field crontab like '0 0 2 * * *'"
        task.cron_expr = cron_expr
    if "name" in payload:
        task.name = str(payload.get("name") or "").strip()[:128]
    if "description" in payload:
        task.description = str(payload.get("description") or "").strip()[:255] or None
    if "enabled" in payload:
        task.enabled = _to_bool(payload.get("enabled"), default=True)
    if "timeout_seconds" in payload:
        task.timeout_seconds = max(1, min(_safe_int(payload.get("timeout_seconds"), 300), 86400))
    if "max_retries" in payload:
        task.max_retries = max(0, min(_safe_int(payload.get("max_retries"), 0), 10))
    if "content_json" in payload:
        content = payload.get("content_json") or {}
        if not isinstance(content, dict):
            return "content_json must be object"
        task.content_json = content
    return None


def _sync_jobs():
    try:
        sync_scheduled_task_jobs(scheduler=scheduler, app=current_app)
    except Exception:
        current_app.logger.exception("sync scheduled task jobs failed")


@bp.get("/schedules")
@require_menu_permission("task_schedule")
def list_schedules():
    query = ScheduledTask.query
    task_type = (request.args.get("task_type") or "").strip()
    if task_type:
        query = query.filter(ScheduledTask.task_type == task_type)
    rows = query.order_by(ScheduledTask.id.desc()).all()
    return ok_response(data=[item.to_dict() for item in rows])


@bp.post("/schedules")
@require_menu_permission("task_schedule")
def create_schedule():
    payload = request.get_json(silent=True) or {}
    task = ScheduledTask(task_type="shell", cron_expr="0 * * * *", enabled=True, timeout_seconds=300, max_retries=0)
    err = _apply_task_fields(task, payload, is_create=True)
    if err:
        return error_response(err, code=400)
    db.session.add(task)
    db.session.commit()
    _sync_jobs()
    user = get_current_user()
    log_audit(user_id=user.id if user else None, action="task.schedule.create", target_type="scheduled_task", target_id=str(task.id), detail=payload)
    return ok_response(data=task.to_dict(), code=201)


@bp.patch("/schedules/<int:task_id>")
@require_menu_permission("task_schedule")
def update_schedule(task_id: int):
    task = ScheduledTask.query.get(task_id)
    if not task:
        return error_response("task not found", code=404)
    payload = request.get_json(silent=True) or {}
    err = _apply_task_fields(task, payload)
    if err:
        return error_response(err, code=400)
    db.session.commit()
    _sync_jobs()
    user = get_current_user()
    log_audit(user_id=user.id if user else None, action="task.schedule.update", target_type="scheduled_task", target_id=str(task.id), detail=payload)
    return ok_response(data=task.to_dict())


@bp.delete("/schedules/<int:task_id>")
@require_menu_permission("task_schedule")
def delete_schedule(task_id: int):
    task = ScheduledTask.query.get(task_id)
    if not task:
        return error_response("task not found", code=404)
    ScheduledTaskRun.query.filter_by(task_id=task.id).delete()
    db.session.delete(task)
    db.session.commit()
    _sync_jobs()
    return ok_response(message="deleted")


@bp.post("/schedules/<int:task_id>/run")
@require_menu_permission("task_schedule")
def run_schedule_now(task_id: int):
    task = ScheduledTask.query.get(task_id)
    if not task:
        return error_response("task not found", code=404)
    app = current_app._get_current_object()
    threading.Thread(target=_run_async, args=(app, task.id, "manual", None), daemon=True).start()
    return ok_response(message="task started")


def _run_async(app, task_id, trigger_type, retry_of_id):
    with app.app_context():
        run_scheduled_task(task_id=task_id, trigger_type=trigger_type, retry_of_id=retry_of_id)


@bp.get("/results")
@require_menu_permission("task_results")
def list_results():
    query = ScheduledTaskRun.query.join(ScheduledTask)
    task_id = _safe_int(request.args.get("task_id"))
    task_name = (request.args.get("task_name") or "").strip()
    status = (request.args.get("status") or "").strip()
    task_type = (request.args.get("task_type") or "").strip()
    if task_id:
        query = query.filter(ScheduledTaskRun.task_id == task_id)
    if task_name:
        query = query.filter(ScheduledTask.name.ilike(f"%{task_name}%"))
    if status:
        query = query.filter(ScheduledTaskRun.status == status)
    if task_type:
        query = query.filter(ScheduledTask.task_type == task_type)
    page = max(1, _safe_int(request.args.get("page"), 1))
    page_size = max(1, min(_safe_int(request.args.get('page_size'), 10), 100))
    total = query.count()
    rows = (
        query.order_by(ScheduledTaskRun.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ok_response(data={"items": [item.to_dict() for item in rows], "total": total, "page": page, "page_size": page_size})


@bp.get("/results/<int:run_id>")
@require_menu_permission("task_results")
def get_result(run_id: int):
    run = ScheduledTaskRun.query.get(run_id)
    if not run:
        return error_response("result not found", code=404)
    return ok_response(data=run.to_dict())


@bp.delete("/results")
@require_menu_permission("task_results")
def delete_results():
    payload = request.get_json(silent=True) or {}
    ids = []
    for item in payload.get("ids") or []:
        value = _safe_int(item)
        if value > 0:
            ids.append(value)
    ids = sorted(set(ids))
    if not ids:
        return error_response("ids is required", code=400)
    deleted = ScheduledTaskRun.query.filter(ScheduledTaskRun.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return ok_response(data={"deleted": deleted})


@bp.post("/results/<int:run_id>/retry")
@require_menu_permission("task_results")
def retry_result(run_id: int):
    run = ScheduledTaskRun.query.get(run_id)
    if not run:
        return error_response("result not found", code=404)
    if run.status != "failed":
        return error_response("only failed result can be retried", code=400)
    app = current_app._get_current_object()
    threading.Thread(target=_run_async, args=(app, run.task_id, "retry", run.id), daemon=True).start()
    return ok_response(message="retry started")
