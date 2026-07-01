from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import telegram_miniapp_auth as tg_auth  # noqa: E402
from telegram_miniapp_auth import (  # noqa: E402
    TelegramMiniAppAuthError,
    build_session_response,
    router,
    verify_telegram_init_data,
)


FAKE_BOT_TOKEN = "123456" + ":" + "TEST_TOKEN"
FAKE_SESSION_SECRET = "test-session-secret"
OWNER_USER_ID = 424242
SIGNED_OWNER_INIT_DATA = (
    "auth_date=1782864000&query_id=AAEAAAE&"
    "user=%7B%22id%22%3A424242%2C%22first_name%22%3A%22Owner%22%2C%22username%22%3A%22owner_test%22%7D&"
    "hash=6ca082c98679682cbf541c3c67f9c5315ae7fb4b00f149d1f0e6dbfd3c8e25d7"
)
BAD_SIGNATURE_INIT_DATA = (
    "auth_date=1782864000&query_id=AAEAAAE&"
    "user=%7B%22id%22%3A424242%2C%22first_name%22%3A%22Owner%22%2C%22username%22%3A%22owner_test%22%7D&"
    "hash=6ca082c98679682cbf541c3c67f9c5315ae7fb4b00f149d1f0e6dbfd3c8e25d0"
)


def decode_session_payload(token: str) -> dict[str, object]:
    _, payload, _ = token.split(".")
    padded = payload + "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))


def test_verifies_fixed_signed_telegram_init_data_fixture():
    verified = verify_telegram_init_data(
        SIGNED_OWNER_INIT_DATA,
        bot_token=FAKE_BOT_TOKEN,
        now=1782864020,
    )

    assert verified.telegram_user_id == OWNER_USER_ID
    assert verified.auth_date == 1782864000
    assert verified.subject.startswith("telegram:user:")
    assert str(OWNER_USER_ID) not in verified.subject


def test_builds_short_lived_owner_session_without_echoing_sensitive_input():
    response = build_session_response(
        SIGNED_OWNER_INIT_DATA,
        bot_token=FAKE_BOT_TOKEN,
        owner_ids={OWNER_USER_ID},
        session_secret=FAKE_SESSION_SECRET,
        now=1782864020,
        session_ttl_seconds=120,
    )

    body = response.model_dump()
    assert body["ok"] is True
    assert body["role"] == "owner"
    assert body["expires_at"] == 1782864140
    assert body["ttl_seconds"] == 120
    assert "init_data" not in body
    assert "initData" not in body
    assert "telegram_user_id" not in body
    assert str(OWNER_USER_ID) not in json.dumps(body)

    session_payload = decode_session_payload(body["session_token"])
    assert session_payload["role"] == "owner"
    assert session_payload["sub"] == body["subject"]
    assert session_payload["exp"] == 1782864140


def test_rejects_unauthorized_valid_telegram_user():
    try:
        build_session_response(
            SIGNED_OWNER_INIT_DATA,
            bot_token=FAKE_BOT_TOKEN,
            owner_ids={999999},
            session_secret=FAKE_SESSION_SECRET,
            now=1782864020,
        )
    except TelegramMiniAppAuthError as exc:
        assert exc.code == "unauthorized"
    else:
        raise AssertionError("expected unauthorized")


def test_rejects_malformed_init_data():
    try:
        verify_telegram_init_data("auth_date=1782864000&hash=not-hex", bot_token=FAKE_BOT_TOKEN, now=1782864020)
    except TelegramMiniAppAuthError as exc:
        assert exc.code == "malformed_init_data"
    else:
        raise AssertionError("expected malformed_init_data")


def test_rejects_stale_init_data():
    try:
        verify_telegram_init_data(
            SIGNED_OWNER_INIT_DATA,
            bot_token=FAKE_BOT_TOKEN,
            now=1782865000,
            max_age_seconds=300,
        )
    except TelegramMiniAppAuthError as exc:
        assert exc.code == "stale_init_data"
    else:
        raise AssertionError("expected stale_init_data")


def test_rejects_bad_signature():
    try:
        verify_telegram_init_data(BAD_SIGNATURE_INIT_DATA, bot_token=FAKE_BOT_TOKEN, now=1782864020)
    except TelegramMiniAppAuthError as exc:
        assert exc.code == "bad_signature"
    else:
        raise AssertionError("expected bad_signature")


def test_route_issues_redaction_safe_session(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_BOT_TOKEN)
    monkeypatch.setenv("TELEGRAM_OWNER_IDS", str(OWNER_USER_ID))
    monkeypatch.setenv("KOLIBRI_SESSION_SECRET", FAKE_SESSION_SECRET)
    monkeypatch.setattr(tg_auth.time, "time", lambda: 1782864020)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/telegram-miniapp/session",
        json={"init_data": SIGNED_OWNER_INIT_DATA},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == "owner"
    assert "session_token" in payload
    assert SIGNED_OWNER_INIT_DATA not in response.text
    assert FAKE_BOT_TOKEN not in response.text
    assert str(OWNER_USER_ID) not in response.text


def test_route_returns_redacted_unauthorized_error(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_BOT_TOKEN)
    monkeypatch.setenv("TELEGRAM_OWNER_IDS", "999999")
    monkeypatch.setenv("KOLIBRI_SESSION_SECRET", FAKE_SESSION_SECRET)
    monkeypatch.setattr(tg_auth.time, "time", lambda: 1782864020)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/telegram-miniapp/session",
        json={"init_data": SIGNED_OWNER_INIT_DATA},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "unauthorized"}
    assert SIGNED_OWNER_INIT_DATA not in response.text
    assert FAKE_BOT_TOKEN not in response.text
    assert str(OWNER_USER_ID) not in response.text
