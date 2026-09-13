import secrets
import os
import time
import threading
from collections import deque
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db_connection

SESSION_COOKIE_NAME = "cooked_session"
SESSION_DURATION_DAYS = 14
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_MINUTES = 5

ADMIN_USERNAMES = [
    u.strip().lower() for u in os.environ.get("ADMIN_USERNAMES", "headchef,admin,sawyer").split(",") if u.strip()
]

# Thread-safe in-memory session token cache (30s TTL)
_SESSION_CACHE = {} # token -> (user_dict, expire_timestamp)
_SESSION_CACHE_LOCK = threading.Lock()
_SESSION_CACHE_TTL = 30.0

# Thread-safe in-memory IP rate limiter (zero disk write locks)
_FAILED_LOGINS = {} # ip -> deque of timestamp floats
_LOGIN_LOCK = threading.Lock()

import re

COMMON_WEAK_PASSWORDS = {
    "password", "password123", "12345678", "123456789", "qwerty123",
    "letmein123", "admin123", "welcome123", "chefpass", "chefpass1",
    "ilovecooking", "cooking123", "secret123", "changeme", "pass1234"
}

def validate_password_strength(password: str) -> tuple[bool, str | None]:
    """
    Enforce strong password policy:
    - At least 8 characters
    - At least 1 uppercase letter (A-Z)
    - At least 1 lowercase letter (a-z)
    - At least 1 numeric digit (0-9)
    - At least 1 special character (!@#$%^&*()_+-=[]{}|;':",.<>/?)
    - Not in common weak passwords blacklist
    """
    if not password or len(password) < 8:
        return (False, "Password must be at least 8 characters long.")

    if not re.search(r'[A-Z]', password):
        return (False, "Password must contain at least one uppercase letter (A-Z).")

    if not re.search(r'[a-z]', password):
        return (False, "Password must contain at least one lowercase letter (a-z).")

    if not re.search(r'[0-9]', password):
        return (False, "Password must contain at least one number (0-9).")

    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?~`]', password):
        return (False, "Password must contain at least one special symbol (!@#$%^&*).")

    if password.lower() in COMMON_WEAK_PASSWORDS:
        return (False, "Password is too common or easily guessable. Please choose a more unique password.")

    return (True, None)

def hash_password(password: str) -> str:
    """Hash password using Werkzeug PBKDF2-HMAC-SHA256 with calibrated work factor for concurrency."""
    return generate_password_hash(password, method="pbkdf2:sha256:50000", salt_length=16)

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against stored hash."""
    return check_password_hash(password_hash, password)

def generate_session_token() -> str:
    """Generate 256-bit cryptographically secure pseudorandom token."""
    return secrets.token_urlsafe(32)

def is_ip_rate_limited(ip_address: str, conn=None) -> bool:
    """Check if the IP has exceeded 5 failed login attempts in the last 5 minutes (in-memory)."""
    now = time.time()
    cutoff = now - (LOCKOUT_WINDOW_MINUTES * 60)
    with _LOGIN_LOCK:
        attempts = _FAILED_LOGINS.get(ip_address)
        if not attempts:
            return False
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        return len(attempts) >= MAX_FAILED_ATTEMPTS

def record_login_attempt(ip_address: str, username: str, success: bool, conn=None):
    """Log a login attempt in-memory for instant, non-blocking rate limiting."""
    now = time.time()
    with _LOGIN_LOCK:
        if success:
            _FAILED_LOGINS.pop(ip_address, None)
        else:
            if ip_address not in _FAILED_LOGINS:
                _FAILED_LOGINS[ip_address] = deque()
            _FAILED_LOGINS[ip_address].append(now)

def create_user_session(user_id: int) -> str:
    """Generate and store a session token in the database."""
    token = generate_session_token()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=SESSION_DURATION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessions (user_id, token, expires_at)
        VALUES (?, ?, ?);
    """, (user_id, token, expires_at))
    conn.commit()
    conn.close()
    return token

def get_authenticated_user():
    """Retrieve current authenticated user with sub-millisecond memory caching."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token and "Authorization" in request.headers:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    if not token:
        return None

    # 1. Check in-memory session cache first
    now_ts = time.time()
    with _SESSION_CACHE_LOCK:
        cached = _SESSION_CACHE.get(token)
        if cached and cached[1] > now_ts:
            return dict(cached[0])

    # 2. Query DB on cache miss
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.username, u.email, u.display_name, u.avatar_url, u.bio,
               u.is_active, u.is_admin, u.created_at, s.token, s.expires_at
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ? AND s.expires_at > ? AND u.is_active = 1
    """, (token, now_str))
    user = cursor.fetchone()
    conn.close()

    if user:
        user_dict = dict(user)
        with _SESSION_CACHE_LOCK:
            _SESSION_CACHE[token] = (user_dict, now_ts + _SESSION_CACHE_TTL)
        return user_dict

    return None

def invalidate_user_sessions(user_id: int = None, token: str = None):
    """Invalidate session cache for a user or specific token."""
    with _SESSION_CACHE_LOCK:
        if token:
            _SESSION_CACHE.pop(token, None)
        if user_id:
            tokens_to_remove = [k for k, v in _SESSION_CACHE.items() if v[0].get("id") == user_id]
            for k in tokens_to_remove:
                _SESSION_CACHE.pop(k, None)

def reset_auth_caches():
    """Clear in-memory session and rate-limit caches (useful for testing and maintenance)."""
    with _SESSION_CACHE_LOCK:
        _SESSION_CACHE.clear()
    with _LOGIN_LOCK:
        _FAILED_LOGINS.clear()

def delete_user_session(token: str):
    """Remove session token from database and cache on logout."""
    if not token:
        return
    invalidate_user_sessions(token=token)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE token = ?;", (token,))
    conn.commit()
    conn.close()

def require_auth(f):
    """Decorator to protect authenticated routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_authenticated_user()
        if not user:
            return jsonify({"error": "Unauthorized", "message": "Authentication required"}), 401
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to restrict access strictly to administrators."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_authenticated_user()
        if not user:
            return jsonify({"error": "Unauthorized", "message": "Authentication required"}), 401
        if user.get("is_admin") != 1:
            return jsonify({"error": "Forbidden", "message": "Administrator privileges required"}), 403
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function

