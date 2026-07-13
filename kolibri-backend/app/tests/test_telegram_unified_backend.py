import asyncio
from datetime import datetime, timedelta, timezone
import time

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
    monkeypatch.delenv("KOLIBRI_TELEGRAM_LIVE_VERIFIED", raising=False)
    monkeypatch.delenv("KOLIBRI_TELEGRAM_REQUIRE_OFFICIAL_SOURCE", raising=False)
    monkeypatch.delenv("KOLIBRI_TELEGRAM_TRUSTED_PROXY_CIDRS", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token-never-logged")
    bot_calls = []
    next_message_id = 9000

    async def fake_bot_api(method, payload):
        nonlocal next_message_id
        bot_calls.append((method, dict(payload)))
        if method == "getMe":
            return {"id": 42, "username": "kolibriai_bot"}
        next_message_id += 1
        return {"message_id": next_message_id}

    monkeypatch.setattr(telegram, "_bot_api", fake_bot_api)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, client=("127.0.0.1", 50000)) as test_client:
        with testing_session() as db:
            asyncio.run(telegram.verify_bot_identity(db))
        test_client.telegram_bot_calls = bot_calls
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


def _post(client: TestClient, body: dict, *, forwarded_for: str = "149.154.160.1"):
    return client.post(
        "/api/v1/telegram/webhook",
        json=body,
        headers={
            "X-Telegram-Bot-Api-Secret-Token": "test_secret_0123456789_abcdefghijk",
            "X-Forwarded-For": forwarded_for,
        },
    )


def _process_one(client: TestClient):
    worker_id = "test-worker"
    with next(app.dependency_overrides[get_db]()) as db:
        row_id = telegram.claim_next_update(db, worker_id)
    assert row_id is not None
    with next(app.dependency_overrides[get_db]()) as db:
        return asyncio.run(telegram.process_claimed_update(db, row_id, worker_id))


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
    assert readiness["delivery_evidence"]["status"] == "absent"
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


def test_webhook_ack_is_fast_and_provider_runs_only_after_durable_claim(client, monkeypatch):
    executed = []

    async def fake_execute(request, *, idempotency_key=None):
        executed.append(idempotency_key)
        return {"id": "resp_async", "status": "completed", "content": "Готово"}

    monkeypatch.setattr(telegram, "execute_kolibri_response", fake_execute)
    started = time.monotonic()
    response = _post(client, _update(99, "Проверь асинхронный путь"))
    elapsed = time.monotonic() - started
    assert response.status_code == 200
    assert elapsed < 1.0
    assert response.json()["accepted"] is True
    assert executed == []
    with next(app.dependency_overrides[get_db]()) as db:
        from app.models import TelegramUpdateDB
        ingress = db.query(TelegramUpdateDB).filter(TelegramUpdateDB.update_id == 99).one()
        assert ingress.state == "queued"
        assert ingress.payload["text"] == "Проверь асинхронный путь"
    _process_one(client)
    assert executed == ["telegram:99:response"]


def test_wrong_bot_identity_is_persisted_and_blocks_worker(client, monkeypatch):
    async def wrong_bot(method, payload):
        assert method == "getMe"
        return {"id": 84, "username": "estimate_generator_bot"}

    monkeypatch.setattr(telegram, "_bot_api", wrong_bot)
    with next(app.dependency_overrides[get_db]()) as db:
        with pytest.raises(telegram.TelegramWorkerError, match="telegram_bot_identity_mismatch"):
            asyncio.run(telegram.verify_bot_identity(db))
        evidence = telegram._identity_evidence(db)
        assert evidence["verified"] is False
        assert evidence["username"] == "estimate_generator_bot"
        assert evidence["expected_username"] == "kolibriai_bot"


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
        "ok": True,
        "accepted": True,
        "duplicate": False,
        "update_id": 101,
    }
    assert repeated.status_code == 200
    assert repeated.json() == {
        "ok": True,
        "accepted": False,
        "duplicate": True,
        "update_id": 101,
    }
    assert calls == []
    result = _process_one(client)
    assert result["status"] == "completed"
    assert result["delivery_method"] == "editMessageText"
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
        assert messages[1].attributes == {
            "response_id": "resp_kolibri_telegram_1",
            "channel": "telegram",
        }
        from app.models import TelegramUpdateDB
        ingress = db.query(TelegramUpdateDB).filter(TelegramUpdateDB.update_id == 101).one()
        assert ingress.state == "completed"
        assert ingress.outbound_state == "delivered"
        assert ingress.response_id == "resp_kolibri_telegram_1"
        assert ingress.payload_hash

    methods = [method for method, _ in client.telegram_bot_calls]
    assert methods.count("sendMessage") == 1
    assert methods.count("editMessageText") == 1
    terminal_payload = next(payload for method, payload in client.telegram_bot_calls if method == "editMessageText")
    assert "Готово через единый ответный контур." in terminal_payload["text"]
    assert "/app?project=" in terminal_payload["text"]


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
    _process_one(client)
    assert _post(client, _update(202, "Добавь тесты и пример запуска")).status_code == 200
    _process_one(client)

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
    _process_one(client)
    help_response = _post(client, _update(301, "/help"))
    _process_one(client)
    status_response = _post(client, _update(302, "/status"))
    _process_one(client)
    assert start_response.json()["accepted"] is True
    assert help_response.json()["accepted"] is True
    assert status_response.json()["accepted"] is True
    terminal_texts = [
        payload["text"]
        for method, payload in client.telegram_bot_calls
        if method == "editMessageText"
    ]
    assert all(
        capability in terminal_texts[0].lower()
        for capability in ("вопрос", "изображение", "код", "автоматизация")
    )
    assert "помощник по строительству" not in terminal_texts[1].lower()
    status_text = terminal_texts[2]
    assert "21/21" not in status_text
    assert "healthy" not in status_text
    assert "подтвержд" in status_text.lower()

    # Local commands are subject to the same update ledger and cannot emit a
    # second Telegram message when Telegram retries the update.
    repeated = _post(client, _update(300, "/start"))
    assert repeated.json()["duplicate"] is True


