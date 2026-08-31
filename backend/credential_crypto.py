from __future__ import annotations

import base64
import hashlib
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


ENCRYPTED_PREFIX = "enc:v1"
AAD = b"workflow-automation:user-credential:v1"


class CredentialDecryptionError(RuntimeError):
    pass


def _key_candidates() -> list[tuple[str, bytes]]:
    configured = [
        os.getenv("CREDENTIAL_ENCRYPTION_KEY", ""),
        os.getenv("JWT_SECRET", ""),
    ]
    keys: list[tuple[str, bytes]] = []
    for secret in configured:
        if not secret:
            continue
        key = hashlib.sha256(secret.encode("utf-8")).digest()
        key_id = hashlib.sha256(key).hexdigest()[:12]
        if all(existing_id != key_id for existing_id, _ in keys):
            keys.append((key_id, key))
    if not keys:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY or JWT_SECRET must be configured")
    return keys


def is_encrypted(value: str | None) -> bool:
    return bool(value and value.startswith(f"{ENCRYPTED_PREFIX}:"))


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return value
    key_id, key = _key_candidates()[0]
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, value.encode("utf-8"), AAD)
    payload = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
    return f"{ENCRYPTED_PREFIX}:{key_id}:{payload}"


def decrypt_secret(value: str | None) -> str | None:
    if not value or not is_encrypted(value):
        return value

    try:
        prefix, version, key_id, payload = value.split(":", 3)
        if f"{prefix}:{version}" != ENCRYPTED_PREFIX:
            raise ValueError("unsupported credential version")
        packed = base64.urlsafe_b64decode(payload.encode("ascii"))
        nonce, ciphertext = packed[:12], packed[12:]
        if len(nonce) != 12 or not ciphertext:
            raise ValueError("invalid encrypted credential")
    except (ValueError, TypeError) as exc:
        raise CredentialDecryptionError("Stored credential has an invalid format") from exc

    for candidate_id, key in _key_candidates():
        if candidate_id != key_id:
            continue
        try:
            return AESGCM(key).decrypt(nonce, ciphertext, AAD).decode("utf-8")
        except Exception as exc:
            raise CredentialDecryptionError("Stored credential could not be decrypted") from exc
    raise CredentialDecryptionError("The encryption key for this credential is unavailable")


def migrate_plaintext_credentials(db) -> int:
    """Encrypt legacy plaintext rows in place. Safe to call on every startup."""
    import models

    changed = 0
    for row in db.query(models.UserApiKey).all():
        if row.api_key and not is_encrypted(row.api_key):
            row.api_key = encrypt_secret(row.api_key)
            changed += 1
        if row.refresh_token and not is_encrypted(row.refresh_token):
            row.refresh_token = encrypt_secret(row.refresh_token)
            changed += 1
    if changed:
        db.commit()
    return changed
