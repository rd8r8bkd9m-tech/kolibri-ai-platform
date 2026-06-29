import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_smoke():
    spec = importlib.util.spec_from_file_location("telegram_miniapp_smoke", ROOT / "ops" / "telegram_miniapp_smoke.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_configured_miniapp_url_defaults_to_kolibriai_domain():
    smoke = load_smoke()
    assert smoke.configured_miniapp_url({}) == "https://kolibriai.ru"


def test_validate_miniapp_url_rejects_http_for_telegram_webapp():
    smoke = load_smoke()
    checks = smoke.validate_miniapp_url("http://178.207.11.90:8180")
    by_name = {item["name"]: item for item in checks}
    assert by_name["miniapp_url_present"]["ok"] is True
    assert by_name["miniapp_url_https"]["ok"] is False
    assert by_name["miniapp_url_host"]["ok"] is True


def test_validate_miniapp_url_accepts_https_domain():
    smoke = load_smoke()
    checks = smoke.validate_miniapp_url("https://kolibriai.ru")
    assert all(item["ok"] for item in checks)
