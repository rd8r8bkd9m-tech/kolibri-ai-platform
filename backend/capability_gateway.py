"""Truthful runtime inventory for Codex skills, plugins, and response tools.

Only known manifest metadata is read.  Skill bodies, connector configuration,
environment files, and credentials are deliberately outside this probe.  An
installed manifest is not enough to claim a connected tool: skills require an
executable Codex runner and connector-style plugin tools remain degraded until
an explicit runtime capability manifest reports them available.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


CAPABILITY_SCHEMA_VERSION = "kolibri.capabilities.v1"
VALID_STATUSES = frozenset({"available", "degraded", "unavailable"})
SAFE_JSON_MANIFEST_NAMES = frozenset({
    "capabilities.json",
    "tools.json",
    "kolibri-capabilities.json",
    "kolibri-tools.json",
})
MAX_FRONTMATTER_BYTES = 32 * 1024
MAX_JSON_MANIFEST_BYTES = 256 * 1024
MAX_MANIFESTS = 4096
MAX_SCAN_DEPTH = 12
PACKAGED_NATIVE_TOOL_REGISTRY = Path(__file__).with_name("kolibri-tools.json")
SKILL_PLANNER_STOPWORDS = frozenset({
    "a", "an", "and", "for", "from", "in", "of", "on", "or", "the", "to", "use", "with",
    "в", "для", "и", "из", "или", "на", "по", "с", "со",
})
SECRET_TEXT_PATTERNS = (
    re.compile(r"\b(?:sk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{10,}\b", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{10,}\b", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
)


class CapabilityRequestError(ValueError):
    """A requested response tool is not backed by an available capability."""

    def __init__(self, code: str, requested: str, status: str | None = None):
        super().__init__(code)
        self.code = code
        self.requested = requested
        self.status = status

    def public_detail(self) -> dict[str, Any]:
        detail: dict[str, Any] = {"code": self.code, "requested_tool": self.requested}
        if self.status in VALID_STATUSES:
            detail["capability_status"] = self.status
        return detail


@dataclass(frozen=True)
class CapabilitySnapshot:
    checked_at: float
    status: str
    records: tuple[dict[str, Any], ...]
    probes: tuple[dict[str, Any], ...]


def _sha256(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _redact_text(value: Any, limit: int = 1000) -> str:
    text = str(value or "").replace("\x00", " ")
    for pattern in SECRET_TEXT_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    text = " ".join(text.split())
    return text[:limit]


def _safe_identifier(value: Any, fallback: str = "unknown") -> str:
    text = _redact_text(value, 160).strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "-", text).strip("-:.")
    return text or fallback


def _status_rank(status: str) -> int:
    return {"unavailable": 0, "degraded": 1, "available": 2}.get(status, 0)


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if not key.startswith("_")}


def _stable_planner_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def _runner_binary(provider: str) -> str | None:
    explicit = os.environ.get(f"KOLIBRI_{provider.upper()}_BIN")
    if explicit:
        path = Path(explicit).expanduser()
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(provider)


def _split_configured_paths(value: str) -> list[Path]:
    # os.pathsep is the canonical separator; newline support is useful for
    # systemd EnvironmentFile values without treating commas in paths as data.
    parts = [part for chunk in value.splitlines() for part in chunk.split(os.pathsep)]
    return [Path(part).expanduser() for part in parts if part.strip()]


def configured_manifest_paths() -> tuple[Path, ...]:
    configured = os.environ.get("KOLIBRI_CAPABILITY_MANIFEST_PATHS", "").strip()
    if configured:
        paths = _split_configured_paths(configured)
    else:
        codex_home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
        paths = [codex_home / "skills", codex_home / "plugins" / "cache"]
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve(strict=False)
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def _is_safe_manifest(path: Path) -> bool:
    if path.name == "SKILL.md":
        return True
    if path.name == "plugin.json" and path.parent.name == ".codex-plugin":
        return True
    return path.name in SAFE_JSON_MANIFEST_NAMES


def _iter_manifest_candidates(configured: Iterable[Path]) -> tuple[list[Path], list[dict[str, Any]]]:
    candidates: list[Path] = []
    probes: list[dict[str, Any]] = []
    for configured_path in configured:
        source_id = _sha256(str(configured_path))[:16]
        if configured_path.is_file():
            if _is_safe_manifest(configured_path):
                candidates.append(configured_path)
                probes.append({"source_id": source_id, "status": "available", "reason": "manifest_file_readable"})
            else:
                probes.append({"source_id": source_id, "status": "unavailable", "reason": "manifest_filename_not_allowed"})
            continue
        if not configured_path.is_dir():
            probes.append({"source_id": source_id, "status": "unavailable", "reason": "manifest_root_missing"})
            continue
        root_depth = len(configured_path.parts)
        discovered = 0
        for current, dirs, files in os.walk(configured_path, followlinks=False):
            current_path = Path(current)
            depth = len(current_path.parts) - root_depth
            dirs[:] = [
                name for name in dirs
                if depth < MAX_SCAN_DEPTH and not (current_path / name).is_symlink()
            ]
            for filename in files:
                path = current_path / filename
                # Runtime capability JSON is accepted only when the exact file
                # was configured. A recursive default scan never opens an
                # unrelated plugin's generic tools.json.
                if path.name in SAFE_JSON_MANIFEST_NAMES:
                    continue
                if path.is_symlink() or not _is_safe_manifest(path):
                    continue
                candidates.append(path)
                discovered += 1
                if len(candidates) >= MAX_MANIFESTS:
                    break
            if len(candidates) >= MAX_MANIFESTS:
                break
        probes.append({
            "source_id": source_id,
            "status": "available" if discovered else "degraded",
            "reason": "manifests_discovered" if discovered else "no_supported_manifests",
            "manifest_count": discovered,
        })
        if len(candidates) >= MAX_MANIFESTS:
            probes.append({"source_id": "inventory", "status": "degraded", "reason": "manifest_limit_reached"})
            break
    return sorted(set(candidates)), probes


def _read_limited(path: Path, limit: int) -> bytes:
    with path.open("rb") as handle:
        payload = handle.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("manifest_too_large")
    return payload


def _parse_skill_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    lines: list[str] = []
    total = 0
    with path.open("rb") as handle:
        first = handle.readline()
        total += len(first)
        if first.decode("utf-8", errors="strict").strip() != "---":
            raise ValueError("skill_frontmatter_missing")
        lines.append("---")
        while total <= MAX_FRONTMATTER_BYTES:
            raw_line = handle.readline()
            if not raw_line:
                raise ValueError("skill_frontmatter_unterminated")
            total += len(raw_line)
            if total > MAX_FRONTMATTER_BYTES:
                raise ValueError("skill_frontmatter_too_large")
            line = raw_line.decode("utf-8", errors="strict").rstrip("\r\n")
            lines.append(line)
            if line.strip() == "---":
                break
    metadata: dict[str, str] = {}
    for line in lines[1:-1]:
        match = re.match(r"^(name|description|version)\s*:\s*(.*?)\s*$", line)
        if not match:
            continue
        value = match.group(2).strip().strip("'\"")
        metadata[match.group(1)] = _redact_text(value)
    if not metadata.get("name"):
        raise ValueError("skill_name_missing")
    frontmatter = "\n".join(lines).encode("utf-8")
    return metadata, _sha256(frontmatter)


def _parse_json_manifest(path: Path) -> tuple[dict[str, Any], str]:
    payload = _read_limited(path, MAX_JSON_MANIFEST_BYTES)
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("manifest_root_must_be_object")
    return parsed, _sha256(payload)


def _nearest_plugin(path: Path, plugins: dict[Path, str]) -> str | None:
    parent = path.parent
    while parent != parent.parent:
        if parent in plugins:
            return plugins[parent]
        parent = parent.parent
    return None


class CapabilityGateway:
    """Probe and validate the locally installed Codex capability surface."""

    def __init__(
        self,
        manifest_paths: Iterable[str | Path] | None = None,
        cache_ttl: float | None = None,
        *,
        include_packaged_registry: bool = True,
        native_probe_runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        native_probe_ttl: float | None = None,
    ):
        paths = list(
            Path(item).expanduser().resolve(strict=False) for item in manifest_paths
        ) if manifest_paths is not None else list(configured_manifest_paths())
        if include_packaged_registry:
            packaged = PACKAGED_NATIVE_TOOL_REGISTRY.resolve(strict=False)
            if packaged not in paths:
                paths.append(packaged)
        self.manifest_paths = tuple(paths)
        self.cache_ttl = float(cache_ttl if cache_ttl is not None else os.environ.get("KOLIBRI_CAPABILITY_CACHE_TTL", "5"))
        self.native_probe_ttl = float(
            native_probe_ttl if native_probe_ttl is not None
            else os.environ.get("KOLIBRI_NATIVE_TOOL_PROBE_TTL", "300")
        )
        self.native_probe_runner = native_probe_runner or self._run_native_probe
        self._native_probe_cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._snapshot: CapabilitySnapshot | None = None

    @staticmethod
    def _runtime_status(providers: tuple[str, ...], declared: str = "available") -> tuple[str, str]:
        declared = declared if declared in VALID_STATUSES else "degraded"
        if declared == "unavailable":
            return "unavailable", "manifest_reports_unavailable"
        if not providers or not any(provider == "gateway" or _runner_binary(provider) for provider in providers):
            return "unavailable", "required_runner_missing"
        if declared == "degraded":
            return "degraded", "runtime_not_fully_verified"
        return "available", "manifest_and_runner_available"

    @staticmethod
    def _record(
        *, capability_id: str, kind: str, name: str, description: str,
        status: str, reason: str, manifest_sha256: str, source_type: str,
        invocable: bool, providers: tuple[str, ...], aliases: Iterable[str] = (),
        event_aliases: Iterable[str] = (), requires_event_probe: bool = False,
        read_only: bool = False, probe_prompt: str = "", probe_instructions: str = "",
    ) -> dict[str, Any]:
        canonical_id = _safe_identifier(capability_id)
        safe_name = _safe_identifier(name)
        normalized_aliases = {
            _safe_identifier(alias) for alias in (canonical_id, safe_name, *aliases) if alias
        }
        safe_event_aliases = tuple(sorted({
            _safe_identifier(alias) for alias in event_aliases if alias
        }))
        record = {
            "id": canonical_id,
            "object": "capability",
            "kind": kind,
            "name": safe_name,
            "description": _redact_text(description),
            "status": status,
            "availability_reason": reason,
            "invocable": invocable,
            "source": {"type": source_type, "manifest_sha256": manifest_sha256},
            "_aliases": tuple(sorted(normalized_aliases)),
            "_providers": providers,
            "_event_aliases": safe_event_aliases,
            "_requires_event_probe": requires_event_probe,
            "_probe_prompt": _redact_text(probe_prompt, 1000),
            "_probe_instructions": _redact_text(probe_instructions, 1000),
        }
        if requires_event_probe:
            record.update({
                "native_tool": True,
                "read_only": bool(read_only),
                "event_aliases": list(safe_event_aliases),
                "runtime_probe": {
                    "status": "degraded",
                    "reason": "native_jsonl_event_probe_required",
                    "observed_event_types": [],
                    "observed_tool_names": [],
                    "tool_event_count": 0,
                    "verifier_verdict": "not_run",
                },
            })
        return record

    def _run_native_probe(self, record: dict[str, Any]) -> dict[str, Any]:
        """Run a real read-only Codex request and retain only safe event facts."""
        from provider_gateway import ProviderGateway

        configured_models = tuple(
            item.strip() for item in os.environ.get(
                "KOLIBRI_NATIVE_TOOL_PROBE_CODEX_MODELS", "gpt-5.5,gpt-5.4,gpt-5.3-codex-spark"
            ).split(",") if item.strip()
        )
        gateway = ProviderGateway(
            provider_order=("codex",),
            timeout=int(os.environ.get("KOLIBRI_NATIVE_TOOL_PROBE_TIMEOUT", "90")),
            model_overrides={"codex": configured_models},
        )
        binding = {
            "id": record["id"],
            "kind": "tool",
            "name": record["name"],
            "status": "available",
            "_aliases": tuple(sorted(set(record["_aliases"]) | set(record["_event_aliases"]))),
            "_providers": ("codex",),
        }
        result = gateway.generate(
            record["_probe_prompt"],
            record["_probe_instructions"],
            f"native-probe-{record['id'].replace(':', '-')}",
            requested_tools=[binding],
        )
        attempts = result.technical.get("attempts") if isinstance(result.technical.get("attempts"), list) else []
        calls = [
            call for attempt in attempts if isinstance(attempt, dict)
            for call in (attempt.get("tool_calls") or []) if isinstance(call, dict)
        ]
        verifier = result.technical.get("verifier_evidence")
        if not isinstance(verifier, dict):
            verifier = next((
                attempt.get("verifier_evidence") for attempt in reversed(attempts)
                if isinstance(attempt, dict) and isinstance(attempt.get("verifier_evidence"), dict)
            ), {})
        passed = result.status == "completed" and verifier.get("verdict") == "passed"
        summary = {
            "status": "available" if passed else "degraded",
            "reason": "native_jsonl_event_verified" if passed else "native_jsonl_event_not_verified",
            "observed_event_types": sorted({_safe_identifier(call.get("event_type")) for call in calls}),
            "observed_tool_names": sorted({_safe_identifier(call.get("tool")) for call in calls}),
            "tool_event_count": len(calls),
            "verifier_verdict": str(verifier.get("verdict") or "failed"),
            "error_types": sorted({
                str(attempt.get("error_type")) for attempt in attempts
                if isinstance(attempt, dict) and attempt.get("error_type")
            }),
        }
        binding_sha = str(verifier.get("binding_sha256") or "")
        if re.fullmatch(r"[a-f0-9]{64}", binding_sha):
            summary["evidence_binding_sha256"] = binding_sha
        return summary

    def _apply_native_probe(self, record: dict[str, Any], *, active: bool) -> None:
        if not record.get("_requires_event_probe"):
            return
        if record["status"] == "unavailable":
            record["runtime_probe"] = {
                "status": "unavailable", "reason": record["availability_reason"],
                "observed_event_types": [], "observed_tool_names": [],
                "tool_event_count": 0, "verifier_verdict": "not_run",
            }
            return
        now = time.time()
        cached = self._native_probe_cache.get(record["id"])
        if active:
            try:
                result = dict(self.native_probe_runner(record))
            except Exception:
                result = {
                    "status": "degraded", "reason": "native_probe_runtime_failed",
                    "observed_event_types": [], "observed_tool_names": [],
                    "tool_event_count": 0, "verifier_verdict": "failed", "error_types": [],
                }
            result["_checked_at"] = now
            self._native_probe_cache[record["id"]] = result
            cached = result
        if cached and now - float(cached.get("_checked_at", 0)) <= self.native_probe_ttl:
            public_probe = {key: value for key, value in cached.items() if not key.startswith("_")}
            status = str(public_probe.get("status") or "degraded")
            record["status"] = status if status in VALID_STATUSES else "degraded"
            record["availability_reason"] = str(public_probe.get("reason") or "native_jsonl_event_not_verified")
            record["runtime_probe"] = public_probe
            return
        record["status"] = "degraded"
        record["availability_reason"] = "native_jsonl_event_probe_required"

    def _probe_uncached(
        self,
        *,
        active_native_probes: bool = False,
        native_tool_ids: set[str] | None = None,
    ) -> CapabilitySnapshot:
        candidates, probes = _iter_manifest_candidates(self.manifest_paths)
        records: list[dict[str, Any]] = []
        plugin_roots: dict[Path, str] = {}

        # Parse plugin manifests first so skills beneath them receive stable,
        # non-colliding namespace identifiers.
        for path in (item for item in candidates if item.name == "plugin.json"):
            try:
                payload, digest = _parse_json_manifest(path)
                name = _safe_identifier(payload.get("name") or path.parent.parent.name)
                plugin_root = path.parent.parent.resolve(strict=False)
                plugin_roots[plugin_root] = name
                status, reason = self._runtime_status(("codex",))
                records.append(self._record(
                    capability_id=f"plugin:{name}", kind="plugin", name=name,
                    description=payload.get("description") or "Installed Codex plugin",
                    status=status, reason=reason, manifest_sha256=digest,
                    source_type="codex_plugin_manifest", invocable=False,
                    providers=("codex",), aliases=(name,),
                ))
                for declared_key, suffix, label in (
                    ("mcpServers", "mcp", "MCP tools"),
                    ("apps", "app", "App connector tools"),
                ):
                    if payload.get(declared_key):
                        tool_status, tool_reason = self._runtime_status(("codex",), "degraded")
                        records.append(self._record(
                            capability_id=f"tool:{name}:{suffix}", kind="tool",
                            name=f"{name}:{suffix}", description=f"{label} declared by {name}",
                            status=tool_status, reason=tool_reason,
                            manifest_sha256=digest, source_type="codex_plugin_manifest",
                            invocable=True, providers=("codex",),
                            aliases=(f"{suffix}:{name}",),
                        ))
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
                probes.append({
                    "source_id": _sha256(str(path))[:16],
                    "status": "unavailable", "reason": "plugin_manifest_invalid",
                })

        for path in (item for item in candidates if item.name == "SKILL.md"):
            try:
                metadata, digest = _parse_skill_frontmatter(path)
                name = _safe_identifier(metadata["name"])
                plugin = _nearest_plugin(path.resolve(strict=False), plugin_roots)
                capability_id = f"skill:{plugin}:{name}" if plugin else f"skill:{name}"
                status, reason = self._runtime_status(("codex",))
                records.append(self._record(
                    capability_id=capability_id, kind="skill", name=name,
                    description=metadata.get("description") or "Installed Codex skill",
                    status=status, reason=reason, manifest_sha256=digest,
                    source_type="codex_skill_frontmatter", invocable=True,
                    providers=("codex",), aliases=(f"skill:{name}",),
                ))
            except (OSError, UnicodeError, ValueError):
                probes.append({
                    "source_id": _sha256(str(path))[:16],
                    "status": "unavailable", "reason": "skill_frontmatter_invalid",
                })

        for path in (item for item in candidates if item.name in SAFE_JSON_MANIFEST_NAMES):
            try:
                payload, digest = _parse_json_manifest(path)
                declared_items: list[Any] = []
                for key in ("capabilities", "tools"):
                    values = payload.get(key, [])
                    if not isinstance(values, list):
                        raise ValueError("capability_items_must_be_array")
                    declared_items.extend(values)
                for item in declared_items:
                    if not isinstance(item, dict):
                        raise ValueError("capability_item_must_be_object")
                    name = _safe_identifier(item.get("name") or item.get("id"))
                    kind = _safe_identifier(item.get("kind") or "tool")
                    if kind not in {"tool", "skill", "capability"}:
                        kind = "tool"
                    capability_id = _safe_identifier(item.get("id") or f"{kind}:{name}")
                    raw_providers = item.get("providers") or [item.get("provider") or "codex"]
                    if not isinstance(raw_providers, list):
                        raw_providers = [raw_providers]
                    providers = tuple(dict.fromkeys(
                        _safe_identifier(provider) for provider in raw_providers
                        if _safe_identifier(provider) in {"codex", "mimo", "gateway"}
                    ))
                    status, reason = self._runtime_status(providers, str(item.get("status") or "available"))
                    aliases = item.get("aliases") if isinstance(item.get("aliases"), list) else []
                    event_aliases = item.get("event_aliases") if isinstance(item.get("event_aliases"), list) else []
                    record = self._record(
                        capability_id=capability_id, kind=kind, name=name,
                        description=item.get("description") or "Configured response capability",
                        status=status, reason=reason, manifest_sha256=digest,
                        source_type="kolibri_runtime_capability_manifest",
                        invocable=bool(item.get("invocable", True)), providers=providers,
                        aliases=aliases, event_aliases=event_aliases,
                        requires_event_probe=bool(item.get("requires_event_probe", False)),
                        read_only=bool(item.get("read_only", False)),
                        probe_prompt=str(item.get("probe_prompt") or ""),
                        probe_instructions=str(item.get("probe_instructions") or ""),
                    )
                    self._apply_native_probe(
                        record,
                        active=active_native_probes and (native_tool_ids is None or record["id"] in native_tool_ids),
                    )
                    records.append(record)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
                probes.append({
                    "source_id": _sha256(str(path))[:16],
                    "status": "unavailable", "reason": "runtime_capability_manifest_invalid",
                })

        # Resolve duplicate manifests deterministically, preferring the record
        # with stronger live status and then the stable manifest digest.
        deduplicated: dict[str, dict[str, Any]] = {}
        for record in sorted(records, key=lambda item: (item["id"], item["source"]["manifest_sha256"])):
            current = deduplicated.get(record["id"])
            if current is None or _status_rank(record["status"]) > _status_rank(current["status"]):
                deduplicated[record["id"]] = record
            elif current is not None:
                current["_aliases"] = tuple(sorted(set(current["_aliases"]) | set(record["_aliases"])))
                current["_providers"] = tuple(sorted(set(current["_providers"]) | set(record["_providers"])))

        final_records = tuple(deduplicated[key] for key in sorted(deduplicated))
        statuses = [record["status"] for record in final_records]
        if "available" in statuses and not any(status == "degraded" for status in statuses):
            overall = "available"
        elif "available" in statuses or "degraded" in statuses:
            overall = "degraded"
        else:
            overall = "unavailable"
        return CapabilitySnapshot(time.time(), overall, final_records, tuple(probes))

    def probe(
        self,
        *,
        refresh: bool = False,
        native_tool_ids: set[str] | None = None,
    ) -> CapabilitySnapshot:
        with self._lock:
            if (
                not refresh and self._snapshot is not None
                and time.time() - self._snapshot.checked_at <= self.cache_ttl
            ):
                return self._snapshot
            self._snapshot = self._probe_uncached(
                active_native_probes=refresh,
                native_tool_ids=native_tool_ids,
            )
            return self._snapshot

    def envelope(self, *, tools_only: bool = False, refresh: bool = False) -> dict[str, Any]:
        snapshot = self.probe(refresh=refresh)
        records = [
            _public_record(record) for record in snapshot.records
            if not tools_only or (record["invocable"] and record["kind"] == "tool")
        ]
        counts = {status: sum(item["status"] == status for item in records) for status in sorted(VALID_STATUSES)}
        if counts["available"] and not counts["degraded"] and not counts["unavailable"]:
            envelope_status = "available"
        elif counts["available"] or counts["degraded"]:
            envelope_status = "degraded"
        else:
            envelope_status = "unavailable"
        return {
            "schema_version": CAPABILITY_SCHEMA_VERSION,
            "object": "list",
            "status": envelope_status,
            "data": records,
            "summary": {"total": len(records), **counts},
            "probes": list(snapshot.probes),
        }

    def validate_requested_tools(self, requested_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not requested_tools:
            return []
        snapshot = self.probe()

        requested_identifiers: set[str] = set()
        for index, request in enumerate(requested_tools):
            if not isinstance(request, dict):
                raise CapabilityRequestError("requested_tool_must_be_object", f"index:{index}")
            request_type = _safe_identifier(request.get("type") or "")
            function = request.get("function") if isinstance(request.get("function"), dict) else {}
            requested = request.get("id") or request.get("name") or function.get("name")
            if not requested and request_type not in {"", "function", "skill", "tool"}:
                requested = request_type
            requested_id = _safe_identifier(requested or "", fallback="")
            if not requested_id:
                raise CapabilityRequestError("requested_tool_identifier_missing", f"index:{index}")
            requested_identifiers.add(requested_id)

        # A native tool starts degraded. An explicit user request authorizes a
        # safe live probe; only a matching real JSONL event can promote it.
        probe_ids = {
            record["id"]
            for record in snapshot.records
            if (
                record.get("_requires_event_probe")
                and record.get("availability_reason") == "native_jsonl_event_probe_required"
                and requested_identifiers & {
                    _safe_identifier(alias)
                    for alias in set(record["_aliases"]) | set(record.get("_event_aliases", ()))
                }
            )
        }
        if probe_ids:
            snapshot = self.probe(refresh=True, native_tool_ids=probe_ids)

        alias_map: dict[str, list[dict[str, Any]]] = {}
        skill_alias_map: dict[str, list[dict[str, Any]]] = {}
        for record in snapshot.records:
            if not record["invocable"]:
                continue
            target = alias_map if record["kind"] == "tool" else skill_alias_map
            for alias in set(record["_aliases"]) | set(record.get("_event_aliases", ())):
                target.setdefault(_safe_identifier(alias), []).append(record)

        validated: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, request in enumerate(requested_tools):
            request_type = _safe_identifier(request.get("type") or "")
            function = request.get("function") if isinstance(request.get("function"), dict) else {}
            requested = request.get("id") or request.get("name") or function.get("name")
            if not requested and request_type not in {"", "function", "skill", "tool"}:
                requested = request_type
            requested_id = _safe_identifier(requested or "", fallback="")
            if not requested_id:
                raise CapabilityRequestError("requested_tool_identifier_missing", f"index:{index}")
            matches = list({record["id"]: record for record in alias_map.get(requested_id, [])}.values())
            if not matches:
                if skill_alias_map.get(requested_id):
                    raise CapabilityRequestError(
                        "requested_capability_is_not_native_tool", requested_id,
                        skill_alias_map[requested_id][0]["status"],
                    )
                raise CapabilityRequestError("requested_tool_not_installed", requested_id, "unavailable")
            if len(matches) > 1:
                raise CapabilityRequestError("requested_tool_identifier_ambiguous", requested_id, "unavailable")
            record = matches[0]
            if record["status"] != "available":
                raise CapabilityRequestError("requested_tool_not_available", requested_id, record["status"])
            if record["id"] in seen:
                continue
            seen.add(record["id"])
            validated.append({
                "id": record["id"],
                "kind": record["kind"],
                "name": record["name"],
                "status": record["status"],
                "source": record["source"],
                "_aliases": tuple(sorted(set(record["_aliases"]) | set(record.get("_event_aliases", ())))),
                "_providers": record["_providers"],
            })
        return validated

    def plan_skills(self, value: Any, *, limit: int = 3) -> list[dict[str, Any]]:
        """Select installed skills for the internal prompt layer, never as tools."""
        if isinstance(value, str):
            text = value
        else:
            text = _stable_planner_text(value)
        normalized_text = _redact_text(text, 50_000).lower()
        request_tokens = {
            token for token in re.findall(r"[a-zа-яё0-9][a-zа-яё0-9_.-]{1,}", normalized_text)
            if token not in SKILL_PLANNER_STOPWORDS
        }
        if not request_tokens:
            return []
        candidates: list[tuple[int, str, dict[str, Any]]] = []
        for record in self.probe().records:
            if record["kind"] != "skill" or record["status"] != "available":
                continue
            name = str(record["name"])
            skill_tokens = {
                token for token in re.findall(
                    r"[a-zа-яё0-9][a-zа-яё0-9_.-]{1,}",
                    f"{name} {record.get('description', '')}".lower(),
                ) if token not in SKILL_PLANNER_STOPWORDS
            }
            overlap = request_tokens & skill_tokens
            exact = name in request_tokens or f"skill:{name}" in normalized_text or f"${name}" in normalized_text
            score = (100 if exact else 0) + len(overlap)
            if exact or len(overlap) >= 2:
                candidates.append((score, record["id"], record))
        if any(score >= 100 for score, _, _ in candidates):
            candidates = [item for item in candidates if item[0] >= 100]
        selected: list[dict[str, Any]] = []
        selected_names: set[str] = set()
        for _, _, record in sorted(candidates, key=lambda item: (-item[0], len(item[1]), item[1])):
            if record["name"] in selected_names:
                continue
            selected.append(record)
            selected_names.add(record["name"])
            if len(selected) >= max(0, limit):
                break
        return [{
            "id": record["id"], "kind": "skill", "name": record["name"],
            "status": record["status"], "source": record["source"],
            "_providers": record["_providers"],
        } for record in selected]

    @staticmethod
    def public_bindings(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_public_record(binding) for binding in bindings]


_gateway: CapabilityGateway | Any | None = None


def configure_capability_gateway(gateway: Any) -> Any:
    global _gateway
    _gateway = gateway
    return gateway


def get_capability_gateway() -> CapabilityGateway | Any:
    global _gateway
    if _gateway is None:
        _gateway = CapabilityGateway()
    return _gateway
