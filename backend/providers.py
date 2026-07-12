import asyncio
import re
import threading
import uuid

from capability_gateway import get_capability_gateway
from provider_gateway import get_provider_gateway

KOLIBRI_SYSTEM_PROMPT = (
    "Ты — Kolibri AI, большая языковая модель. " +
    "Отвечай на языке пользователя. Не используй эмодзи."
)

class ProviderGatewayError(RuntimeError):
    def __init__(self, technical):
        super().__init__("provider routes ended without a completed result")
        self.technical = technical


class AIProviderManager:
    def __init__(self, gateway=None):
        self.gateway = gateway

    def _gateway(self):
        return self.gateway or get_provider_gateway()

    def get_status(self):
        availability = self._gateway().available()
        return [{
            "name": "kolibri",
            "available": any(availability.values()),
            "status": "online" if any(availability.values()) else "offline",
        }]

    def get_model_catalog(self):
        return [{"name": "kolibri", "description": "Kolibri AI", "available": any(self._gateway().available().values())}]

    def get_system_prompt(self):
        return KOLIBRI_SYSTEM_PROMPT

    async def generate(self, messages, model="kolibri", provider=None, **kwargs):
        del provider
        execution_mode = str(kwargs.pop("execution_mode", "fast") or "fast").lower()
        requested_response_id = kwargs.pop("response_id", None)
        timeout_seconds = kwargs.pop("timeout_seconds", None)
        reasoning = kwargs.pop("reasoning", None)
        stream_callback = kwargs.pop("stream_callback", None)
        cancel_event = kwargs.pop("cancel_event", None)
        requested_tools = kwargs.pop("requested_tools", None)
        if cancel_event is not None and not isinstance(cancel_event, threading.Event):
            raise ValueError("cancel_event must be a threading.Event")
        if execution_mode not in {"fast", "codex"}:
            raise ValueError("execution_mode must be 'fast' or 'codex'")
        if model not in (None, "", "auto", "kolibri"):
            raise ValueError("Only the public model 'kolibri' is supported")
        system_parts = [KOLIBRI_SYSTEM_PROMPT]
        dialogue = []
        for message in messages or []:
            if message.get("role") == "system":
                system_parts.append(str(message.get("content") or ""))
            else:
                dialogue.append(message)
        capability_gateway = get_capability_gateway()
        # Route skills from the customer's actual request. Generic Kolibri
        # identity/policy text must not accidentally activate unrelated skills.
        planned_skills = capability_gateway.plan_skills({"messages": dialogue})
        gateway = self._gateway()
        response_id = str(requested_response_id or f"chat-{uuid.uuid4().hex}")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", response_id) is None:
            raise ValueError("response_id is invalid")
        instructions = "\n\n".join(part for part in system_parts if part)
        optional_gateway_args = {
            "planned_skills": planned_skills,
            "execution_mode": execution_mode,
            **({"requested_tools": requested_tools} if requested_tools is not None else {}),
            **({"reasoning": reasoning} if reasoning is not None else {}),
            **({"timeout_seconds": timeout_seconds} if timeout_seconds is not None else {}),
            **({"stream_callback": stream_callback} if stream_callback is not None else {}),
            **({"cancel_event": cancel_event} if cancel_event is not None else {}),
        }
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise asyncio.CancelledError
            try:
                result = await asyncio.to_thread(
                    gateway.generate, dialogue, instructions, response_id,
                    **optional_gateway_args,
                )
                break
            except TypeError as exc:
                # Test doubles and compatibility gateways may predate one of
                # the optional routing arguments. Remove only the argument
                # explicitly named by Python; never mask an internal TypeError.
                match = re.search(
                    r"got an unexpected keyword argument ['\"]"
                    r"(planned_skills|execution_mode|requested_tools|reasoning|timeout_seconds|stream_callback|cancel_event)['\"]$",
                    str(exc),
                )
                unsupported = match.group(1) if match else None
                if unsupported not in optional_gateway_args:
                    unsupported = None
                if unsupported is None:
                    raise
                optional_gateway_args.pop(unsupported)
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError
        evidence = result.technical.get("evidence") if isinstance(result.technical.get("evidence"), list) else []
        provider_evidence = any(
            isinstance(item, dict) and item.get("type") == "provider_execution"
            for item in evidence
        )
        verifier_evidence = any(
            isinstance(item, dict)
            and item.get("type") == "deterministic_verifier"
            and item.get("verdict") == "passed"
            for item in evidence
        )
        if result.status != "completed" or not result.text or not provider_evidence or not verifier_evidence:
            raise ProviderGatewayError(result.technical)
        return {"response": result.text, "model": "kolibri", "technical": {"provider_routing": result.technical}}

    async def tool_call(self, message, tools=None):
        capability_gateway = get_capability_gateway()
        bindings = capability_gateway.validate_requested_tools(tools or [])
        planned_skills = capability_gateway.plan_skills(message)
        result = await asyncio.to_thread(
            self._gateway().generate,
            message,
            KOLIBRI_SYSTEM_PROMPT,
            f"tool-{uuid.uuid4().hex}",
            requested_tools=bindings,
            planned_skills=planned_skills,
        )
        evidence = result.technical.get("evidence") if isinstance(result.technical.get("evidence"), list) else []
        verified = any(
            isinstance(item, dict)
            and item.get("type") == "deterministic_verifier"
            and item.get("verdict") == "passed"
            for item in evidence
        )
        if result.status != "completed" or not result.text or not verified:
            raise ProviderGatewayError(result.technical)
        return {
            "response": result.text,
            "model": "kolibri",
            "tools": capability_gateway.public_bindings(bindings),
            "technical": {"provider_routing": result.technical},
        }

manager = AIProviderManager()
