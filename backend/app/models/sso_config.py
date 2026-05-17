from app.extensions import db
from app.models.base import TimestampMixin


class SsoConfig(db.Model, TimestampMixin):
    """Single-row SSO configuration stored in database. id=1 is always used."""

    __tablename__ = "sso_configs"

    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    provider_name = db.Column(db.String(64), nullable=False, default="SSO")
    client_id = db.Column(db.String(255), nullable=False, default="")
    client_secret = db.Column(db.String(255), nullable=False, default="")
    authorize_url = db.Column(db.String(512), nullable=False, default="")
    token_url = db.Column(db.String(512), nullable=False, default="")
    userinfo_url = db.Column(db.String(512), nullable=False, default="")
    scope = db.Column(db.String(255), nullable=False, default="openid profile email")
    redirect_uri = db.Column(db.String(512), nullable=False, default="")
    username_field = db.Column(db.String(64), nullable=False, default="preferred_username")
    email_field = db.Column(db.String(64), nullable=False, default="email")
    display_name_field = db.Column(db.String(64), nullable=False, default="")

    def to_dict(self, reveal_secret: bool = False):
        secret_view = self.client_secret or ""
        if not reveal_secret and secret_view:
            secret_view = "******"
        return {
            "id": self.id,
            "enabled": bool(self.enabled),
            "provider_name": self.provider_name or "SSO",
            "client_id": self.client_id or "",
            "client_secret": secret_view,
            "authorize_url": self.authorize_url or "",
            "token_url": self.token_url or "",
            "userinfo_url": self.userinfo_url or "",
            "scope": self.scope or "openid profile email",
            "redirect_uri": self.redirect_uri or "",
            "username_field": self.username_field or "preferred_username",
            "email_field": self.email_field or "email",
            "display_name_field": self.display_name_field or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def get_current(cls):
        """Return the singleton SSO config row (creating it if missing)."""
        row = cls.query.order_by(cls.id.asc()).first()
        if row is None:
            row = cls()
            db.session.add(row)
            db.session.commit()
        return row