def test_provider_exception_finishes_placeholder_without_leaking_details(client, monkeypatch):
    async def broken_execute(request, *, idempotency_key=None):
        raise RuntimeError("SECRET local/path provider stderr")

    monkeypatch.setattr(telegram, "execute_kolibri_response", broken_execute)
    response = _post(client, _update(350, "Проверь код"))
    assert response.status_code == 200
    _process_one(client)
    terminal = [payload for method, payload in client.telegram_bot_calls if method == "editMessageText"][-1]
    assert "SECRET" not in terminal["text"]
    assert "stderr" not in terminal["text"]

    repeated = _post(client, _update(350, "Проверь код"))
    assert repeated.json()["duplicate"] is True


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
    assert response.json()["accepted"] is True
    result = _process_one(client)
    assert result["delivery_method"] == "sendPhoto"
    photo = next(payload for method, payload in client.telegram_bot_calls if method == "sendPhoto")
    assert photo["chat_id"] == 7001
    assert photo["photo"] == "https://kolibriai.ru/api/v1/artifacts/images/397d471e-3512-44ac-afec-89a3fdf78502"
    assert "Готово. Изображение проверено." in photo["caption"]
    assert "/app?project=" in photo["caption"]

    with next(app.dependency_overrides[get_db]()) as db:
        from app.models import ProjectMessageDB

        assistant = db.query(ProjectMessageDB).filter(
            ProjectMessageDB.role == "assistant"
        ).one()
        assert assistant.status == "completed"
        assert assistant.attributes == {
            "response_id": "resp_image_1",
            "channel": "telegram",
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
    _process_one(client)
    methods = [method for method, _ in client.telegram_bot_calls]
    assert "sendPhoto" not in methods
    assert "editMessageText" in methods


def test_release_contract_has_no_watchdog_gomesh_or_legacy_sender(client):
    info = client.get("/api/v1/telegram/info")
    assert info.status_code == 200
    assert info.json()["receiver_ready"] is True
    assert info.json()["webhook_ready"] is False
    assert info.json()["execution_contract"] == "v1-responses"
    assert info.json()["history_contract"] == "project-history"
    assert info.json()["ingress_contract"] == "durable-async-update-v1"
    assert info.json()["bot_identity"]["username"] == "kolibriai_bot"
    assert info.json()["bot_identity"]["verified"] is True
    assert info.json()["queue"] == {
        "queued": 0,
        "processing": 0,
        "retry": 0,
        "completed": 0,
        "failed": 0,
    }
    assert info.json()["background_senders"] == {
        "watchdog": False,
        "gomesh": False,
        "legacy": False,
    }
    assert info.json()["background_sender_evidence"] == {
        "scope": "telegram-adapter-process",
        "fleet_runtime": "unknown",
    }
    readiness = info.json()["readiness"]
    assert readiness["status"] == "configured_unverified"
    assert readiness["receiver_ready"] is True
    assert readiness["owner_approved"] is True
    assert readiness["secret_valid"] is True
    assert readiness["allowed_chat_count"] == 2
    assert readiness["public_base_configured"] is True
    assert readiness["require_official_source"] is False
    assert readiness["trusted_proxy_config_valid"] is True
    assert readiness["live_delivery_verified"] is False
    assert readiness["delivery_evidence"] == {
        "status": "absent",
        "verified_at": None,
        "age_seconds": None,
        "max_age_seconds": 86400,
        "update_id": None,
        "response_method": None,
        "origin_network": None,
    }
    assert readiness["blockers"] == []
    source = open(telegram.__file__, encoding="utf-8").read().lower()
    assert "sendmessage" in source
    assert "send_photo" not in source
    assert "getupdates" not in source
    assert "httpx.post" not in source


def test_static_live_flag_is_ignored_and_official_delivery_is_persisted(client, monkeypatch):
    before = client.get("/api/v1/telegram/info")
    assert before.status_code == 200
    assert before.json()["webhook_ready"] is False
    assert before.json()["readiness"]["status"] == "configured_unverified"

    monkeypatch.setenv("KOLIBRI_TELEGRAM_LIVE_VERIFIED", "true")
    still_unverified = client.get("/api/v1/telegram/info")
    assert still_unverified.status_code == 200
    assert still_unverified.json()["webhook_ready"] is False
    assert still_unverified.json()["readiness"]["delivery_evidence"]["status"] == "absent"

    delivered = _post(client, _update(390, "/start"))
    assert delivered.status_code == 200
    after = client.get("/api/v1/telegram/info")
    assert after.status_code == 200
    assert after.json()["webhook_ready"] is True
    readiness = after.json()["readiness"]
    assert readiness["status"] == "ready"
    assert readiness["receiver_ready"] is True
    assert readiness["live_delivery_verified"] is True
    assert readiness["delivery_evidence"]["status"] == "current"
    assert readiness["delivery_evidence"]["update_id"] == 390
    assert readiness["delivery_evidence"]["response_method"] == "async_ack"
    assert readiness["delivery_evidence"]["origin_network"] == "149.154.160.0/20"
    assert readiness["delivery_evidence"]["verified_at"]
    assert readiness["blockers"] == []


def test_spoofed_forwarded_for_does_not_create_delivery_evidence(client):
    # The right-most untrusted hop is the origin. A public client cannot put a
    # Telegram address to its left and obtain live status.
    response = _post(client, _update(391, "/start"), forwarded_for="149.154.160.1, 203.0.113.7")
    assert response.status_code == 200
    info = client.get("/api/v1/telegram/info").json()
    assert info["webhook_ready"] is False
    assert info["readiness"]["delivery_evidence"]["status"] == "absent"


def test_official_source_can_be_required_through_explicit_mesh_relay(client, monkeypatch):
    monkeypatch.setenv("KOLIBRI_TELEGRAM_REQUIRE_OFFICIAL_SOURCE", "true")
    monkeypatch.setenv("KOLIBRI_TELEGRAM_TRUSTED_PROXY_CIDRS", "10.99.0.44/32")

    denied = _post(client, _update(392, "/start"), forwarded_for="149.154.160.1, 203.0.113.7")
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "telegram_origin_not_verified"

    accepted = _post(client, _update(393, "/start"), forwarded_for="149.154.160.1, 10.99.0.44")
    assert accepted.status_code == 200
    info = client.get("/api/v1/telegram/info").json()
    assert info["webhook_ready"] is True
    assert info["readiness"]["delivery_evidence"]["origin_network"] == "149.154.160.0/20"


def test_broad_or_telegram_proxy_trust_is_fail_closed(client, monkeypatch):
    monkeypatch.setenv("KOLIBRI_TELEGRAM_REQUIRE_OFFICIAL_SOURCE", "true")
    for invalid in ("0.0.0.0/0", "10.99.0.0/16", "149.154.160.0/20", "not-a-cidr"):
        monkeypatch.setenv("KOLIBRI_TELEGRAM_TRUSTED_PROXY_CIDRS", invalid)
        info = client.get("/api/v1/telegram/info").json()
        assert info["receiver_ready"] is False
        assert info["readiness"]["trusted_proxy_config_valid"] is False
        assert "trusted_proxy_cidrs_invalid" in info["readiness"]["blockers"]


def test_delivery_evidence_database_failure_reports_partial(monkeypatch):
    from sqlalchemy.exc import OperationalError

    class BrokenSession:
        def get(self, model, key):
            raise OperationalError("SELECT", {}, RuntimeError("database unavailable"))

        def rollback(self):
            self.rolled_back = True

    db = BrokenSession()
    evidence = telegram._delivery_evidence(db)
    assert evidence["status"] == "unavailable"
    assert evidence["verified_at"] is None
    assert db.rolled_back is True


def test_stale_delivery_evidence_returns_to_configured_unverified(client):
    assert _post(client, _update(394, "/start")).status_code == 200
    with next(app.dependency_overrides[get_db]()) as db:
        from app.models import TelegramDeliveryEvidenceDB

        evidence = db.get(TelegramDeliveryEvidenceDB, "telegram-webhook-live")
        evidence.verified_at = datetime.now(timezone.utc) - timedelta(days=2)
        db.commit()

    info = client.get("/api/v1/telegram/info").json()
    assert info["webhook_ready"] is False
    assert info["readiness"]["status"] == "configured_unverified"
    assert info["readiness"]["delivery_evidence"]["status"] == "stale"


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
