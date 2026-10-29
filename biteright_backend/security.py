"""
Authentication & request-safety helpers for the BiteRight API.

- Password hashing (scrypt via Werkzeug) with transparent upgrade of the
  legacy ``sha256(password + salt):salt`` hashes stored by older versions.
- Signed, expiring session tokens (itsdangerous, ships with Flask).
- ``require_user`` route guard that checks the caller owns the user_id
  they are reading or writing.
- A tiny in-memory rate limiter (the app runs a single gunicorn worker).

Environment variables
---------------------
SECRET_KEY          Required in production. Signs session tokens. If unset a
                    random key is generated, which logs every user out when
                    the server restarts.
AUTH_REQUIRED       "true" (default) rejects user-scoped requests without a
                    valid token. Set to "false" only for local debugging.
TOKEN_MAX_AGE_DAYS  Session lifetime in days (default 30).
"""

import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

MIN_PASSWORD_LENGTH = 6
TOKEN_MAX_AGE_SECONDS = int(os.environ.get('TOKEN_MAX_AGE_DAYS', '30')) * 24 * 3600
AUTH_REQUIRED = os.environ.get('AUTH_REQUIRED', 'true').strip().lower() not in ('0', 'false', 'no', 'off')


def _load_secret_key():
    key = os.environ.get('SECRET_KEY', '').strip()
    if key:
        return key
    print(
        "WARNING: SECRET_KEY is not set. Using a random key; all sessions "
        "will be invalidated when the server restarts.",
        flush=True,
    )
    return secrets.token_hex(32)


_serializer = URLSafeTimedSerializer(_load_secret_key(), salt='biteright-session')


# ============= PASSWORDS =============

def hash_password(password):
    """Hash a password with Werkzeug's default (scrypt) algorithm."""
    return generate_password_hash(password)


def verify_password(password, stored_hash):
    """Check a password against a stored hash.

    Returns ``(is_valid, needs_rehash)``. ``needs_rehash`` is True when the
    stored hash uses the legacy SHA-256 format and should be upgraded.
    """
    if not stored_hash or not password:
        return False, False

    if stored_hash.startswith(('scrypt:', 'pbkdf2:')):
        return check_password_hash(stored_hash, password), False

    # Legacy format: "<sha256 hex>:<salt>"
    if ':' in stored_hash:
        hashed, salt = stored_hash.split(':', 1)
        candidate = hashlib.sha256((password + salt).encode()).hexdigest()
        is_valid = hmac.compare_digest(hashed, candidate)
        return is_valid, is_valid

    return False, False


# ============= SESSION TOKENS =============

def issue_token(user_id):
    return _serializer.dumps({'uid': str(user_id)})


def read_token(token):
    """Return the user id stored in a valid token, or None."""
    if not token:
        return None
    try:
        data = _serializer.loads(token, max_age=TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    if isinstance(data, dict) and data.get('uid'):
        return str(data['uid'])
    return None


def token_user_id():
    """User id from the request's ``Authorization: Bearer <token>`` header."""
    header = request.headers.get('Authorization', '')
    if header[:7].lower() == 'bearer ':
        return read_token(header[7:].strip())
    return None


def _requested_user_id(kwargs):
    if kwargs.get('user_id'):
        return str(kwargs['user_id'])
    body = request.get_json(silent=True)
    if isinstance(body, dict) and body.get('user_id'):
        return str(body['user_id'])
    if request.args.get('user_id'):
        return str(request.args['user_id'])
    return None


def require_user(view):
    """Require a valid session token that matches the targeted user.

    The target user comes from the ``<user_id>`` URL segment, a ``user_id``
    JSON field, or a ``user_id`` query parameter. The resolved id is stored
    in ``flask.g.user_id``.
    """
    @wraps(view)
    def wrapper(*args, **kwargs):
        requested = _requested_user_id(kwargs)
        authenticated = token_user_id()

        if authenticated is None:
            if AUTH_REQUIRED:
                return jsonify({'error': 'Your session has expired. Please sign in again.',
                                'code': 'auth_required'}), 401
            g.user_id = requested
            return view(*args, **kwargs)

        if requested and requested != authenticated:
            return jsonify({'error': 'You do not have access to this account.',
                            'code': 'forbidden'}), 403

        g.user_id = authenticated
        return view(*args, **kwargs)

    return wrapper


# ============= RATE LIMITING =============

class RateLimiter:
    """Sliding-window limiter keyed by an arbitrary string."""

    def __init__(self, max_attempts, window_seconds):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key):
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window_seconds:
                hits.popleft()
            if len(hits) >= self.max_attempts:
                return False
            hits.append(now)
            return True

    def reset(self, key):
        with self._lock:
            self._hits.pop(key, None)


def client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'
