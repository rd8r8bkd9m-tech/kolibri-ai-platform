"""Model provider registry — manages AI providers and their capabilities."""
import os
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ProviderCapabilities:
    chat: str = "unknown"
    models: str = "unknown"
    streaming: str = "unknown"
    tools: str = "unknown"
    json_schema: str = "unknown"
    files: str = "unknown"
    batch: str = "unknown"


@dataclass
class Provider:
    id: str
    name: str
    base_url: str
    api_key_env: str
    model_env: str
    default_model_id: str = ""
    protocol: str = "openai_compatible"
    official: bool = False
    custom_proxy: bool = True
    routing_enabled: bool = True
    credential_source: str = "server_env"
    route_id: str | None = None
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)

    @property
    def api_key(self) -> str:
        api_key = os.getenv(self.api_key_env, "")
        if api_key:
            return api_key
        if self.id == "mimo":
            return os.getenv("KOLIBRI_AI_API_KEY", "")
        if self.id == "openai":
            return (
                os.getenv("OPENAI_API_KEY", "")
                or os.getenv("KOLIBRI_API_RUNNER_TOKEN", "")
            )
        return ""

    @property
    def default_model(self) -> str:
        model = os.getenv(self.model_env, "")
        if model:
            return model
        if self.id == "mimo":
            return os.getenv("KOLIBRI_AI_MODEL", "") or self.default_model_id
        return self.default_model_id


def _openai_routing_is_enabled() -> bool:
    configured = os.getenv("OPENAI_REST_ROUTING_ENABLED", "").strip().lower()
    if configured in {"1", "true", "yes", "on"}:
        return True
    preferred = os.getenv("KOLIBRI_PRIMARY_RESPONSE_PROVIDER", "").strip().lower() in {
        "openai",
        "openai_codex",
        "codex_spark",
        "spark",
    }
    if preferred:
        return True
    if configured in {"0", "false", "no", "off"}:
        return False
    return bool(os.getenv("OPENAI_API_KEY", "") or os.getenv("KOLIBRI_API_RUNNER_TOKEN", ""))


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

PROVIDERS: Dict[str, Provider] = {}


def register_provider(p: Provider):
    PROVIDERS[p.id] = p


def get_provider(provider_id: str) -> Optional[Provider]:
    return PROVIDERS.get(provider_id)


def list_providers() -> list:
    from app.ai_provider import PROVIDERS as RUNTIME_PROVIDERS, provider_route_snapshot

    items = []
    for p in PROVIDERS.values():
        runtime_route = RUNTIME_PROVIDERS.get(p.route_id or p.id)
        route = (
            provider_route_snapshot(runtime_route)
            if runtime_route is not None
            else {
                "id": p.route_id or p.id,
                "model": p.default_model,
                "configured": bool(p.api_key),
                "routable": False,
                "status": "unavailable",
                "verified_at": None,
                "failure_kind": None,
                "credential_source": p.credential_source,
            }
        )
        items.append({
            "id": p.id,
            "name": p.name,
            "base_url": p.base_url,
            "protocol": p.protocol,
            "official": p.official,
            "custom_proxy": p.custom_proxy,
            "routing_enabled": p.routing_enabled,
            "credential_source": p.credential_source,
            "model": p.default_model,
            "has_key": bool(p.api_key),
            "route": route,
            "capabilities": {
                "chat": p.capabilities.chat,
                "models": p.capabilities.models,
                "streaming": p.capabilities.streaming,
                "tools": p.capabilities.tools,
                "json_schema": p.capabilities.json_schema,
                "files": p.capabilities.files,
                "batch": p.capabilities.batch,
            },
        })
    return items


# ---------------------------------------------------------------------------
# Register Kimi Proxy CFBT
# ---------------------------------------------------------------------------

register_provider(Provider(
    id="kimi_proxy_cfbt",
    name="Kimi Proxy CFBT",
    base_url=os.getenv("KIMI_CFBT_BASE_URL", "https://cfbt.ccwu.cc/v1"),
    api_key_env="KIMI_CFBT_API_KEY",
    model_env="KIMI_CFBT_MODEL",
    protocol="openai_compatible",
    official=False,
    custom_proxy=True,
    routing_enabled=False,
    capabilities=ProviderCapabilities(
        chat="probe", models="probe", streaming="probe",
        tools="probe", json_schema="probe", files="unknown", batch="unknown",
    ),
))

