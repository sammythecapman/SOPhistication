"""
Document security controls:
  1. Encryption at rest   — Fernet (AES-128-CBC + HMAC-SHA256) via the cryptography package
  2. Signed download tokens — HMAC-SHA256, time-limited, single-purpose
"""

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


# ──────────────────────────────────────────────
# Fernet key — derived from SESSION_SECRET
# ──────────────────────────────────────────────

def _get_fernet() -> Fernet:
    """Derive a stable Fernet key from SESSION_SECRET."""
    secret = os.environ.get("SESSION_SECRET", "")
    if not secret:
        raise RuntimeError(
            "SESSION_SECRET environment variable is required for file encryption."
        )
    key_bytes = hashlib.sha256(f"sba-file-encryption:{secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


# ──────────────────────────────────────────────
# File encryption / decryption
# ──────────────────────────────────────────────

def encrypt_file(src_path: str, dest_path: str) -> None:
    """Read src_path, encrypt it, write ciphertext to dest_path."""
    fernet = _get_fernet()
    data = Path(src_path).read_bytes()
    Path(dest_path).write_bytes(fernet.encrypt(data))


def decrypt_file(enc_path: str) -> bytes:
    """Read an encrypted file and return the decrypted bytes."""
    fernet = _get_fernet()
    try:
        return fernet.decrypt(Path(enc_path).read_bytes())
    except InvalidToken:
        raise ValueError(f"Could not decrypt {enc_path}: invalid key or corrupted data.")


# ──────────────────────────────────────────────
# Signed download tokens
# ──────────────────────────────────────────────

def _token_secret() -> bytes:
    secret = os.environ.get("SESSION_SECRET", "")
    return hashlib.sha256(f"sba-download-token:{secret}".encode()).digest()


def generate_download_token(
    extraction_id: int,
    filename: str,
    ttl_seconds: int = 3600,
) -> str:
    """
    Return a URL-safe signed token valid for ttl_seconds (default 1 hour).
    Format: <base64url(payload)>.<base64url(hmac)>
    """
    payload = json.dumps(
        {
            "eid": extraction_id,
            "fn": filename,
            "iat": int(time.time()),
            "exp": int(time.time()) + ttl_seconds,
        },
        separators=(",", ":"),
    ).encode()

    p64 = base64.urlsafe_b64encode(payload).rstrip(b"=")
    sig = hmac.new(_token_secret(), p64, hashlib.sha256).digest()
    s64 = base64.urlsafe_b64encode(sig).rstrip(b"=")
    return f"{p64.decode()}.{s64.decode()}"


def verify_download_token(token: str) -> dict:
    """
    Validate a signed download token.
    Returns the payload dict on success.
    Raises ValueError on invalid or expired tokens.
    """
    try:
        p64_str, s64_str = token.split(".", 1)
    except ValueError:
        raise ValueError("Malformed token")

    p64 = p64_str.encode()
    s64 = s64_str.encode()

    expected = hmac.new(_token_secret(), p64, hashlib.sha256).digest()
    padding = (-len(s64)) % 4
    try:
        actual = base64.urlsafe_b64decode(s64 + b"=" * padding)
    except Exception:
        raise ValueError("Token decode error")

    if not hmac.compare_digest(expected, actual):
        raise ValueError("Invalid token signature")

    padding = (-len(p64)) % 4
    try:
        payload = json.loads(base64.urlsafe_b64decode(p64 + b"=" * padding))
    except Exception:
        raise ValueError("Payload decode error")

    if time.time() > payload.get("exp", 0):
        raise ValueError("Token has expired")

    return payload
