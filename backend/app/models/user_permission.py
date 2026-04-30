from app.extensions import db
from app.models.base import TimestampMixin


class UserMenuPermission(db.Model, TimestampMixin):
    __tablename__ = "user_menu_permissions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    menu_key = db.Column(db.String(64), nullable=False)


class UserClusterPermission(db.Model, TimestampMixin):
    __tablename__ = "user_cluster_permissions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    cluster_id = db.Column(db.Integer, db.ForeignKey("db_clusters.id"), nullable=False)
    can_query = db.Column(db.Boolean, nullable=False, default=False)
    can_change = db.Column(db.Boolean, nullable=False, default=False)


class ApiKey(db.Model, TimestampMixin):
    __tablename__ = "api_keys"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    token = db.Column(db.String(128), nullable=False, unique=True)
    status = db.Column(db.String(16), nullable=False, default="active")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "token": self.token,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RoleGroup(db.Model, TimestampMixin):
    __tablename__ = "role_groups"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RoleGroupMenuPermission(db.Model, TimestampMixin):
    __tablename__ = "role_group_menu_permissions"

    id = db.Column(db.Integer, primary_key=True)
    role_group_id = db.Column(db.Integer, db.ForeignKey("role_groups.id"), nullable=False)
    menu_key = db.Column(db.String(64), nullable=False)


class RoleGroupClusterPermission(db.Model, TimestampMixin):
    __tablename__ = "role_group_cluster_permissions"

    id = db.Column(db.Integer, primary_key=True)
    role_group_id = db.Column(db.Integer, db.ForeignKey("role_groups.id"), nullable=False)
    cluster_id = db.Column(db.Integer, db.ForeignKey("db_clusters.id"), nullable=False)
    can_query = db.Column(db.Boolean, nullable=False, default=False)
    can_change = db.Column(db.Boolean, nullable=False, default=False)


class UserRoleGroup(db.Model, TimestampMixin):
    __tablename__ = "user_role_groups"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role_group_id = db.Column(db.Integer, db.ForeignKey("role_groups.id"), nullable=False)
