import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.routers import telegram


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setenv("KOLIBRI_TELEGRAM_WEBHOOK_ENABLED", "true")
    monkeypatch.setenv("KOLIBRI_TELEGRAM_OWNER_APPROVED", "true")
    monkeypatch.setenv("KOLIBRI_TELEGRAM_ALLOWED_CHAT_IDS", "7001,-100123")
    monkeypatch.setenv("KOLIBRI_PUBLIC_BASE_URL", "https://kolibriai.ru")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test_secret_0123456789_abcdefghijk")
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _update(update_id: int, text: str, chat_id: int = 7001) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": 12},
            "text": text,
        },
    }


def _post(client: TestClient, body: dict):
    return client.post(
        "/api/v1/telegram/webhook",
        json=body,
        headers={"X-Telegram-Bot-Api-Secret-Token": "test_secret_0123456789_abcdefghijk"},
    )


def test_webhook_is_disabled_by_default_and_has_no_default_secret(monkeypatch):
    monkeypatch.delenv("KOLIBRI_TELEGRAM_WEBHOOK_ENABLED", raising=False)
    monkeypatch.delenv("KOLIBRI_TELEGRAM_OWNER_APPROVED", raising=False)
    monkeypatch.delenv("KOLIBRI_TELEGRAM_ALLOWED_CHAT_IDS", raising=False)
    monkeypatch.delenv("KOLIBRI_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    assert telegram._webhook_ready() is False
    readiness = telegram._readiness()
    assert readiness["status"] == "disabled"
    assert readiness["live_delivery_verified"] is False
    assert set(readiness["blockers"]) == {
        "webhook_disabled",
        "owner_approval_required",
        "protected_webhook_secret_required",
        "allowed_chat_ids_required",
        "public_https_base_url_required",
    }


def test_owner_approval_and_strong_secret_are_required(client, monkeypatch):
    monkeypatch.setenv("KOLIBRI_TELEGRAM_OWNER_APPROVED", "false")
    denied = _post(client, _update(10, "Привет"))
    assert denied.status_code == 503
    assert denied.json()["detail"]["code"] == "telegram_owner_approval_required"

    monkeypatch.setenv("KOLIBRI_TELEGRAM_OWNER_APPROVED", "true")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "kolibri-webhook-secret")
    weak_secret = client.post(
        "/api/v1/telegram/webhook",
        json=_update(11, "Привет"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "kolibri-webhook-secret"},
    )
    assert weak_secret.status_code == 503
    assert weak_secret.json()["detail"]["code"] == "telegram_webhook_secret_invalid"


def test_only_explicitly_allowed_chat_can_use_provider(client, monkeypatch):
    async def must_not_execute(request, *, idempotency_key=None):
        raise AssertionError("an unapproved chat reached the provider")

    monkeypatch.setattr(telegram, "execute_kolibri_response", must_not_execute)
    denied = _post(client, _update(12, "Привет", chat_id=9009))
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "telegram_chat_not_allowed"


def test_unified_response_persists_one_placeholder_and_deduplicates_update(client, monkeypatch):
    calls = []

    async def fake_execute(request, *, idempotency_key=None):
        calls.append((request, idempotency_key))
        return {
            "id": "resp_kolibri_telegram_1",
            "status": "completed",
            "content": "Готово через единый ответный контур.",
        }

    monkeypatch.setattr(telegram, "execute_kolibri_response", fake_execute)
    update = _update(101, "Напиши функцию сортировки на Rust")

    first = _post(client, update)
    repeated = _post(client, update)

    assert first.status_code == 200
    assert first.json() == {
        "method": "sendMessage",
        "chat_id": 7001,
        "text": "Готово через единый ответный контур.",
    }
    assert repeated.status_code == 200
    assert repeated.json() == {"ok": True, "duplicate": True}
    assert len(calls) == 1
    request, idempotency_key = calls[0]
    assert request.model == "kolibri"
    assert idempotency_key == "telegram:101:response"
    assert request.input == [{"role": "user", "content": "Напиши функцию сортировки на Rust"}]

    with next(app.dependency_overrides[get_db]()) as db:
        from app.models import ProjectDB, ProjectMessageDB

        project = db.query(ProjectDB).filter(ProjectDB.scope_id == "telegram:7001").one()
        messages = db.query(ProjectMessageDB).filter(
            ProjectMessageDB.project_id == project.id
        ).order_by(ProjectMessageDB.sequence).all()
        assert [(item.role, item.status) for item in messages] == [
            ("user", "completed"),
            ("assistant", "completed"),
        ]
        assert messages[1].content == "Готово через единый ответный контур."
        assert messages[1].attributes == {"response_id": "resp_kolibri_telegram_1"}


