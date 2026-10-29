"""Unit tests for security.py (password hashing, tokens, route guard, rate limiting).

Run with:
    cd biteright_backend
    python -m pytest tests/test_security.py -v
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SECRET_KEY', 'test-secret-key')

import pytest
from flask import Flask, g, jsonify

import security
from security import (
    RateLimiter,
    hash_password,
    issue_token,
    read_token,
    require_user,
    verify_password,
)


def _legacy_hash(password, salt='abc123'):
    return f"{hashlib.sha256((password + salt).encode()).hexdigest()}:{salt}"


class TestPasswords:
    def test_new_hash_round_trip(self):
        stored = hash_password('correct horse')
        assert stored.startswith('scrypt:')
        assert verify_password('correct horse', stored) == (True, False)
        assert verify_password('wrong', stored) == (False, False)

    def test_legacy_hash_is_accepted_and_flagged_for_upgrade(self):
        stored = _legacy_hash('secret1')
        assert verify_password('secret1', stored) == (True, True)
        assert verify_password('secret2', stored) == (False, False)

    @pytest.mark.parametrize('stored', ['', None, 'not-a-hash'])
    def test_missing_or_garbage_hash_is_rejected(self, stored):
        assert verify_password('anything', stored) == (False, False)


class TestTokens:
    def test_round_trip(self):
        assert read_token(issue_token('user-42')) == 'user-42'

    def test_tampered_token_is_rejected(self):
        token = issue_token('user-42')
        assert read_token(token[:-2] + ('AA' if token[-2:] != 'AA' else 'BB')) is None

    def test_empty_token_is_rejected(self):
        assert read_token('') is None
        assert read_token(None) is None


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(security, 'AUTH_REQUIRED', True)
    app = Flask(__name__)

    @app.route('/users/<user_id>/thing')
    @require_user
    def thing(user_id):
        return jsonify({'user': g.user_id})

    @app.route('/analyze', methods=['POST'])
    @require_user
    def analyze():
        return jsonify({'user': g.user_id})

    return app.test_client()


class TestRequireUser:
    def test_missing_token_is_401(self, client):
        response = client.get('/users/u1/thing')
        assert response.status_code == 401
        assert response.get_json()['code'] == 'auth_required'

    def test_matching_token_is_allowed(self, client):
        response = client.get('/users/u1/thing', headers={'Authorization': f'Bearer {issue_token("u1")}'})
        assert response.status_code == 200
        assert response.get_json() == {'user': 'u1'}

    def test_other_users_token_is_403(self, client):
        response = client.get('/users/u1/thing', headers={'Authorization': f'Bearer {issue_token("u2")}'})
        assert response.status_code == 403

    def test_user_id_in_json_body_is_checked(self, client):
        headers = {'Authorization': f'Bearer {issue_token("u1")}'}
        assert client.post('/analyze', json={'user_id': 'u2'}, headers=headers).status_code == 403
        ok = client.post('/analyze', json={'user_id': 'u1'}, headers=headers)
        assert ok.status_code == 200

    def test_token_user_is_used_when_no_target_given(self, client):
        response = client.post('/analyze', json={}, headers={'Authorization': f'Bearer {issue_token("u9")}'})
        assert response.get_json() == {'user': 'u9'}

    def test_auth_can_be_disabled_for_local_debugging(self, client, monkeypatch):
        monkeypatch.setattr(security, 'AUTH_REQUIRED', False)
        response = client.get('/users/u1/thing')
        assert response.status_code == 200
        assert response.get_json() == {'user': 'u1'}


class TestRateLimiter:
    def test_blocks_after_limit_and_resets(self):
        limiter = RateLimiter(max_attempts=3, window_seconds=60)
        assert [limiter.allow('k') for _ in range(4)] == [True, True, True, False]
        assert limiter.allow('other') is True
        limiter.reset('k')
        assert limiter.allow('k') is True
