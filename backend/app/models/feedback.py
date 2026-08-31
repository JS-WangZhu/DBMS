from app.extensions import db
from app.models.base import TimestampMixin


class Feedback(db.Model, TimestampMixin):
    __tablename__ = "feedbacks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    username = db.Column(db.String(128), nullable=False)
    subject = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(16), nullable=False, default="pending", index=True)
    admin_unread = db.Column(db.Boolean, nullable=False, default=True)
    user_unread = db.Column(db.Boolean, nullable=False, default=False)

    replies = db.relationship(
        "FeedbackReply",
        backref="feedback",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="FeedbackReply.id.asc()",
    )

    def to_dict(self, include_replies=True):
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "subject": self.subject,
            "content": self.content,
            "status": self.status,
            "admin_unread": bool(self.admin_unread),
            "user_unread": bool(self.user_unread),
            "reply_count": len(self.replies),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_replies:
            data["replies"] = [reply.to_dict() for reply in self.replies]
        return data


class FeedbackReply(db.Model, TimestampMixin):
    __tablename__ = "feedback_replies"

    id = db.Column(db.Integer, primary_key=True)
    feedback_id = db.Column(
        db.Integer,
        db.ForeignKey("feedbacks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    admin_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    admin_name = db.Column(db.String(128), nullable=False)
    content = db.Column(db.Text, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "feedback_id": self.feedback_id,
            "admin_id": self.admin_id,
            "admin_name": self.admin_name,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