def test_history_is_reused_without_construction_only_prompt(client, monkeypatch):
    inputs = []

    async def fake_execute(request, *, idempotency_key=None):
        inputs.append(request.input)
        return {
            "id": f"resp_{len(inputs)}",
            "status": "completed",
            "content": f"Ответ {len(inputs)}",
        }

    monkeypatch.setattr(telegram, "execute_kolibri_response", fake_execute)
    assert _post(client, _update(201, "Как написать HTTP-сервер на Rust?")).status_code == 200
    assert _post(client, _update(202, "Добавь тесты и пример запуска")).status_code == 200

    assert inputs[1] == [
        {"role": "user", "content": "Как написать HTTP-сервер на Rust?"},
        {"role": "assistant", "content": "Ответ 1"},
        {"role": "user", "content": "Добавь тесты и пример запуска"},
    ]
    joined = " ".join(item["content"] for item in inputs[1]).lower()
    assert "помощник по строительству" not in joined
    assert "только смет" not in joined


def test_help_and_status_contain_no_fake_fleet_values(client):
    start_response = _post(client, _update(300, "/start"))
    help_response = _post(client, _update(301, "/help"))
    status_response = _post(client, _update(302, "/status"))
    assert all(
        capability in start_response.json()["text"].lower()
        for capability in ("вопрос", "изображение", "код", "автоматизация")
    )
    assert "помощник по строительству" not in help_response.json()["text"].lower()
    status_text = status_response.json()["text"]
    assert "21/21" not in status_text
    assert "healthy" not in status_text
    assert "подтвержд" in status_text.lower()

    # Local commands are subject to the same update ledger and cannot emit a
    # second Telegram message when Telegram retries the update.
    repeated = _post(client, _update(300, "/start"))
    assert repeated.json() == {"ok": True, "duplicate": True}


def test_provider_exception_finishes_placeholder_without_leaking_details(client, monkeypatch):
    async def broken_execute(request, *, idempotency_key=None):
        raise RuntimeError("SECRET local/path provider stderr")

    monkeypatch.setattr(telegram, "execute_kolibri_response", broken_execute)
    response = _post(client, _update(350, "Проверь код"))
    assert response.status_code == 200
    assert response.json()["method"] == "sendMessage"
    assert "SECRET" not in response.json()["text"]
    assert "stderr" not in response.json()["text"]

    repeated = _post(client, _update(350, "Проверь код"))
    assert repeated.json() == {"ok": True, "duplicate": True}


def test_verified_image_artifact_is_delivered_as_real_photo(client, monkeypatch):
    async def fake_execute(request, *, idempotency_key=None):
        return {
            "id": "resp_image_1",
            "status": "completed",
            "content": "Готово. Изображение проверено.",
            "artifact": {
                "id": "397d471e-3512-44ac-afec-89a3fdf78502",
                "type": "image",
                "mime_type": "image/png",
                "size_bytes": 42_000,
                "sha256": "a" * 64,
                "url": "/api/v1/artifacts/images/397d471e-3512-44ac-afec-89a3fdf78502",
            },
        }

    monkeypatch.setattr(telegram, "execute_kolibri_response", fake_execute)
    response = _post(client, _update(360, "Сгенерируй цветы"))
    assert response.status_code == 200
    assert response.json() == {
        "method": "sendPhoto",
        "chat_id": 7001,
        "photo": "https://kolibriai.ru/api/v1/artifacts/images/397d471e-3512-44ac-afec-89a3fdf78502",
        "caption": "Готово. Изображение проверено.",
    }

    with next(app.dependency_overrides[get_db]()) as db:
        from app.models import ProjectMessageDB

        assistant = db.query(ProjectMessageDB).filter(
            ProjectMessageDB.role == "assistant"
        ).one()
        assert assistant.status == "completed"
        assert assistant.attributes == {
            "response_id": "resp_image_1",
            "artifact": {
                "id": "397d471e-3512-44ac-afec-89a3fdf78502",
                "type": "image",
                "sha256": "a" * 64,
            },
        }


