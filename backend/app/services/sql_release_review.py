import threading

from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.models.sql_release import SqlRelease
from app.services.audit import log_audit
from app.services.sql_release_service import review_release, split_sql_statements
from app.services.sql_release_config import is_sql_release_ai_review_enabled


def run_sql_release_review(app, release_id: int):
    with app.app_context():
        release = SqlRelease.query.get(release_id)
        if not release or release.status != "reviewing":
            return

        statements = split_sql_statements(release.sql_text)
        instance = DatabaseInstance.query.get(release.instance_id)

        if not is_sql_release_ai_review_enabled():
            reason = "全局 AI 预审已关闭，工单未执行 AI 审核"
            release.review_json = [{
                **dict(item),
                "passed": None,
                "status": "skipped",
                "reason": reason,
                "suggestion": "",
            } for item in (release.review_json or [])]
            release.ai_passed = False
            release.ai_summary = reason
            release.status = "pending"
            db.session.commit()
            log_audit(
                user_id=release.applicant_id,
                action="sql_release.review.skip",
                target_type="sql_release",
                target_id=str(release.id),
                detail={"status": release.status, "reason": "global_config_disabled"},
            )
            return

        def persist_review_item(review, total):
            current = list(release.review_json or [])
            line = int(review.get("line") or 0)
            updated = []
            for item in current:
                item = dict(item)
                if item.get("line") == line:
                    item = {**item, **review}
                elif item.get("line") == line + 1 and item.get("status") == "pending":
                    item["status"] = "reviewing"
                    item["reason"] = "AI 正在分析该语句"
                updated.append(item)
            release.review_json = updated
            release.ai_summary = f"AI 初审进行中（{line}/{total}）"
            db.session.commit()

        try:
            if not instance or not instance.enabled:
                raise ValueError("release instance is unavailable")

            initial = list(release.review_json or [])
            if not initial:
                initial = [{
                    "line": index, "sql": statement, "passed": None,
                    "risk_level": None, "reason": "等待 AI 初审",
                    "suggestion": "", "status": "pending",
                } for index, statement in enumerate(statements, start=1)]
            if initial:
                initial[0] = {**initial[0], "status": "reviewing", "reason": "AI 正在分析该语句"}
                release.review_json = initial
                release.ai_summary = f"AI 初审进行中（0/{len(statements)}）"
                db.session.commit()
            reviews, summary = review_release(
                instance,
                release.database_name,
                statements,
                release.db_type or instance.db_type or "mysql",
                persist_review_item,
            )
            if len(reviews) != len(statements):
                raise ValueError("AI 初审未返回全部语句的审核结果")
            completed_lines = {
                item.get("line") for item in (release.review_json or [])
                if item.get("status") == "completed"
            }
            for review in reviews:
                if review.get("line") not in completed_lines:
                    persist_review_item({**review, "status": "completed"}, len(statements))
            release.review_json = [{**item, "status": "completed"} for item in reviews]
            release.ai_summary = summary
            release.ai_passed = bool(reviews) and all(item.get("passed") is True for item in reviews)
            release.status = "pending" if release.ai_passed else "review_rejected"
            detail = {"status": release.status, "ai_passed": release.ai_passed}
        except Exception as exc:
            release.ai_passed = False
            release.status = "review_failed"
            release.ai_summary = f"AI 初审失败：{exc}"
            failed_items = []
            failure_recorded = False
            for item in (release.review_json or []):
                item = dict(item)
                if item.get("status") == "reviewing" and not failure_recorded:
                    item.update(status="failed", reason=str(exc), passed=False)
                    failure_recorded = True
                elif item.get("status") == "pending":
                    item.update(status="skipped", reason="审核任务异常，未继续处理")
                failed_items.append(item)
            release.review_json = failed_items
            detail = {"status": release.status, "ai_passed": False, "error": str(exc)}

        db.session.commit()
        log_audit(
            user_id=release.applicant_id,
            action="sql_release.review",
            target_type="sql_release",
            target_id=str(release.id),
            detail=detail,
        )


def dispatch_sql_release_review(app, release_id: int):
    worker = threading.Thread(
        target=run_sql_release_review,
        args=(app, release_id),
        name=f"sql-release-review-{release_id}",
        daemon=True,
    )
    worker.start()
    return worker
