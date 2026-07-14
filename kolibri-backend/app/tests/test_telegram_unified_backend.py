import asyncio
from datetime import datetime, timedelta, timezone
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.control_plane import ControlPlaneUnavailable
from app.database import Base, get_db
from app.main import app
from app.routers import telegram


class _FakeCurlProcess:
    returncode = 0

    async def communicate(self, body):
        self.body = body
        return b'{"ok":true,"result":{"id":42,"username":"kolibriai_bot"}}', b""


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
    monkeypatch.setenv(
        "KOLIBRI_PROJECT_HANDOFF_SECRET",
        "test-project-handoff-secret-0123456789abcdef",
    )
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


def test_bot_api_interface_route_keeps_token_out_of_argv(monkeypatch):
    captured = {}
    process = _FakeCurlProcess()

    async def fake_subprocess(*argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return process

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token-never-in-argv")
    monkeypatch.setenv("KOLIBRI_TELEGRAM_EGRESS_INTERFACE", "wg-awg-out")
    monkeypatch.setattr(telegram.socket, "if_nametoindex", lambda value: 290)
    monkeypatch.setattr(telegram.asyncio, "create_subprocess_exec", fake_subprocess)

    result = asyncio.run(telegram._bot_api("getMe", {}))

    assert result == {"id": 42, "username": "kolibriai_bot"}
    argv_text = " ".join(captured["argv"])
    assert "secret-token-never-in-argv" not in argv_text
    assert "{{TELEGRAM_BOT_TOKEN}}" in argv_text
    assert "%TELEGRAM_BOT_TOKEN" in captured["argv"]
    assert process.body == b""


def test_bot_api_rejects_invalid_interface_before_execution(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "configured")
    monkeypatch.setenv("KOLIBRI_TELEGRAM_EGRESS_INTERFACE", "../../unsafe")
    with pytest.raises(telegram.TelegramWorkerError, match="telegram_egress_interface_invalid"):
        asyncio.run(telegram._bot_api("getMe", {}))


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
    async def must_not_execute(request, *, idempotency_key=None, owner_scope=None):
        raise AssertionError("an unapproved chat reached the provider")

    monkeypatch.setattr(telegram, "execute_kolibri_response", must_not_execute)
    denied = _post(client, _update(12, "Привет", chat_id=9009))
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "telegram_chat_not_allowed"


def test_webhook_ack_is_fast_and_provider_runs_only_after_durable_claim(client, monkeypatch):
    executed = []

    async def fake_execute(request, *, idempotency_key=None, owner_scope=None):
        executed.append((idempotency_key, owner_scope))
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
    assert executed == [("telegram:99:response", "telegram:7001")]


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

    async def fake_execute(request, *, idempotency_key=None, owner_scope=None):
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


def test_private_telegram_link_hands_the_same_project_to_one_browser_scope(client, monkeypatch):
    async def fake_execute(request, *, idempotency_key=None, owner_scope=None):
        return {
            "id": "resp_handoff",
            "status": "completed",
            "content": "Продолжаем один проект.",
        }

    monkeypatch.setattr(telegram, "execute_kolibri_response", fake_execute)
    assert _post(client, _update(111, "Сохрани контекст между Telegram и Web")).status_code == 200
    result = _process_one(client)
    project_id = result["project_id"]
    terminal_payload = next(
        payload
        for method, payload in reversed(client.telegram_bot_calls)
        if method == "editMessageText"
    )
    link = terminal_payload["text"].rsplit("Открыть проект в Колибри: ", 1)[1]
    parsed = urlsplit(link)
    assert parsed.path == "/app"
    assert parse_qs(parsed.query) == {"project": [project_id]}
    token = parse_qs(parsed.fragment)["handoff"][0]
    assert len(token) == 43
    assert token not in parsed.query

    with TestClient(app) as browser:
        assert browser.post("/api/v1/shell/bootstrap").status_code == 200
        assert browser.get(f"/api/v1/projects/{project_id}").status_code == 404
        invalid = browser.post(
            f"/api/v1/projects/{project_id}/claim",
            json={"token": "B" * 43},
        )
        assert invalid.status_code == 404
        claimed = browser.post(
            f"/api/v1/projects/{project_id}/claim",
            json={"token": token},
        )
        assert claimed.status_code == 200
        assert claimed.json()["id"] == project_id
        messages = browser.get(f"/api/v1/projects/{project_id}/messages")
        assert messages.status_code == 200
        assert [item["content"] for item in messages.json()["items"]] == [
            "Сохрани контекст между Telegram и Web",
            "Продолжаем один проект.",
        ]
        continued = browser.post(
            f"/api/v1/projects/{project_id}/messages",
            json={"role": "user", "content": "Продолжение из браузера"},
        )
        assert continued.status_code == 201
        registered = browser.post(
            "/api/v1/auth/register",
            json={
                "email": "telegram-handoff@example.test",
                "name": "Telegram Owner",
                "password": "secure-password",
            },
        )
        assert registered.status_code == 201
        auth = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        assert browser.get(f"/api/v1/projects/{project_id}").status_code == 404
        assert browser.get(f"/api/v1/projects/{project_id}", headers=auth).status_code == 200
        reclaimed = browser.post(
            f"/api/v1/projects/{project_id}/claim",
            headers=auth,
            json={"token": token},
        )
        assert reclaimed.status_code == 200
        continued_after_login = browser.post(
            f"/api/v1/projects/{project_id}/messages",
            headers=auth,
            json={"role": "user", "content": "Продолжение после входа"},
        )
        assert continued_after_login.status_code == 201

    with TestClient(app) as second_browser:
        assert second_browser.post("/api/v1/shell/bootstrap").status_code == 200
        assert second_browser.get(f"/api/v1/projects/{project_id}").status_code == 404
        repeated = second_browser.post(
            f"/api/v1/projects/{project_id}/claim",
            json={"token": token},
        )
        assert repeated.status_code == 410
        assert repeated.json()["detail"]["code"] == "project_handoff_already_claimed"

    with next(app.dependency_overrides[get_db]()) as db:
        telegram_repo = telegram.ProjectHistoryRepository(db, "telegram:7001")
        assert telegram_repo.get_project(project_id)["id"] == project_id
        assert telegram_repo.list_messages(project_id, after=0, limit=500)["total"] == 4


def test_group_delivery_does_not_emit_forwardable_project_handoff(client, monkeypatch):
    async def fake_execute(request, *, idempotency_key=None, owner_scope=None):
        return {"id": "resp_group", "status": "completed", "content": "Готово в группе."}

    monkeypatch.setattr(telegram, "execute_kolibri_response", fake_execute)
    assert _post(client, _update(112, "Групповая задача", chat_id=-100123)).status_code == 200
    _process_one(client)
    terminal_payload = next(
        payload
        for method, payload in reversed(client.telegram_bot_calls)
        if method == "editMessageText"
    )
    assert terminal_payload["text"] == "Готово в группе."


def test_history_is_reused_without_construction_only_prompt(client, monkeypatch):
    inputs = []

    async def fake_execute(request, *, idempotency_key=None, owner_scope=None):
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
    assert "#handoff=" not in status_text
    assert "/app?project=" not in status_text

    # Local commands are subject to the same update ledger and cannot emit a
    # second Telegram message when Telegram retries the update.
    repeated = _post(client, _update(300, "/start"))
    assert repeated.json()["duplicate"] is True


@pytest.mark.parametrize(
    "query",
    (
        "/status",
        "Фабрика работает?",
        "Какой сейчас статус фабрики?",
        "Фабрика работает 24/7?",
    ),
)
def test_private_factory_status_uses_home_truth_without_provider_or_handoff(
    client,
    monkeypatch,
    query,
):
    probes = []

    class FakeHomeControlPlane:
        async def cluster_stats(self):
            probes.append("cluster_stats")
            return {
                "nodes": {"total": 21, "healthy": 18, "degraded": 2, "offline": 1},
                "agents": {"total": 21, "active": 4, "idle": 16, "paused": 1},
                "tasks": {
                    "total": 37,
                    "running": 4,
                    "queued": 3,
                    "completed": 27,
                    "failed": 2,
                    "cancelled": 1,
                },
                "resources": {"avg_cpu": 35.0, "avg_ram": 51.0, "avg_disk": 62.0},
                "truth": {
                    "availability": "live",
                    "source": "home_control_plane",
                    "as_of": "2026-07-14T10:11:12+00:00",
                },
            }

    async def must_not_execute(request, *, idempotency_key=None):
        raise AssertionError("factory status reached the AI provider")

    def must_not_issue_handoff(*args, **kwargs):
        raise AssertionError("factory status minted a project handoff")

    monkeypatch.setattr(
        telegram,
        "_home_control_plane_adapter",
        lambda: FakeHomeControlPlane(),
    )
    monkeypatch.setattr(telegram, "execute_kolibri_response", must_not_execute)
    monkeypatch.setattr(telegram, "issue_project_handoff", must_not_issue_handoff)

    response = _post(client, _update(320, query))
    assert response.status_code == 200
    _process_one(client)

    assert probes == ["cluster_stats"]
    terminal = [
        payload["text"]
        for method, payload in client.telegram_bot_calls
        if method == "editMessageText"
    ][-1]
    assert "Доступность: live" in terminal
    assert "as_of: 2026-07-14T10:11:12+00:00" in terminal
    assert "Узлы: всего 21; исправны 18; деградировали 2; недоступны 1" in terminal
    assert "Исполнители: всего 21; активны 4; ожидают 16; приостановлены 1" in terminal
    assert (
        "Задачи: всего 37; выполняются 4; в очереди 3; завершены 27; "
        "ошибки 2; отменены 1"
    ) in terminal
    assert "Непрерывность 24/7 одним снимком не подтверждается." in terminal
    assert "#handoff=" not in terminal
    assert "/app?project=" not in terminal


def test_factory_status_probe_failure_is_honest_and_skips_provider(client, monkeypatch):
    class UnavailableHomeControlPlane:
        async def cluster_stats(self):
            raise ControlPlaneUnavailable("control_plane_timeout")

    async def must_not_execute(request, *, idempotency_key=None):
        raise AssertionError("failed factory status probe reached the AI provider")

    monkeypatch.setattr(
        telegram,
        "_home_control_plane_adapter",
        lambda: UnavailableHomeControlPlane(),
    )
    monkeypatch.setattr(telegram, "execute_kolibri_response", must_not_execute)

    response = _post(client, _update(321, "Статус фабрики"))
    assert response.status_code == 200
    _process_one(client)

    terminal = [
        payload["text"]
        for method, payload in client.telegram_bot_calls
        if method == "editMessageText"
    ][-1]
    assert terminal == (
        "Недоступно в текущем сеансе: подтверждённое состояние фабрики. "
        "Причина: control_plane_timeout. "
        "Могу вместо этого: повторить инструментальную проверку после восстановления "
        "Home Control Plane."
    )
    assert "#handoff=" not in terminal
    assert "/app?project=" not in terminal


def test_factory_status_unexpected_failure_does_not_leak_details(client, monkeypatch):
    class BrokenHomeControlPlane:
        async def cluster_stats(self):
            raise RuntimeError("SECRET backend topology and credentials")

    async def must_not_execute(request, *, idempotency_key=None):
        raise AssertionError("failed factory status probe reached the AI provider")

    monkeypatch.setattr(
        telegram,
        "_home_control_plane_adapter",
        lambda: BrokenHomeControlPlane(),
    )
    monkeypatch.setattr(telegram, "execute_kolibri_response", must_not_execute)

    response = _post(client, _update(322, "Фабрика уже работает?"))
    assert response.status_code == 200
    _process_one(client)
    terminal = [
        payload["text"]
        for method, payload in client.telegram_bot_calls
        if method == "editMessageText"
    ][-1]
    assert "Причина: control_plane_unavailable." in terminal
    assert "SECRET" not in terminal
    assert "credentials" not in terminal
    assert "#handoff=" not in terminal


def test_provider_exception_finishes_placeholder_without_leaking_details(client, monkeypatch):
    async def broken_execute(request, *, idempotency_key=None, owner_scope=None):
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
    async def fake_execute(request, *, idempotency_key=None, owner_scope=None):
        return {
            "id": "resp_image_1",
            "status": "completed",
            "content": "Готово. Изображение проверено. " + ("Подробное описание. " * 120),
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
    assert "#handoff=" in photo["caption"]
    assert len(photo["caption"]) <= 1024

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
    async def fake_execute(request, *, idempotency_key=None, owner_scope=None):
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