# Register official Kimi (when API key is available)
register_provider(Provider(
    id="kimi_official",
    name="Kimi API (Moonshot)",
    base_url=os.getenv("KIMI_BASE_URL", "https://api.moonshot.ai/v1"),
    api_key_env="KIMI_API_KEY",
    model_env="KIMI_MODEL",
    default_model_id="kimi-k2.7-code",
    protocol="openai_compatible",
    official=True,
    custom_proxy=False,
    route_id="kimi_code",
    capabilities=ProviderCapabilities(
        chat="probe", models="probe", streaming="probe",
        tools="probe", json_schema="probe", files="probe", batch="probe",
    ),
))

# Register MiMo (Xiaomi Token Plan)
register_provider(Provider(
    id="mimo",
    name="MiMo (Xiaomi)",
    base_url=(
        os.getenv("MIMO_BASE_URL", os.getenv("KOLIBRI_AI_BASE_URL", "https://token-plan-sgp.xiaomimimo.com/v1"))
    ),
    api_key_env="MIMO_API_KEY",
    model_env="MIMO_MODEL",
    default_model_id="mimo-v2.5-pro",
    protocol="openai_compatible",
    official=False,
    custom_proxy=False,
    route_id="mimo",
    capabilities=ProviderCapabilities(
        chat="probe", models="probe", streaming="probe",
        tools="unknown", json_schema="unknown", files="unknown", batch="unknown",
    ),
))

# Register Qwen (browser proxy)
register_provider(Provider(
    id="qwen",
    name="Qwen (Browser Proxy)",
    base_url=os.getenv("QWEN_BASE_URL", "http://127.0.0.1:8787/v1"),
    api_key_env="QWEN_API_KEY",
    model_env="QWEN_MODEL",
    protocol="openai_compatible",
    official=False,
    custom_proxy=True,
    routing_enabled=False,
    credential_source="browser_session_forbidden",
    capabilities=ProviderCapabilities(
        chat="probe", models="unknown", streaming="unknown",
        tools="unknown", json_schema="unknown", files="unknown", batch="unknown",
    ),
))

# Register the Home-owned Codex CLI route.  It authenticates through the
# existing local Codex login and intentionally has no API key field.
register_provider(Provider(
    id="codex_cli",
    name="Codex CLI (Home)",
    base_url="local://codex-cli",
    api_key_env="",
    model_env="CODEX_CLI_MODEL",
    default_model_id=os.getenv("KOLIBRI_CODEX_MODEL", "") or "account-default",
    protocol="codex_cli_jsonl",
    official=True,
    custom_proxy=False,
    routing_enabled=os.getenv("CODEX_CLI_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
    credential_source="home_codex_cli_login",
    route_id="codex_cli",
    capabilities=ProviderCapabilities(
        chat="probe", models="probe", streaming="probe",
        tools="probe", json_schema="unknown", files="unknown", batch="unknown",
    ),
))

# Register OpenAI REST as an explicit opt-in fallback.  Normal production
# execution uses Codex CLI above, not an OpenAI API key.
register_provider(Provider(
    id="openai",
    name="OpenAI",
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    api_key_env="OPENAI_API_KEY",
    model_env="OPENAI_MODEL",
    default_model_id="gpt-5.6-sol",
    protocol="responses",
    official=True,
    custom_proxy=False,
    routing_enabled=_openai_routing_is_enabled(),
    route_id="openai_codex",
    capabilities=ProviderCapabilities(
        chat="probe", models="probe", streaming="probe",
        tools="probe", json_schema="probe", files="probe", batch="probe",
    ),
))

# Register DeepSeek
register_provider(Provider(
    id="deepseek",
    name="DeepSeek",
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    api_key_env="DEEPSEEK_API_KEY",
    model_env="DEEPSEEK_MODEL",
    default_model_id="deepseek-v4-flash",
    protocol="openai_compatible",
    official=True,
    custom_proxy=False,
    route_id="deepseek_flash",
    capabilities=ProviderCapabilities(
        chat="probe", models="probe", streaming="probe",
        tools="probe", json_schema="probe", files="unknown", batch="unknown",
    ),
))
