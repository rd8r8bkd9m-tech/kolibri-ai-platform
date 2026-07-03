import hashlib
import hmac
import importlib.util
import json
import urllib.parse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_contracts():
    spec = importlib.util.spec_from_file_location("telegram_superfactory", ROOT / "ops" / "telegram_superfactory.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def signed_init_data(bot_token, user, auth_date=1_800_000_000):
    fields = {
        "auth_date": str(auth_date),
        "query_id": "AAE-test",
        "user": json.dumps(user, separators=(",", ":")),
    }
    data_check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check.encode("utf-8"), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(fields)


def test_polling_receiver_refuses_existing_webhook_without_explicit_delete():
    contracts = load_contracts()
    plan = contracts.plan_update_receiver(
        {"TELEGRAM_UPDATE_RECEIVER": "polling"},
        {"url": "https://example.invalid/tg/webhook"},
    )
    assert plan.should_poll is False
    assert plan.conflict == "webhook_already_configured"
    assert contracts.redacted_receiver_status(plan)["webhook_configured"] is True
    assert "example.invalid" not in json.dumps(contracts.redacted_receiver_status(plan))


def test_polling_receiver_requires_separate_migration_even_when_delete_env_is_set():
    contracts = load_contracts()
    plan = contracts.plan_update_receiver(
        {"TELEGRAM_UPDATE_RECEIVER": "polling", "TELEGRAM_ALLOW_WEBHOOK_DELETE": "1"},
        {"url": "https://example.invalid/tg/webhook"},
    )
    assert plan.should_poll is False
    assert plan.conflict == "webhook_already_configured"
    assert plan.startup_action == "refuse_polling"


def test_telegram_init_data_validation_enforces_hash_freshness_and_owner():
    contracts = load_contracts()
    token = "123456:test-token"
    init_data = signed_init_data(token, {"id": 100, "first_name": "Owner"})
    ok = contracts.validate_telegram_init_data(init_data, token, {100}, now=1_800_000_010)
    assert ok["ok"] is True
    assert ok["role"] == "owner"

    forbidden = contracts.validate_telegram_init_data(init_data, token, {200}, now=1_800_000_010)
    assert forbidden == {"ok": False, "error": "forbidden"}

    tampered = init_data.replace("Owner", "Intruder")
    assert contracts.validate_telegram_init_data(tampered, token, {100}, now=1_800_000_010)["error"] == "hash_mismatch"


def test_runner_policy_reports_missing_api_auth_without_secret_values():
    contracts = load_contracts()
    result = contracts.select_runner("owner_remote_task", "api", {"KOLIBRI_RUNNER_POLICY": "api,local_llm"})
    assert result["runner"] == "api"
    text = json.dumps(result)
    assert "OPENAI_API_KEY" in text
    assert "KOLIBRI_API_RUNNER_TOKEN" in text
    assert "sk-" not in text


def test_runner_policy_reports_codex_auth_missing_when_env_unset():
    contracts = load_contracts()
    result = contracts.runner_policy({"KOLIBRI_RUNNER_POLICY": "codex,mimo,api,local_llm"})
    codex_diag = next(d for d in result["diagnostics"] if d["runner"] == "codex")
    assert codex_diag["available"] is False
    assert "OPENAI_API_KEY" in codex_diag["missing_configuration"]
    text = json.dumps(result)
    assert "sk-" not in text


def test_runner_policy_codex_available_when_key_set():
    contracts = load_contracts()
    result = contracts.runner_policy({"KOLIBRI_RUNNER_POLICY": "codex", "OPENAI_API_KEY": "test-key"})
    codex_diag = next(d for d in result["diagnostics"] if d["runner"] == "codex")
    assert codex_diag["available"] is True
    assert codex_diag["missing_configuration"] == []
