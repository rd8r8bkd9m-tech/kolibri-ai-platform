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
    protocol: str = "openai_compatible"
    official: bool = False
    custom_proxy: bool = True
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "")

    @property
    def default_model(self) -> str:
        return os.getenv(self.model_env, "")


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

PROVIDERS: Dict[str, Provider] = {}


def register_provider(p: Provider):
    PROVIDERS[p.id] = p


def get_provider(provider_id: str) -> Optional[Provider]:
    return PROVIDERS.get(provider_id)


def list_providers() -> list:
    return [
        {
            "id": p.id,
            "name": p.name,
            "base_url": p.base_url,
            "protocol": p.protocol,
            "official": p.official,
            "custom_proxy": p.custom_proxy,
            "model": p.default_model,
            "has_key": bool(p.api_key),
            "capabilities": {
                "chat": p.capabilities.chat,
                "models": p.capabilities.models,
                "streaming": p.capabilities.streaming,
                "tools": p.capabilities.tools,
                "json_schema": p.capabilities.json_schema,
                "files": p.capabilities.files,
                "batch": p.capabilities.batch,
            },
        }
        for p in PROVIDERS.values()
    ]


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
    protocol="openai_compatible",
    official=True,
    custom_proxy=False,
    capabilities=ProviderCapabilities(
        chat="true", models="true", streaming="true",
        tools="true", json_schema="true", files="true", batch="true",
    ),
))

# Register MiMo (Xiaomi Token Plan)
register_provider(Provider(
    id="mimo",
    name="MiMo (Xiaomi)",
    base_url=os.getenv("MIMO_BASE_URL", "https://token-plan-sgp.xiaomimimo.com/v1"),
    api_key_env="MIMO_API_KEY",
    model_env="MIMO_MODEL",
    protocol="openai_compatible",
    official=False,
    custom_proxy=False,
    capabilities=ProviderCapabilities(
        chat="true", models="unknown", streaming="unknown",
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
    capabilities=ProviderCapabilities(
        chat="probe", models="unknown", streaming="unknown",
        tools="unknown", json_schema="unknown", files="unknown", batch="unknown",
    ),
))

# Register OpenAI
register_provider(Provider(
    id="openai",
    name="OpenAI",
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    api_key_env="OPENAI_API_KEY",
    model_env="OPENAI_MODEL",
    protocol="openai_compatible",
    official=True,
    custom_proxy=False,
    capabilities=ProviderCapabilities(
        chat="true", models="true", streaming="true",
        tools="true", json_schema="true", files="true", batch="unknown",
    ),
))

# Register DeepSeek
register_provider(Provider(
    id="deepseek",
    name="DeepSeek",
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    api_key_env="DEEPSEEK_API_KEY",
    model_env="DEEPSEEK_MODEL",
    protocol="openai_compatible",
    official=True,
    custom_proxy=False,
    capabilities=ProviderCapabilities(
        chat="true", models="true", streaming="true",
        tools="true", json_schema="true", files="unknown", batch="unknown",
    ),
))

# Register DeepSeek Local Proxy
register_provider(Provider(
    id="deepseek_local",
    name="DeepSeek (Local Proxy)",
    base_url="http://127.0.0.1:8000/deepseek",
    api_key_env="",
    model_env="DEEPSEEK_MODEL",
    protocol="openai_compatible",
    official=False,
    custom_proxy=True,
    capabilities=ProviderCapabilities(
        chat="probe", models="probe", streaming="unknown",
        tools="unknown", json_schema="unknown", files="unknown", batch="unknown",
    ),
))
