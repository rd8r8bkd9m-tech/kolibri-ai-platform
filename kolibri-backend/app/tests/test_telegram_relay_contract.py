import importlib.util
import sys
from pathlib import Path

import pytest


RELAY_DIR = Path(__file__).resolve().parents[2] / "ops" / "telegram-relay"
SPEC = importlib.util.spec_from_file_location("telegram_relayctl", RELAY_DIR / "telegram_relayctl.py")
assert SPEC and SPEC.loader
relay = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = relay
SPEC.loader.exec_module(relay)


def inputs(**overrides):
    values = {
        "home_mesh_ip": "10.99.0.1",
        "relay_mesh_ip": "10.99.0.44",
        "fullchain_path": "/etc/letsencrypt/live/kolibriai.ru/fullchain.pem",
        "private_key_path": "/etc/letsencrypt/live/kolibriai.ru/privkey.pem",
    }
    values.update(overrides)
    return relay.RelayInputs(**values)


def test_relay_exposes_only_exact_webhook_and_preserves_verified_proxy_contract():
    rendered = relay.render_config(inputs())
    relay.validate_contract(rendered)

    assert rendered.count("proxy_pass ") == 1
    assert rendered.count("location = /api/v1/telegram/webhook") == 1
    assert "server 10.99.0.1:443;" in rendered
    assert "listen 78.17.4.108:443 ssl;" in rendered
    assert "allow 149.154.160.0/20;" in rendered
    assert "allow 91.108.4.0/22;" in rendered
    assert "limit_except POST" in rendered
    assert "proxy_ssl_name kolibriai.ru;" in rendered
    assert "proxy_ssl_verify on;" in rendered
    assert "proxy_set_header Host kolibriai.ru;" in rendered
    assert (
        "proxy_set_header X-Telegram-Bot-Api-Secret-Token "
        "$http_x_telegram_bot_api_secret_token;"
    ) in rendered
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in rendered
    assert "location / {\n        return 404;\n    }" in rendered
    assert "TELEGRAM_BOT_TOKEN" not in rendered


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("home_mesh_ip", "10.98.0.1"),
        ("home_mesh_ip", "78.17.4.108"),
        ("relay_mesh_ip", "not-an-ip"),
        ("relay_mesh_ip", "10.98.0.44"),
    ],
)
def test_relay_rejects_non_mesh_or_invalid_addresses(field, value):
    with pytest.raises(relay.RelayError):
        relay.validate_inputs(inputs(**{field: value}), require_files=False)


def test_relay_rejects_same_home_and_relay_address():
    with pytest.raises(relay.RelayError, match="must be different"):
        relay.validate_inputs(inputs(relay_mesh_ip="10.99.0.1"), require_files=False)


def test_prepare_without_live_checks_is_non_privileged_and_writes_sanitized_candidate(tmp_path):
    output = tmp_path / "candidate.conf"
    evidence = relay.prepare(inputs(), output, live_checks=False)

    assert output.is_file()
    assert evidence["status"] == "rendered"
    assert Path(evidence["evidence"]).is_file()
    assert evidence["relay_mesh_cidr_for_home"] == "10.99.0.44/32"
    assert evidence["official_telegram_cidrs"] == ["149.154.160.0/20", "91.108.4.0/22"]
    assert len(evidence["candidate_sha256"]) == 64
    text = output.read_text(encoding="utf-8")
    assert "__" not in text
    assert "secret=" not in text.lower()
