import threading

from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.models.sql_release import SqlRelease
from app.services.audit import log_audit
from app.services.sql_release_service import review_release, split_sql_statements


def run_sql_release_review(app, release_id: int):
    with app.app_context():
        release = SqlRelease.query.get(release_id)
        if not release or release.status != "reviewing":
            return

        statements = split_sql_statements(release.sql_text)
        instance = DatabaseInstance.query.get(release.instance_id)
        try:
            if not instance or not instance.enabled:
                raise ValueError("release instance is unavailable")
            reviews, summary = review_release(
                instance,
                release.database_name,
                statements,
                release.db_type or instance.db_type or "mysql",
            )
            if len(reviews) != len(statements):
                raise ValueError("AI 初审未返回全部语句的审核结果")
            release.review_json = reviews
            release.ai_summary = summary
            release.ai_passed = bool(reviews) and all(item.get("passed") is True for item in reviews)
            release.status = "pending" if release.ai_passed else "review_rejected"
            detail = {"status": release.status, "ai_passed": release.ai_passed}
        except Exception as exc:
            release.ai_passed = False
            release.status = "review_failed"
            release.ai_summary = f"AI 初审失败：{exc}"
            release.review_json = []
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
