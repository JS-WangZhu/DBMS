import base64
import hashlib

from cryptography.fernet import Fernet
from flask import current_app


def _derive_fernet_key(secret_seed: str) -> bytes:
    digest = hashlib.sha256(secret_seed.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _build_fernet() -> Fernet:
    configured = current_app.config.get("FERNET_KEY")
    key = configured.encode("utf-8") if configured else _derive_fernet_key(current_app.config["SECRET_KEY"])
    return Fernet(key)


def encrypt_secret(raw_value: str) -> str:
    if raw_value is None:
        return ""
    f = _build_fernet()
    return f.encrypt(raw_value.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted_value: str) -> str:
    if not encrypted_value:
        return ""
    f = _build_fernet()
    return f.decrypt(encrypted_value.encode("utf-8")).decode("utf-8")
