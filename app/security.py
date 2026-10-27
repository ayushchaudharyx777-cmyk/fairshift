import hashlib
import os
import secrets
from typing import Optional
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request, HTTPException, status
from app.config import get_settings


def hash_pin(pin: str, salt: Optional[str] = None) -> str:
    """Hash a numeric PIN using PBKDF2 with SHA-256."""
    if not salt:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        pin.encode('utf-8'),
        salt.encode('utf-8'),
        100_000
    )
    return f"{salt}${key.hex()}"


def verify_pin(plain_pin: str, hashed_str: str) -> bool:
    """Verify plain PIN against stored salt$hash."""
    try:
        salt, expected_hex = hashed_str.split('$', 1)
        actual_key = hashlib.pbkdf2_hmac(
            'sha256',
            plain_pin.encode('utf-8'),
            salt.encode('utf-8'),
            100_000
        )
        return secrets.compare_digest(actual_key.hex(), expected_hex)
    except Exception:
        return False


def get_serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.SESSION_SECRET, salt="fairshift-session-salt")


def create_worker_session_token(worker_id: str) -> str:
    serializer = get_serializer()
    return serializer.dumps({"worker_id": worker_id, "type": "worker"})


def verify_worker_session_token(token: str, max_age: int = 86400 * 7) -> Optional[str]:
    serializer = get_serializer()
    try:
        data = serializer.loads(token, max_age=max_age)
        if data.get("type") == "worker":
            return data.get("worker_id")
        return None
    except (BadSignature, SignatureExpired):
        return None


def create_admin_session_token() -> str:
    serializer = get_serializer()
    return serializer.dumps({"type": "admin", "admin": True})


def verify_admin_session_token(token: str, max_age: int = 86400 * 2) -> bool:
    serializer = get_serializer()
    try:
        data = serializer.loads(token, max_age=max_age)
        return data.get("type") == "admin" and data.get("admin") is True
    except (BadSignature, SignatureExpired):
        return False


# Dependencies for FastAPI routes

def get_current_worker_id(request: Request) -> str:
    cookie_token = request.cookies.get("worker_session")
    auth_header = request.headers.get("Authorization")
    token = cookie_token
    if not token and auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Worker authentication required"
        )
    worker_id = verify_worker_session_token(token)
    if not worker_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please log in again."
        )
    return worker_id


def require_admin_auth(request: Request) -> bool:
    cookie_token = request.cookies.get("admin_session")
    auth_header = request.headers.get("Authorization")
    token = cookie_token
    if not token and auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]

    if not token or not verify_admin_session_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required"
        )
    return True
