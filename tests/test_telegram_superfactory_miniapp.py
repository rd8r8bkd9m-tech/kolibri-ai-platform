import hashlib
import hmac
import importlib.util
import json
import urllib.parse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def signed_init_data(bot_token, user, auth_date=1_800_000_000):
    fields = {
        "auth_date": str(auth_date),
        "query_id": "AAE-miniapp",
        "user": json.dumps(user, separators=(",", ":")),
    }
    data_check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check.encode("utf-8"), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(fields)


def test_miniapp_init_data_accepts_owner_and_admin_without_leaking_token():
    contracts = load_module("telegram_superfactory", "ops/telegram_superfactory.py")
    bot_token = "123456:compat-test-token"

    owner = contracts.validate_telegram_init_data(
        signed_init_data(bot_token, {"id": 100, "first_name": "Owner"}),
        bot_token,
        {100},
        {200},
        now=1_800_000_010,
    )
    admin = contracts.validate_telegram_init_data(
        signed_init_data(bot_token, {"id": 200, "first_name": "Admin"}),
        bot_token,
        {100},
        {200},
        now=1_800_000_010,
    )

    assert owner["ok"] is True
    assert owner["role"] == "owner"
    assert admin["ok"] is True
    assert admin["role"] == "admin"
    assert "compat-test-token" not in json.dumps([owner, admin])


def test_miniapp_task_envelope_is_verifier_compatible_and_secret_safe(monkeypatch):
    control = load_module("factory_control", "ops/factory_control.py")
    monkeypatch.setenv("KOLIBRI_RUNNER_POLICY", "api,local_llm,codex")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-compat-test-secret")

    body = {
        "objective": "Проверь Superfactory Mini App контракты",
        "runner": "api",
        "task_id": "TGAPP-COMPAT-1",
        "idempotency_key": "telegram-miniapp:test:compat",
    }
    auth = {"ok": True, "role": "owner", "user": {"id": 100, "first_name": "Owner"}}

    envelope = control.miniapp_task_envelope(body, auth)

    assert envelope["task_id"] == "TGAPP-COMPAT-1"
    assert envelope["idempotency_key"] == "telegram-miniapp:test:compat"
    assert envelope["kind"] == "owner_remote_task"
    assert envelope["runner"] == "api"
    assert envelope["source"]["kind"] == "telegram_miniapp"
    assert envelope["source"]["role"] == "owner"
    assert envelope["source"]["user_id"] == 100

    serialized = json.dumps(envelope, ensure_ascii=False)
    assert envelope["runner_policy"]["diagnostics"]
    assert "sk-compat-test-secret" not in serialized
    assert "TELEGRAM_BOT_TOKEN" not in serialized