def test_unverified_artifact_metadata_never_claims_photo_delivery(client, monkeypatch):
    async def fake_execute(request, *, idempotency_key=None):
        return {
            "id": "resp_bad_image",
            "status": "completed",
            "content": "Артефакт сохранён.",
            "artifact": {
                "id": "not-an-id",
                "type": "image",
                "mime_type": "image/png",
                "size_bytes": 1,
                "sha256": "bad",
                "url": "https://example.invalid/image.png",
            },
        }

    monkeypatch.setattr(telegram, "execute_kolibri_response", fake_execute)
    response = _post(client, _update(361, "Сгенерируй цветы"))
    assert response.status_code == 200
    assert response.json()["method"] == "sendMessage"
    assert "photo" not in response.json()


def test_release_contract_has_no_watchdog_gomesh_or_legacy_sender(client):
    info = client.get("/api/v1/telegram/info")
    assert info.status_code == 200
    assert info.json()["receiver_ready"] is True
    assert info.json()["webhook_ready"] is False
    assert info.json()["execution_contract"] == "kolibri-responses"
    assert info.json()["history_contract"] == "project-history"
    assert info.json()["background_senders"] == {
        "watchdog": False,
        "gomesh": False,
        "legacy": False,
    }
    assert info.json()["background_sender_evidence"] == {
        "scope": "telegram-adapter-process",
        "fleet_runtime": "unknown",
    }
    assert info.json()["readiness"] == {
        "status": "configured_unverified",
        "receiver_ready": True,
        "owner_approved": True,
        "secret_valid": True,
        "allowed_chat_count": 2,
        "public_base_configured": True,
        "live_delivery_verified": False,
        "blockers": [],
    }
    source = open(telegram.__file__, encoding="utf-8").read().lower()
    assert "sendmessage" in source
    assert "send_photo" not in source
    assert "getupdates" not in source
    assert "httpx.post" not in source


def test_readiness_becomes_ready_only_after_live_delivery_evidence(client, monkeypatch):
    before = client.get("/api/v1/telegram/info")
    assert before.status_code == 200
    assert before.json()["webhook_ready"] is False
    assert before.json()["readiness"]["status"] == "configured_unverified"

    monkeypatch.setenv("KOLIBRI_TELEGRAM_LIVE_VERIFIED", "true")
    after = client.get("/api/v1/telegram/info")
    assert after.status_code == 200
    assert after.json()["webhook_ready"] is True
    assert after.json()["readiness"] == {
        "status": "ready",
        "receiver_ready": True,
        "owner_approved": True,
        "secret_valid": True,
        "allowed_chat_count": 2,
        "public_base_configured": True,
        "live_delivery_verified": True,
        "blockers": [],
    }


def test_invalid_secret_is_rejected(client):
    response = client.post(
        "/api/v1/telegram/webhook",
        json=_update(401, "Привет"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "invalid_webhook_secret"


def test_invalid_json_and_oversized_update_fail_closed(client):
    invalid = client.post(
        "/api/v1/telegram/webhook",
        content=b"{not-json",
        headers={
            "content-type": "application/json",
            "X-Telegram-Bot-Api-Secret-Token": "test_secret_0123456789_abcdefghijk",
        },
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"] == "invalid_telegram_json"

    oversized = client.post(
        "/api/v1/telegram/webhook",
        content=b"{}",
        headers={
            "content-length": str(telegram._MAX_UPDATE_BYTES + 1),
            "content-type": "application/json",
            "X-Telegram-Bot-Api-Secret-Token": "test_secret_0123456789_abcdefghijk",
        },
    )
    assert oversized.status_code == 413
    assert oversized.json()["detail"]["code"] == "telegram_update_too_large"
