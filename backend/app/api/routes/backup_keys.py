from flask import Blueprint, request

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

from app.api.routes.common import active_user_required
from app.extensions import db
from app.models.backup_key import BackupKey
from app.services.audit import log_audit
from app.utils.response import error_response, ok_response

bp = Blueprint("backup_keys", __name__, url_prefix="/backups/keys")


def _trim(value):
    return (value or "").strip()


def validate_key_pair(public_key: str, private_key: str = None) -> dict:
    if not public_key:
        return {"valid": False, "message": "公钥不能为空"}
    
    try:
        pub_key = load_pem_public_key(public_key.encode("utf-8"), backend=default_backend())
    except Exception as e:
        return {"valid": False, "message": f"公钥格式错误: {str(e)}"}
    
    if not private_key:
        return {"valid": True, "message": "未提供私钥，跳过配对验证"}
    
    try:
        priv_key = load_pem_private_key(private_key.encode("utf-8"), password=None, backend=default_backend())
    except Exception as e:
        return {"valid": False, "message": f"私钥格式错误: {str(e)}"}
    
    if pub_key.key_size != priv_key.key_size:
        return {"valid": False, "message": f"公钥和私钥位数不匹配: {pub_key.key_size} vs {priv_key.key_size}"}
    
    test_data = b"DBMS_KEYPAIR_VALIDATION_TEST"
    
    try:
        encrypted = pub_key.encrypt(
            test_data,
            padding.PKCS1v15()
        )
        decrypted = priv_key.decrypt(
            encrypted,
            padding.PKCS1v15()
        )
        if decrypted != test_data:
            return {"valid": False, "message": "密钥对验证失败: 解密数据不匹配"}
    except Exception as e:
        return {"valid": False, "message": f"密钥对验证失败: {str(e)}"}
    
    return {"valid": True, "message": "密钥对验证通过", "key_size": pub_key.key_size}


@bp.get("")
@active_user_required
def list_backup_keys():
    keys = BackupKey.query.order_by(BackupKey.id.desc()).all()
    return ok_response(data=[item.to_dict() for item in keys])


@bp.post("")
@active_user_required
def create_backup_key():
    payload = request.get_json(silent=True) or {}
    name = _trim(payload.get("name"))
    public_key = _trim(payload.get("public_key"))
    private_key = _trim(payload.get("private_key"))
    description = _trim(payload.get("description"))

    if not name:
        return error_response("name is required", code=400)
    if not public_key:
        return error_response("public_key is required", code=400)
    if BackupKey.query.filter_by(name=name).first():
        return error_response("name already exists", code=400)

    if private_key:
        validation = validate_key_pair(public_key, private_key)
        if not validation["valid"]:
            return error_response(validation["message"], code=400)

    key = BackupKey(name=name, public_key=public_key, private_key=private_key or None, description=description or None)
    db.session.add(key)
    db.session.commit()
    log_audit(user_id=None, action="backup.key.create", target_type="backup_key", target_id=str(key.id), detail=payload)
    return ok_response(data=key.to_dict(), code=201)


@bp.get("/<int:key_id>")
@active_user_required
def get_backup_key(key_id: int):
    key = BackupKey.query.get(key_id)
    if not key:
        return error_response("backup key not found", code=404)
    return ok_response(data=key.to_dict())


@bp.get("/<int:key_id>/private-key")
@active_user_required
def get_backup_private_key(key_id: int):
    key = BackupKey.query.get(key_id)
    if not key:
        return error_response("backup key not found", code=404)
    if not key.private_key:
        return error_response("private key not found", code=404)
    log_audit(user_id=None, action="backup.key.view_private", target_type="backup_key", target_id=str(key.id))
    return ok_response(data={"id": key.id, "name": key.name, "private_key": key.private_key})


@bp.patch("/<int:key_id>")
@active_user_required
def update_backup_key(key_id: int):
    key = BackupKey.query.get(key_id)
    if not key:
        return error_response("backup key not found", code=404)

    payload = request.get_json(silent=True) or {}
    name = _trim(payload.get("name")) if "name" in payload else None
    public_key = _trim(payload.get("public_key")) if "public_key" in payload else None
    private_key = _trim(payload.get("private_key")) if "private_key" in payload else None
    description = _trim(payload.get("description")) if "description" in payload else None

    if name:
        existed = BackupKey.query.filter_by(name=name).first()
        if existed and existed.id != key.id:
            return error_response("name already exists", code=400)
        key.name = name
    if public_key:
        new_private_key = private_key if private_key is not None else key.private_key
        if new_private_key:
            validation = validate_key_pair(public_key, new_private_key)
            if not validation["valid"]:
                return error_response(validation["message"], code=400)
        key.public_key = public_key
    if private_key is not None:
        if private_key and public_key:
            validation = validate_key_pair(public_key, private_key)
            if not validation["valid"]:
                return error_response(validation["message"], code=400)
        key.private_key = private_key or None
    if "description" in payload:
        key.description = description or None

    db.session.commit()
    log_audit(user_id=None, action="backup.key.update", target_type="backup_key", target_id=str(key.id), detail=payload)
    return ok_response(data=key.to_dict())


@bp.delete("/<int:key_id>")
@active_user_required
def delete_backup_key(key_id: int):
    key = BackupKey.query.get(key_id)
    if not key:
        return error_response("backup key not found", code=404)
    db.session.delete(key)
    db.session.commit()
    log_audit(user_id=None, action="backup.key.delete", target_type="backup_key", target_id=str(key.id))
    return ok_response(message="deleted")
