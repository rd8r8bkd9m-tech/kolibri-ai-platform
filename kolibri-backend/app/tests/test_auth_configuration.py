import jwt
import pytest
from fastapi import HTTPException
from starlette.responses import Response

import app.auth as auth
from app.main import _set_auth_cookie


def test_production_rejects_development_jwt_secret(monkeypatch):
    monkeypatch.setenv("KOLIBRI_RELEASE_ID", "release-test")
    monkeypatch.setattr(auth, "SECRET_KEY", auth.DEVELOPMENT_SECRET)
    with pytest.raises(RuntimeError, match="jwt_secret_not_configured"):
        auth.validate_auth_configuration()


def test_production_accepts_long_configured_jwt_secret(monkeypatch):
    monkeypatch.setenv("KOLIBRI_RELEASE_ID", "release-test")
    monkeypatch.setattr(auth, "SECRET_KEY", "s" * 48)
    auth.validate_auth_configuration()


def test_operator_tokens_require_issuer_and_audience(monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", "s" * 48)
    valid = auth.create_access_token({"sub": "owner-1"})
    assert auth.decode_token(valid)["sub"] == "owner-1"

    invalid = jwt.encode({"sub": "owner-1"}, auth.SECRET_KEY, algorithm=auth.ALGORITHM)
    with pytest.raises(HTTPException):
        auth.decode_token(invalid)


def test_browser_auth_cookie_is_http_only_strict_and_secure_in_production(monkeypatch):
    monkeypatch.setenv("KOLIBRI_PUBLIC_BASE_URL", "https://kolibriai.ru")
    response = Response()
    _set_auth_cookie(response, "signed-token")

    cookie = response.headers["set-cookie"]
    assert "kolibri_auth=signed-token" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Secure" in cookie
    assert "Path=/" in cookie
