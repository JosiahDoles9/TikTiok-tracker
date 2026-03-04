from __future__ import annotations

import base64
import hashlib
import os


def _key_bytes() -> bytes:
    key = os.getenv("TOKEN_ENCRYPTION_KEY", "dev-only-change-me")
    return hashlib.sha256(key.encode("utf-8")).digest()


def encrypt_token(value: str) -> str:
    raw = value.encode("utf-8")
    key = _key_bytes()
    out = bytes([raw[i] ^ key[i % len(key)] for i in range(len(raw))])
    return base64.urlsafe_b64encode(out).decode("utf-8")


def decrypt_token(value: str) -> str:
    raw = base64.urlsafe_b64decode(value.encode("utf-8"))
    key = _key_bytes()
    out = bytes([raw[i] ^ key[i % len(key)] for i in range(len(raw))])
    return out.decode("utf-8")
