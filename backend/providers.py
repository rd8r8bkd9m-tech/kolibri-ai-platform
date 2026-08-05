import json
import os
import re
import ast
import httpx
import ipaddress
import subprocess
from typing import Any
from urllib.parse import urlparse

try:
    from estimate_engine import create_estimate_from_prompt
except Exception:  # pragma: no cover - fallback in isolated test/runtime contexts
    create_estimate_from_prompt = None

KOLIBRI_SYSTEM_PROMPT = (
    "Ты — Kolibri AI. Отвечай на языке пользователя, кратко и по делу. "
    "Не выдумывай факты, если данных не хватает — прямо скажи, что нужно уточнить. "
    "Если запрос похож на смету или расчёт стоимости ремонта, не придумывай цены вручную: "
    "используй только структурированный, аккуратный ответ со сводкой и допущениями."
)

ESTIMATE_RE = re.compile(r"\bсмет\w*\b|\bрассчита(?:й|ть)\s+(?:стоимость|бюджет)|\bestimate\b|\bestimate\b", re.IGNORECASE)


class AIProviderManager:
    _ALLOWED_TOOLS = ("search", "math", "documents", "estimate", "upload", "web_fetch")
    _TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
        "search": {
            "type": "object",
            "required": ("q",),
            "properties": {
                "q": {"type": "string", "min_length": 2, "max_length": 512},
            },
            "max_extra": False,
        },
        "math": {
            "type": "object",
            "required": ("expression",),
            "properties": {
                "expression": {"type": "string", "min_length": 1, "max_length": 512},
            },
            "max_extra": False,
        },
        "documents": {
            "type": "object",
            "required": ("query",),
            "properties": {
                "query": {"type": "string", "min_length": 2, "max_length": 2048},
                "document_id": {"type": "string", "min_length": 1, "max_length": 128},
            },
            "max_extra": False,
        },
        "estimate": {
            "type": "object",
            "required": ("prompt",),
            "properties": {
                "prompt": {"type": "string", "min_length": 2, "max_length": 2000},
            },
            "max_extra": False,
        },
        "upload": {
            "type": "object",
            "required": ("file_name", "content_type", "size_bytes"),
            "properties": {
                "file_name": {"type": "string", "min_length": 1, "max_length": 255},
                "content_type": {"type": "string", "min_length": 1, "max_length": 120},
                "size_bytes": {"type": "int", "min_value": 1, "max_value": 50_000_000},
                "storage_path": {"type": "string", "min_length": 1, "max_length": 260, "path": True},
            },
            "max_extra": False,
        },
        "web_fetch": {
            "type": "object",
            "required": ("url",),
            "properties": {
                "url": {"type": "url", "max_length": 2048},
                "method": {"type": "string", "enum": ("GET", "HEAD"), "default": "GET"},
            },
            "max_extra": False,
        },
    }

    _URL_ALLOWED_SCHEMES = {"http", "https"}

    def __init__(self):
        import os

        self.mimo_path = os.environ.get("KOLIBRI_MIMO_PATH", "/Users/kolibri/.mimocode/bin/mimo")
        self.default_provider = os.environ.get("KOLIBRI_DEFAULT_PROVIDER", "mimo").strip().lower()
        self.ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2:3b").strip() or "llama3.2:3b"

    def get_status(self):
        providers = []
        for name in ["mimo", "ollama", "deepseek", "openai", "anthropic", "local"]:
            if name == "deepseek":
                available = bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())
            elif name == "ollama":
                available = bool(os.environ.get("OLLAMA_BASE_URL", "").strip()) or self.default_provider == "ollama"
            else:
                available = name == "mimo"
            providers.append({
                "name": name,
                "available": available,
                "status": "online" if available else "offline",
            })
        return providers

    def get_model_catalog(self):
        models = [
            {"name": "mimo-auto", "description": "Auto mode (recommended)", "available": True},
            {"name": "mimo-v2.5-pro", "description": "High quality reasoning", "available": True},
            {"name": "mimo-v2.5-lite", "description": "Fast lightweight model", "available": True},
        ]
        if os.environ.get("DEEPSEEK_API_KEY", "").strip():
            models.extend([
                {"name": "deepseek-v4-flash", "description": "DeepSeek fast model", "available": True},
                {"name": "deepseek-v4-pro", "description": "DeepSeek reasoning model", "available": True},
            ])
        if self.default_provider == "ollama" or os.environ.get("OLLAMA_BASE_URL", "").strip():
            models.insert(0, {
                "name": self.ollama_model,
                "description": "Local Ollama model",
                "available": True,
                "provider": "ollama",
            })
        return models

    def get_system_prompt(self):
        return KOLIBRI_SYSTEM_PROMPT

    def _latest_user_message(self, messages):
        for message in reversed(messages or []):
            if str(message.get("role", "")).lower() == "user":
                content = str(message.get("content", "")).strip()
                if content:
                    return content
        return ""

    def _looks_like_estimate_request(self, messages, model: str | None = None, provider: str | None = None) -> bool:
        text = " ".join(
            str(message.get("content", ""))
            for message in (messages or [])
            if str(message.get("role", "")).lower() in {"user", "system"}
        )
        if model and str(model).lower().startswith("estimate"):
            return True
        if provider and str(provider).lower().startswith("estimate"):
            return True
        return bool(ESTIMATE_RE.search(text))

    def _format_estimate_response(self, prompt: str) -> dict:
        if create_estimate_from_prompt is None:
            return {
                "response": "estimate tool disabled in hardened gateway",
                "provider": "estimate_engine",
                "model": "deterministic-estimate-v1",
            }
        estimate = create_estimate_from_prompt(prompt, client_name="Клиент")
        lines = [
            estimate.title,
            f"Объект: {estimate.object_address}",
            "",
            "Разделы:",
        ]
        for section in estimate.sections:
            lines.append(f"- {section.title}")
            for item in section.items:
                lines.append(
                    f"  - {item.name}: {item.quantity} {item.unit} "
                    f"× {item.labor_unit_price + item.material_unit_price} ₽ = {item.line_total()} ₽"
                )
        lines.extend([
            "",
            "Итоги:",
            f"- Работы: {estimate.totals.labor} ₽",
            f"- Материалы: {estimate.totals.materials} ₽",
            f"- Итого: {estimate.totals.grand_total} ₽",
            "",
            "Допущения:",
            "- Это примерная, не рыночная смета.",
            "- Нужны точные обмеры и состав работ для финализации.",
        ])
        return {"response": "\n".join(lines), "provider": "estimate_engine", "model": "deterministic-estimate-v1"}

    def _build_chat_prompt(self, messages, user_msg: str) -> str:
        prompt_parts = [KOLIBRI_SYSTEM_PROMPT]
        for message in messages or []:
            role = str(message.get("role", "user")).strip().lower()
            content = str(message.get("content", "")).strip()
            if not content:
                continue
            label = "Пользователь" if role == "user" else "Ассистент" if role == "assistant" else "Система"
            prompt_parts.append(f"{label}: {content}")
        if user_msg and (not messages or self._latest_user_message(messages) != user_msg):
            prompt_parts.append(f"Пользователь: {user_msg}")
        prompt_parts.append("Ответ:")
        return "\n\n".join(prompt_parts)

    async def generate(self, messages, model="auto", provider=None, **kwargs):
        selected_provider = (provider or self.default_provider or "mimo").strip().lower()
        if self.default_provider == "deepseek" and selected_provider == "mimo":
            selected_provider = "deepseek"
        if model and str(model).lower().startswith("deepseek"):
            selected_provider = "deepseek"

        if selected_provider in {"local", "ollama"} or (model and str(model).lower().startswith("ollama/")):
            selected_provider = "ollama"

        user_msg = self._latest_user_message(messages)
        if self._looks_like_estimate_request(messages, model=model, provider=provider):
            return self._format_estimate_response(user_msg or "Смета")

        if selected_provider == "deepseek":
            api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
            if not api_key:
                return {"response": "Error: DEEPSEEK_API_KEY is not configured", "provider": "error", "model": "none"}

            base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
            chosen_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash").strip() or "deepseek-v4-flash"
            payload = {
                "model": chosen_model,
                "messages": messages,
                "temperature": kwargs.get("temperature", 0.7),
                "max_tokens": kwargs.get("max_tokens", 2048),
                "stream": False,
            }

            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(
                        f"{base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                        json=payload,
                    )
                resp.raise_for_status()
                data = resp.json()
                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                content = message.get("content") or choice.get("text") or ""
                if not content:
                    content = json.dumps(data, ensure_ascii=False)
                return {"response": content, "provider": "deepseek", "model": chosen_model}
            except Exception as e:
                return {"response": f"Error: {e}", "provider": "error", "model": "none"}

        if selected_provider == "ollama":
            chosen_model = self.ollama_model
            if model and str(model).lower().startswith("ollama/"):
                chosen_model = str(model).split("/", 1)[1].strip() or chosen_model
            payload = {
                "model": chosen_model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": kwargs.get("temperature", 0.7),
                    "num_predict": kwargs.get("max_tokens", 2048),
                },
            }
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(
                        f"{self.ollama_base_url}/api/chat",
                        headers={"Content-Type": "application/json", "Accept": "application/json"},
                        json=payload,
                    )
                resp.raise_for_status()
                data = resp.json()
                message = data.get("message") or {}
                content = message.get("content") or data.get("response") or ""
                if not content:
                    return {"response": "Error: Ollama returned an empty response", "provider": "error", "model": "none"}
                return {"response": content, "provider": "ollama", "model": chosen_model}
            except Exception as e:
                return {"response": f"Error: Ollama unavailable: {e}", "provider": "error", "model": "none"}

        prompt = self._build_chat_prompt(messages, user_msg)

        try:
            result = subprocess.run(
                [self.mimo_path, "run", "--dangerously-skip-permissions",
                 "--model", "mimo/mimo-auto", prompt],
                capture_output=True, text=True, timeout=120
            )
            response = result.stdout.strip()
            if not response:
                response = result.stderr.strip()
            return {"response": response, "provider": "mimo", "model": "mimo-auto"}
        except Exception as e:
            return {"response": f"Error: {e}", "provider": "error", "model": "none"}

    @staticmethod
    def _coerce_tool_call_payload(raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None

        name = ""
        raw_name = raw.get("name")
        if isinstance(raw_name, str) and raw_name.strip():
            name = raw_name.strip().lower()

        if not name and isinstance(raw.get("tool"), str):
            name = raw.get("tool", "").strip().lower()

        if not name:
            function = raw.get("function") if isinstance(raw.get("function"), dict) else None
            if function:
                name = str(function.get("name") or "").strip().lower()

        if not name:
            return None

        args = raw.get("args")
        if args is None and isinstance(raw.get("function"), dict):
            args = raw["function"].get("arguments")
        if args is None:
            args = raw.get("arguments")

        if isinstance(args, str):
            try:
                parsed_args = json.loads(args)
            except json.JSONDecodeError:
                return {"tool": name, "args": None, "error": "tool_args_not_json"}
            args = parsed_args

        if not isinstance(args, dict):
            if args is None:
                args = {}
            else:
                return {"tool": name, "args": None, "error": "tool_args_not_object"}

        return {"tool": name, "args": args}

    @staticmethod
    def _coerce_path(value: str) -> str:
        return str(value).replace("\\", "/").strip()

    def _is_private_host(self, host: str | None) -> bool:
        if not host:
            return True
        normalized = host.lower().strip()
        if normalized in {"localhost", "127.0.0.1", "::1"}:
            return True
        try:
            ip = ipaddress.ip_address(normalized)
        except ValueError:
            return False
        return ip.is_private or ip.is_loopback or ip.is_multicast or ip.is_unspecified or ip.is_link_local or ip.is_reserved

    def _is_safe_http_url(self, raw: str) -> bool:
        parsed = urlparse(str(raw).strip())
        if parsed.scheme not in self._URL_ALLOWED_SCHEMES:
            return False
        if not parsed.netloc:
            return False
        if self._is_private_host(parsed.hostname):
            return False
        if parsed.username or parsed.password:
            return False
        return True

    def _is_safe_path(self, value: str) -> bool:
        path = self._coerce_path(value)
        if not path:
            return False
        if path.startswith(("/", "\\")):
            return False
        if path == ".." or path.startswith("../") or path.startswith("..\\"):
            return False
        if "/../" in f"/{path}" or "\\..\\" in f"\\{path}\\":
            return False
        if ".." in path.split("/"):
            return False
        return True

    def _validate_tool_payload(self, tool_name: str, args: dict[str, Any]) -> tuple[bool, str]:
        schema = self._TOOL_SCHEMAS.get(tool_name)
        if not schema:
            return False, "tool_not_allowed"

        if not isinstance(args, dict):
            return False, "tool_args_not_object"

        properties = schema.get("properties", {})
        required = schema.get("required", ())
        for field in required:
            if field not in args:
                return False, "tool_args_missing_required"

        if not schema.get("max_extra", True):
            unknown = [key for key in args if key not in properties]
            if unknown:
                return False, "tool_args_unknown_fields"

        for key, value in args.items():
            prop = properties.get(key)
            if not isinstance(prop, dict):
                return False, "tool_schema_invalid"

            prop_type = str(prop.get("type", "")).strip()
            if prop_type == "string":
                if not isinstance(value, str):
                    return False, "tool_args_type_mismatch"
                text = value.strip()
                if len(text) < int(prop.get("min_length", 0) or 0):
                    return False, "tool_args_length_invalid"
                max_length = int(prop.get("max_length", 0) or 0)
                if max_length > 0 and len(text) > max_length:
                    return False, "tool_args_length_invalid"
                if prop.get("path") and not self._is_safe_path(text):
                    return False, "tool_args_invalid_path"
            elif prop_type == "int":
                if not isinstance(value, int):
                    return False, "tool_args_type_mismatch"
                if value < int(prop.get("min_value", 0) or 0):
                    return False, "tool_args_range_invalid"
                if value > int(prop.get("max_value", 2_147_483_647) or 2_147_483_647):
                    return False, "tool_args_range_invalid"
            elif prop_type == "url":
                if not isinstance(value, str):
                    return False, "tool_args_type_mismatch"
                max_length = int(prop.get("max_length", 0) or 0)
                if max_length > 0 and len(value) > max_length:
                    return False, "tool_args_length_invalid"
                if not value.strip():
                    return False, "tool_args_length_invalid"
                if " " in value:
                    return False, "tool_args_not_allowed_value"
                if not self._is_safe_http_url(value):
                    return False, "tool_args_unsafe_url"
            else:
                return False, "tool_schema_invalid"

            if "enum" in prop and value not in prop["enum"]:
                return False, "tool_args_not_allowed_value"
        return True, ""

    def _safe_eval_math(self, expression: str) -> Any:
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError:
            return None, "tool_execution_failed"
        allowed_nodes = {ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Num, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.FloorDiv, ast.UAdd, ast.USub}
        if not all(type(node) in allowed_nodes for node in ast.walk(tree)):
            return None, "tool_execution_failed"
        try:
            return self._eval_math_node(tree.body), ""
        except Exception:
            return None, "tool_execution_failed"

    def _eval_math_node(self, node: ast.AST) -> float | int:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("non numeric constant")
        if isinstance(node, ast.Num):  # pragma: no cover - py<3.8 compatibility fallback
            return node.n
        if isinstance(node, ast.BinOp):
            left = self._eval_math_node(node.left)
            right = self._eval_math_node(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                return left / right
            if isinstance(node.op, ast.Mod):
                if right == 0:
                    raise ZeroDivisionError("mod by zero")
                return left % right
            if isinstance(node.op, ast.FloorDiv):
                if right == 0:
                    raise ZeroDivisionError("division by zero")
                return left // right
            if isinstance(node.op, ast.Pow):
                return left ** right
            raise ValueError("operator disabled")
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_math_node(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +operand
            if isinstance(node.op, ast.USub):
                return -operand
            raise ValueError("unary operator disabled")
        raise ValueError("unsupported expression")

    async def _execute_tool(self, tool_name: str, args: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        if tool_name == "search":
            query = args.get("q", "").strip()
            return {
                "tool": "search",
                "status": "ok",
                "result": {"query": query, "hits": []},
            }, True

        if tool_name == "math":
            expr = args.get("expression", "")
            value, error = self._safe_eval_math(str(expr))
            if error:
                return {
                    "tool": "math",
                    "status": "denied",
                    "error": error,
                    "reason": "tool_math_invalid_expression",
                }, False
            return {
                "tool": "math",
                "status": "ok",
                "result": {"expression": expr, "value": value},
            }, True

        if tool_name == "documents":
            query = args.get("query", "").strip()
            return {
                "tool": "documents",
                "status": "ok",
                "result": {
                    "query": query,
                    "document_id": args.get("document_id"),
                    "matches": [],
                    "status_note": "document lookup disabled in hardened gateway",
                },
            }, True

        if tool_name == "estimate":
            prompt = args.get("prompt", "")
            preview = re.sub(r"\s+", " ", str(prompt)).strip()[:120]
            return {
                "tool": "estimate",
                "status": "ok",
                "result": {
                    "prompt": preview,
                    "status_note": "estimate tool not executed in gateway",
                },
            }, True

        if tool_name == "upload":
            safe_path = self._coerce_path(args.get("storage_path") or "")
            return {
                "tool": "upload",
                "status": "ok",
                "result": {
                    "file_name": args.get("file_name"),
                    "content_type": args.get("content_type"),
                    "size_bytes": args.get("size_bytes"),
                    "storage_path": safe_path or None,
                    "status_note": "upload quarantined and not written",
                },
            }, True

        if tool_name == "web_fetch":
            return {
                "tool": "web_fetch",
                "status": "ok",
                "result": {
                    "url": args.get("url"),
                    "method": args.get("method", "GET"),
                    "status_note": "web_fetch is intentionally disabled in tool gateway",
                },
            }, True

        return {
            "tool": tool_name,
            "status": "denied",
            "error": "tool_not_allowed",
            "reason": "tool_not_allowed",
        }, False

    async def tool_call(self, message, tools=None):
        message_text = str(message or "").strip()
        requested_tools = list(tools or [])
        if not isinstance(requested_tools, list):
            return {
                "error": "tool_call_invalid_request",
                "message": "tools must be a list",
            }

        tool_results = []
        denied = 0
        allowed = 0

        for raw_tool in requested_tools:
            normalized = self._coerce_tool_call_payload(raw_tool)
            if normalized is None or not normalized.get("tool"):
                tool_results.append({
                    "tool": None,
                    "status": "denied",
                    "reason": "tool_call_invalid_shape",
                })
                denied += 1
                continue

            if "error" in normalized:
                tool_results.append({
                    "tool": normalized.get("tool"),
                    "status": "denied",
                    "reason": normalized["error"],
                })
                denied += 1
                continue

            tool = normalized["tool"]
            args = normalized["args"]
            if tool not in self._ALLOWED_TOOLS:
                tool_results.append({"tool": tool, "status": "denied", "reason": "tool_not_allowed"})
                denied += 1
                continue

            valid, reason = self._validate_tool_payload(tool, args)
            if not valid:
                tool_results.append({"tool": tool, "status": "denied", "reason": reason})
                denied += 1
                continue

            result, is_ok = await self._execute_tool(tool, args)
            if is_ok:
                allowed += 1
            else:
                denied += 1
            tool_results.append(result)

        if denied and allowed:
            status = "partial"
        elif denied:
            status = "blocked"
        else:
            status = "ok"

        return {
            "status": status,
            "message": message_text[:256],
            "summary": {
                "total": len(tool_results),
                "allowed": allowed,
                "denied": denied,
            },
            "tool_results": tool_results,
        }


manager = AIProviderManager()
