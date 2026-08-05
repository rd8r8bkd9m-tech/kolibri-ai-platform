#!/usr/bin/env python3
"""Minimal Kolibri Factory control plane sidecar.

The sidecar intentionally uses only the Python standard library. It stores all
task and node state in the existing local Redis server through a tiny RESP
client so it can run next to the legacy control plane without adding packages.

Integrates Truth Factory: claims, evidence, and verdict ledgers for
adversarial review of task outcomes.
"""

from __future__ import annotations

import sys
import os

# Sibling control modules must resolve both when this file is executed as a
# service and when contract tests load it through spec_from_file_location.
_OPS_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _OPS_MODULE_DIR not in sys.path:
    sys.path.insert(0, _OPS_MODULE_DIR)

# Ensure this module is registered in sys.modules so dataclass processing
# works when loaded via spec_from_file_location with a custom name.
try:
    _mod = sys.modules[__name__]
except KeyError:
    sys.modules[__name__] = type(sys)(__name__)

import argparse
import copy
import hashlib
import hmac
import json
import os
import re
import socket
import stat
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Literal
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

CURRENT_DIR = Path(__file__).resolve().parent


def factory_ops_import_paths() -> list[Path]:
    paths = [CURRENT_DIR]
    explicit_ops = os.environ.get("KOLIBRI_OPS_DIR")
    if explicit_ops:
        paths.append(Path(explicit_ops).expanduser())
    repo_root = os.environ.get("KOLIBRI_REPO_ROOT")
    if repo_root:
        paths.append(Path(repo_root).expanduser() / "ops")
    paths.extend([
        Path.cwd() / "ops",
        Path("/opt/kolibri-ai-platform/ops"),
        Path("/opt/kolibri-ai/ops"),
    ])
    resolved: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            resolved.append(path)
            seen.add(key)
    return resolved


for ops_path in reversed(factory_ops_import_paths()):
    if ops_path.exists() and str(ops_path) not in sys.path:
        sys.path.insert(0, str(ops_path))
from activity_adapter import ActivityAdapter
from generated_contracts_v1 import ContractBoundaryClient
from goal_control import (
    GoalCommandError,
    GoalControlService,
    canonical_request_hash,
    load_goal_transitions,
)
from workflow_control import ProjectWorkflowError, ProjectWorkflowControlService
from project_case_control import (
    ProjectCaseControlError,
    ProjectCaseControlService,
    _request_signature,
)
from task_graph_control import (
    TaskGraphCommandError,
    TaskGraphControlService,
)
from product_text_run_control import (
    ProductTextRunControlError,
    ProductTextRunControlService,
    developer_runtime_capability,
    developer_task_objective,
)
from product_goal_initialize_control import (
    ProductGoalInitializeControlError,
    ProductGoalInitializeControlService,
)
from policy_engine import PolicyDecisionService
from telegram_superfactory import plan_update_receiver, runner_policy, select_runner, validate_telegram_init_data


HOME_CONTRACTS_V1 = ContractBoundaryClient("logical_home_control_plane")
LOGICAL_HOME_AUTHORITY_AGENT_CARD_ID = (
    "agentcard_logical_home_authority_v1"
)
FACTORY_AGENT_CONTROL_TOKEN_FILE_ENV = "FACTORY_AGENT_CONTROL_TOKEN_FILE"
FACTORY_AGENT_CONTROL_IDENTITY_MAP_FILE_ENV = (
    "FACTORY_AGENT_CONTROL_IDENTITY_MAP_FILE"
)
FACTORY_AGENT_CONTROL_ALLOWED_NODE_ID_ENV = (
    "FACTORY_AGENT_CONTROL_ALLOWED_NODE_ID"
)
FACTORY_AGENT_CONTROL_ALLOWED_AGENT_ID_ENV = (
    "FACTORY_AGENT_CONTROL_ALLOWED_AGENT_ID"
)
FACTORY_AGENT_CONTROL_ALLOWED_CAPABILITIES_ENV = (
    "FACTORY_AGENT_CONTROL_ALLOWED_CAPABILITIES"
)
FACTORY_AGENT_CONTROL_ALLOWED_AGENT_CARD_SHA256S_ENV = (
    "FACTORY_AGENT_CONTROL_ALLOWED_AGENT_CARD_SHA256S"
)
FACTORY_AGENT_CONTROL_REMOTE_PREFIX_ENV = (
    "FACTORY_AGENT_CONTROL_REMOTE_PREFIX"
)
AGENT_CONTROL_REMOTE_PREFIX = os.environ.get(
    FACTORY_AGENT_CONTROL_REMOTE_PREFIX_ENV,
    "/__kolibri-control/v3",
).strip()
AGENT_CONTROL_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._~+/=-]{32,512}$")
AGENT_CONTROL_IDENTITY_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$",
)
AGENT_CONTROL_NONCE_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{16,128}$")
AGENT_CONTROL_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
AGENT_CONTROL_CAPABILITY_PATTERN = re.compile(
    r"^[a-z][a-z0-9._:-]{1,127}$",
)
AGENT_CONTROL_REMOTE_PREFIX_PATTERN = re.compile(
    r"^/__[A-Za-z0-9][A-Za-z0-9._/-]{1,126}$",
)
AGENT_CONTROL_AUTH_HEADER_NAMES = (
    "Authorization",
    "X-Kolibri-Timestamp",
    "X-Kolibri-Nonce",
    "X-Kolibri-Node-Id",
    "X-Kolibri-Agent-Id",
    "X-Kolibri-Body-SHA256",
    "X-Kolibri-Signature",
)
MAX_REQUEST_BODY_BYTES = int(
    os.environ.get("FACTORY_MAX_REQUEST_BODY_BYTES", str(1024 * 1024)),
)
REQUEST_BODY_TIMEOUT_SECONDS = float(
    os.environ.get("FACTORY_REQUEST_BODY_TIMEOUT_SECONDS", "10"),
)

if (
    not AGENT_CONTROL_REMOTE_PREFIX_PATTERN.fullmatch(
        AGENT_CONTROL_REMOTE_PREFIX,
    )
    or AGENT_CONTROL_REMOTE_PREFIX.endswith("/")
    or "//" in AGENT_CONTROL_REMOTE_PREFIX
    or any(
        part in {".", ".."}
        for part in AGENT_CONTROL_REMOTE_PREFIX.split("/")
    )
):
    raise RuntimeError(
        f"{FACTORY_AGENT_CONTROL_REMOTE_PREFIX_ENV} is invalid",
    )
if not 1024 <= MAX_REQUEST_BODY_BYTES <= 16 * 1024 * 1024:
    raise RuntimeError("FACTORY_MAX_REQUEST_BODY_BYTES must be between 1 KiB and 16 MiB")
if not 1 <= REQUEST_BODY_TIMEOUT_SECONDS <= 60:
    raise RuntimeError("FACTORY_REQUEST_BODY_TIMEOUT_SECONDS must be between 1 and 60")


def resolve_goal_transitions_path() -> Path:
    """Resolve the versioned state machine from an explicit repository root."""

    roots: list[Path] = []
    explicit_root = os.environ.get("KOLIBRI_REPO_ROOT")
    if explicit_root:
        roots.append(Path(explicit_root).expanduser())
    roots.extend([CURRENT_DIR.parent, Path.cwd()])
    roots.extend(path.parent for path in factory_ops_import_paths())
    seen: set[str] = set()
    for root in roots:
        candidate = (
            root
            / "contracts"
            / "v1"
            / "goals"
            / "goal-transitions.json"
        )
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("goal-transitions.json not found in repository roots")


GOAL_TRANSITIONS = load_goal_transitions(resolve_goal_transitions_path())
NAMESPACE = os.environ.get("FACTORY_NAMESPACE", "kolibri_factory")
REDIS_HOST = os.environ.get("FACTORY_REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("FACTORY_REDIS_PORT", "6379"))
LEASE_DURATION = int(os.environ.get("FACTORY_LEASE_DURATION", "60"))
MAX_RETRIES = int(os.environ.get("FACTORY_MAX_RETRIES", "3"))
FABRIC_API_VERSION = "2026-07-01"
FABRIC_MANIFEST_VERSION = "2026-07-01.manifest-01"
CANONICAL_RESPONSE_STATUSES = {"completed", "running", "blocked", "failed", "partial"}
FALLBACK_REASON_TAXONOMY = {
    "api_unreachable",
    "vpn_down",
    "firewall",
    "disk_full",
    "auth_failed",
    "dns",
    "target_node_unavailable",
    "no_node_matches_capability",
    "model_runtime_budget_exhausted",
    "provider_swap_limit_reached",
    "model_runtime_unavailable",
    "admin_scope_denied",
    "unknown",
}
NODE_DEGRADED_AFTER = int(os.environ.get("FACTORY_NODE_DEGRADED_AFTER", "30"))
NODE_STALE_AFTER = int(os.environ.get("FACTORY_NODE_STALE_AFTER", "90"))

STATE_QUEUED = "queued"
STATE_LEASED = "leased"
STATE_RUNNING = "running"
STATE_WAITING_REVIEW = "waiting_review"
STATE_REVIEW = "review"
STATE_COMPLETED = "completed"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"
STATE_RETRY = "retry_scheduled"
STATE_DEAD = "dead_letter"
TERMINAL_STATES = {STATE_COMPLETED, STATE_FAILED, STATE_CANCELLED, STATE_DEAD}
ACTIVE_LEASE_STATES = {STATE_LEASED, STATE_RUNNING, STATE_REVIEW}
LEASE_CONTRACT_VERSION = "2026-07-14.lease-v1"
LEASE_FENCE_FIELDS = ("attempt_id", "lease_id", "fencing_token")
# Only an explicitly active grant may authorize a mutable task operation.
# Pending has not been granted yet; suspended is deliberately paused.
ASSIGNMENT_ACTIVE_STATES = {"active"}
ASSIGNMENT_TERMINAL_STATES = {"completed", "expired", "revoked", "superseded"}
ASSIGNMENT_REVOKED_STATES = {"revoked", "expired"}
BLOCKED_RUNNER_STATES = {"blocked", "degraded", "runner_auth_blocked", "unavailable"}
INACTIVE_AGENT_SLOT_STATES = BLOCKED_RUNNER_STATES | {
    "disabled",
    "draining",
    "failed",
    "offline",
    "stale",
    "stopped",
}

# The lock only serializes mutations inside one control-plane process. Durable
# cross-process ownership and task creation use Redis transactions below.
NODE_UPDATE_LOCK = threading.RLock()

EXECUTION_TASK_CREATE_LUA = r"""
local owner = redis.call("GET", KEYS[1])
if owner and owner ~= ARGV[1] then
  return {"task_identity_conflict", owner}
end

local idem_task_id = redis.call("GET", KEYS[3])
if idem_task_id and idem_task_id ~= ARGV[3] then
  return {"idempotency_conflict", idem_task_id}
end

local current_task = redis.call("GET", KEYS[2])
if current_task and ARGV[4] ~= "1" then
  if not owner then
    redis.call("SET", KEYS[1], ARGV[1])
  end
  if not idem_task_id then
    redis.call("SET", KEYS[3], ARGV[3])
  end
  return {"existing", current_task}
end

redis.call("SET", KEYS[1], ARGV[1])
redis.call("SET", KEYS[2], ARGV[2])
redis.call("SET", KEYS[3], ARGV[3])
redis.call("SADD", KEYS[4], ARGV[3])
redis.call("SREM", KEYS[5], ARGV[3])
redis.call("LREM", KEYS[6], 0, ARGV[3])
redis.call("RPUSH", KEYS[6], ARGV[3])
return {"committed", ARGV[2]}
"""

EXECUTION_TASK_LEASE_LUA = r"""
local current_raw = redis.call("GET", KEYS[1])
if not current_raw then
  return {"task_not_found", ""}
end
local current = cjson.decode(current_raw)
if current["state"] ~= "queued" and
   current["state"] ~= "review" and
   current["state"] ~= "retry_scheduled" then
  return {"task_not_leaseable", current_raw}
end
if tonumber(current["attempt"] or 0) ~= tonumber(ARGV[1]) then
  return {"attempt_conflict", current_raw}
end
redis.call("SET", KEYS[1], ARGV[2])
redis.call("LREM", KEYS[2], 0, ARGV[3])
redis.call("SADD", KEYS[3], ARGV[3])
return {"committed", ARGV[2]}
"""

CANONICAL_EXECUTION_TASK_LEASE_LUA = r"""
-- CANONICAL_EXECUTION_TASK_LEASE_ATOMIC_V2
local current_raw = redis.call("GET", KEYS[1])
if not current_raw then
  return {"task_not_found", ""}
end
if current_raw ~= ARGV[1] then
  return {"stale_task_revision", current_raw}
end
local graph_raw = redis.call("GET", KEYS[4])
if not graph_raw then
  return {"task_graph_not_found", ""}
end
if graph_raw ~= ARGV[4] then
  return {"stale_task_graph_revision", graph_raw}
end
local current = cjson.decode(current_raw)
if current["state"] ~= "queued" and
   current["state"] ~= "review" and
   current["state"] ~= "retry_scheduled" then
  return {"task_not_leaseable", current_raw}
end
if tonumber(current["attempt"] or 0) ~= tonumber(ARGV[3]) then
  return {"attempt_conflict", current_raw}
end
local card_raw = redis.call("GET", KEYS[10])
if not card_raw or card_raw ~= ARGV[11] then
  return {"stale_agent_card_revision", card_raw or ""}
end
if redis.call("SISMEMBER", KEYS[11], ARGV[10]) ~= 1 and
   redis.call("SCARD", KEYS[11]) >= tonumber(ARGV[13]) then
  return {"agent_card_capacity_exhausted", ARGV[10]}
end
local assignment_raw = redis.call("GET", KEYS[7])
if assignment_raw and assignment_raw ~= ARGV[9] then
  return {"assignment_conflict", assignment_raw}
end
local attempt_raw = redis.call("GET", KEYS[5])
if attempt_raw and attempt_raw ~= ARGV[7] then
  return {"attempt_record_conflict", attempt_raw}
end
local owner_raw = redis.call("GET", KEYS[6])
if ARGV[12] == "__kolibri_missing__" then
  if owner_raw then
    return {"stale_owner_state", owner_raw}
  end
elseif owner_raw ~= ARGV[12] then
  return {"stale_owner_state", owner_raw or ""}
end
redis.call("SET", KEYS[1], ARGV[2])
redis.call("LREM", KEYS[2], 0, ARGV[5])
redis.call("SADD", KEYS[3], ARGV[5])
redis.call("SET", KEYS[4], ARGV[6])
redis.call("SET", KEYS[5], ARGV[7])
redis.call("SET", KEYS[6], ARGV[8])
redis.call("SET", KEYS[7], ARGV[9])
redis.call("SADD", KEYS[8], ARGV[10])
redis.call("SADD", KEYS[9], ARGV[10])
redis.call("SADD", KEYS[11], ARGV[10])
return {"committed", ARGV[2]}
"""

CANONICAL_EXECUTION_TASK_MUTATION_LUA = r"""
-- CANONICAL_EXECUTION_TASK_MUTATION_ATOMIC_V2
local expected_records = {
  ARGV[1], ARGV[3], ARGV[5], ARGV[7], ARGV[9]
}
local record_keys = {
  KEYS[1], KEYS[5], KEYS[6], KEYS[7], KEYS[8]
}
for index = 1, 5 do
  local current_raw = redis.call("GET", record_keys[index])
  if not current_raw then
    return {"durable_record_not_found", tostring(index)}
  end
  if current_raw ~= expected_records[index] then
    return {"stale_durable_record", tostring(index)}
  end
end
local current_card = redis.call("GET", KEYS[9])
if ARGV[11] == "__kolibri_missing__" then
  if current_card then
    return {"stale_agent_card", current_card}
  end
elseif current_card ~= ARGV[11] then
  return {"stale_agent_card", current_card or ""}
end
if redis.call("SISMEMBER", KEYS[10], ARGV[13]) ~= 1 then
  return {"stale_assignment_index", ARGV[13]}
end
if redis.call("SCARD", KEYS[11]) ~= 1 or
   redis.call("SISMEMBER", KEYS[11], ARGV[13]) ~= 1 then
  return {"stale_task_assignment_index", ARGV[13]}
end
if redis.call("SISMEMBER", KEYS[12], ARGV[13]) ~= 1 then
  local expected_assignment = cjson.decode(ARGV[9])
  if expected_assignment["status"] ~= "revoked" then
    return {"stale_agent_card_assignment_index", ARGV[13]}
  end
end
redis.call("SET", KEYS[1], ARGV[2])
redis.call("SET", KEYS[5], ARGV[4])
redis.call("SET", KEYS[6], ARGV[6])
redis.call("SET", KEYS[7], ARGV[8])
redis.call("SET", KEYS[8], ARGV[10])
redis.call("SADD", KEYS[10], ARGV[13])
redis.call("SADD", KEYS[11], ARGV[13])
if ARGV[16] == "remove" then
  redis.call("SREM", KEYS[12], ARGV[13])
end
if ARGV[14] == "add" then
  redis.call("SADD", KEYS[2], ARGV[12])
elseif ARGV[14] == "remove" then
  redis.call("SREM", KEYS[2], ARGV[12])
end
if ARGV[15] == "enqueue" then
  redis.call("LREM", KEYS[3], 0, ARGV[12])
  redis.call("RPUSH", KEYS[3], ARGV[12])
  redis.call("LREM", KEYS[4], 0, ARGV[12])
elseif ARGV[15] == "dead" then
  redis.call("LREM", KEYS[3], 0, ARGV[12])
  redis.call("LREM", KEYS[4], 0, ARGV[12])
  redis.call("RPUSH", KEYS[4], ARGV[12])
elseif ARGV[15] == "remove" then
  redis.call("LREM", KEYS[3], 0, ARGV[12])
  redis.call("LREM", KEYS[4], 0, ARGV[12])
end
return {"committed", ARGV[2]}
"""

ASSIGNMENT_REGISTRY_WRITE_LUA = r"""
-- ASSIGNMENT_REGISTRY_WRITE_ATOMIC_V1
local current_raw = redis.call("GET", KEYS[1])
local expected_raw = ARGV[4]
local mode = ARGV[5]
if mode == "create" and current_raw then
  if current_raw == ARGV[1] then
    redis.call("SADD", KEYS[2], ARGV[2])
    redis.call("SADD", KEYS[3], ARGV[2])
    return {"existing", current_raw}
  end
  return {"conflict", current_raw}
end
if mode == "cas" then
  if expected_raw == "__kolibri_missing__" then
    if current_raw then
      return {"stale", current_raw}
    end
  elseif current_raw ~= expected_raw then
    return {"stale", current_raw or ""}
  end
end
if current_raw and KEYS[4] ~= KEYS[3] then
  redis.call("SREM", KEYS[4], ARGV[2])
end
redis.call("SET", KEYS[1], ARGV[1])
redis.call("SADD", KEYS[2], ARGV[2])
redis.call("SADD", KEYS[3], ARGV[2])
return {"committed", ARGV[1]}
"""

ASSIGNMENT_STATUS_EVENT_LUA = r"""
-- ASSIGNMENT_STATUS_EVENT_ATOMIC_V1
local current_raw = redis.call("GET", KEYS[1])
if current_raw ~= ARGV[1] then
  return {"stale", current_raw or ""}
end
if redis.call("SISMEMBER", KEYS[2], ARGV[3]) ~= 1 or
   redis.call("SISMEMBER", KEYS[3], ARGV[3]) ~= 1 then
  return {"stale_assignment_index", ARGV[3]}
end
local current_event = redis.call("GET", KEYS[5])
if current_event and current_event ~= ARGV[5] then
  return {"event_conflict", current_event}
end
redis.call("SET", KEYS[1], ARGV[2])
redis.call("SADD", KEYS[2], ARGV[3])
redis.call("SADD", KEYS[3], ARGV[3])
if ARGV[6] == "remove" then
  redis.call("SREM", KEYS[4], ARGV[3])
end
redis.call("SET", KEYS[5], ARGV[5])
redis.call("SADD", KEYS[6], ARGV[4])
if not current_event then
  redis.call("RPUSH", KEYS[7], ARGV[4])
end
return {"committed", ARGV[2]}
"""

A2A_AGENT_CARD_REGISTRY_WRITE_LUA = r"""
-- A2A_AGENT_CARD_REGISTRY_WRITE_ATOMIC_V1
local current_raw = redis.call("GET", KEYS[1])
local expected_raw = ARGV[4]
local mode = ARGV[5]
if mode == "create" and current_raw then
  if current_raw == ARGV[1] then
    redis.call("SADD", KEYS[2], ARGV[2])
    redis.call("SADD", KEYS[3], ARGV[2])
    return {"existing", current_raw}
  end
  return {"conflict", current_raw}
end
if mode == "cas" then
  if expected_raw == "__kolibri_missing__" then
    if current_raw then
      return {"stale", current_raw}
    end
  elseif current_raw ~= expected_raw then
    return {"stale", current_raw or ""}
  end
end
if current_raw and KEYS[4] ~= KEYS[3] then
  redis.call("SREM", KEYS[4], ARGV[2])
end
redis.call("SET", KEYS[1], ARGV[1])
redis.call("SADD", KEYS[2], ARGV[2])
redis.call("SADD", KEYS[3], ARGV[2])
return {"committed", ARGV[1]}
"""

AGENT_CONTROL_RUNTIME_CARD_REGISTER_LUA = r"""
-- AGENT_CONTROL_RUNTIME_CARD_REGISTER_ATOMIC_V1
local current_card = redis.call("GET", KEYS[1])
if current_card and current_card ~= ARGV[1] then
  return {"conflict", current_card}
end
local current_owner = redis.call("GET", KEYS[4])
if current_owner and current_owner ~= ARGV[2] then
  return {"runtime_profile_conflict", current_owner}
end
redis.call("SET", KEYS[1], ARGV[1])
redis.call("SADD", KEYS[2], ARGV[2])
redis.call("SADD", KEYS[3], ARGV[2])
redis.call("SET", KEYS[4], ARGV[2])
return {
  current_card and "existing" or "committed",
  ARGV[1]
}
"""

A2A_MESSAGE_APPEND_LUA = r"""
-- A2A_MESSAGE_APPEND_ATOMIC_V1
local cursor_raw = redis.call("GET", KEYS[1])
if ARGV[1] == "__kolibri_missing__" then
  if cursor_raw then
    return {"stale_cursor", cursor_raw}
  end
elseif cursor_raw ~= ARGV[1] then
  return {"stale_cursor", cursor_raw or ""}
end
for i = 5, #KEYS do
  local assignment_number = i - 4
  local assignment_id = ARGV[3 + (assignment_number * 2)]
  local expected_assignment = ARGV[4 + (assignment_number * 2)]
  local assignment_raw = redis.call("GET", KEYS[i])
  if assignment_raw ~= expected_assignment then
    return {"stale_assignment", assignment_id}
  end
  if redis.call("SISMEMBER", KEYS[4], assignment_id) ~= 1 then
    return {"stale_assignment_index", assignment_id}
  end
end
local message_raw = redis.call("GET", KEYS[2])
if message_raw and message_raw ~= ARGV[3] then
  return {"message_record_conflict", message_raw}
end
redis.call("SET", KEYS[1], ARGV[2])
redis.call("SET", KEYS[2], ARGV[3])
redis.call("LREM", KEYS[3], 0, ARGV[4])
redis.call("RPUSH", KEYS[3], ARGV[4])
return {"committed", ARGV[2]}
"""

PRODUCT_DEVELOPER_ADMISSION_LUA = r"""
local graph_raw = redis.call("GET", KEYS[1])
if not graph_raw then
  return {"task_graph_not_found", ""}
end
if graph_raw ~= ARGV[1] then
  return {"stale_task_graph_revision", graph_raw}
end
local source_raw = redis.call("GET", KEYS[2])
if not source_raw then
  return {"source_command_not_found", ""}
end
if source_raw ~= ARGV[2] then
  return {"source_command_conflict", source_raw}
end
redis.call("SET", KEYS[2], ARGV[3])
redis.call("SET", KEYS[1], ARGV[4])
return {"committed", ARGV[4]}
"""
PRODUCT_DEVELOPER_ADMISSION_CAS_ATTEMPTS = 3

PRODUCT_DEVELOPER_CANONICAL_LEASE_LUA = r"""
local current_raw = redis.call("GET", KEYS[1])
if not current_raw then
  return {"task_not_found", ""}
end
if current_raw ~= ARGV[1] then
  return {"stale_task_revision", current_raw}
end
local graph_raw = redis.call("GET", KEYS[4])
if not graph_raw then
  return {"task_graph_not_found", ""}
end
if graph_raw ~= ARGV[4] then
  return {"stale_task_graph_revision", graph_raw}
end
local current = cjson.decode(current_raw)
if current["state"] ~= "queued" and
   current["state"] ~= "review" and
   current["state"] ~= "retry_scheduled" then
  return {"task_not_leaseable", current_raw}
end
if tonumber(current["attempt"] or 0) ~= tonumber(ARGV[3]) then
  return {"attempt_conflict", current_raw}
end
for key_index = 5, 9 do
  local existing = redis.call("GET", KEYS[key_index])
  local argument_index = key_index + 2
  if existing and existing ~= ARGV[argument_index] then
    return {"durable_record_conflict", existing}
  end
end
local existing_message = redis.call("GET", KEYS[12])
if existing_message and existing_message ~= ARGV[14] then
  return {"a2a_message_conflict", existing_message}
end
local existing_cursor = redis.call("GET", KEYS[13])
if existing_cursor and existing_cursor ~= ARGV[15] then
  return {"a2a_cursor_conflict", existing_cursor}
end
local runtime_card_raw = redis.call("GET", KEYS[15])
if not runtime_card_raw or runtime_card_raw ~= ARGV[17] then
  return {"stale_runtime_agent_card", runtime_card_raw or ""}
end
local requester_card_raw = redis.call("GET", KEYS[16])
if not requester_card_raw or requester_card_raw ~= ARGV[18] then
  return {"stale_requester_agent_card", requester_card_raw or ""}
end
if redis.call("SISMEMBER", KEYS[17], ARGV[12]) ~= 1 and
   redis.call("SCARD", KEYS[17]) >= tonumber(ARGV[19]) then
  return {"runtime_agent_card_capacity_exhausted", ARGV[12]}
end
if redis.call("SISMEMBER", KEYS[18], ARGV[13]) ~= 1 and
   redis.call("SCARD", KEYS[18]) >= tonumber(ARGV[20]) then
  return {"requester_agent_card_capacity_exhausted", ARGV[13]}
end
redis.call("SET", KEYS[8], ARGV[10])
redis.call("SET", KEYS[9], ARGV[11])
redis.call("SADD", KEYS[10], ARGV[12], ARGV[13])
redis.call("SADD", KEYS[11], ARGV[12], ARGV[13])
redis.call("SADD", KEYS[17], ARGV[12])
redis.call("SADD", KEYS[18], ARGV[13])
redis.call("SET", KEYS[12], ARGV[14])
redis.call("SET", KEYS[13], ARGV[15])
redis.call("LREM", KEYS[14], 0, ARGV[16])
redis.call("RPUSH", KEYS[14], ARGV[16])
redis.call("SET", KEYS[1], ARGV[2])
redis.call("LREM", KEYS[2], 0, ARGV[5])
redis.call("SADD", KEYS[3], ARGV[5])
redis.call("SET", KEYS[4], ARGV[6])
redis.call("SET", KEYS[5], ARGV[7])
redis.call("SET", KEYS[6], ARGV[8])
redis.call("SET", KEYS[7], ARGV[9])
return {"committed", ARGV[2]}
"""

PRODUCT_DEVELOPER_TERMINAL_LUA = r"""
-- PRODUCT_DEVELOPER_TERMINAL_ATOMIC_V2
local current_task = redis.call("GET", KEYS[1])
if not current_task then
  return {"task_not_found", ""}
end
if current_task ~= ARGV[1] then
  return {"stale_task_revision", current_task}
end
local expected_values = {
  ARGV[3], ARGV[5], ARGV[7], ARGV[9], ARGV[11], ARGV[13]
}
for index = 4, 9 do
  local current_value = redis.call("GET", KEYS[index])
  local expected_value = expected_values[index - 3]
  if not current_value then
    return {"durable_record_not_found", ""}
  end
  if current_value ~= expected_value then
    return {"stale_durable_record", current_value}
  end
end
local request_raw = redis.call("GET", KEYS[12])
if not request_raw then
  return {"a2a_request_not_found", ""}
end
local response_raw = redis.call("GET", KEYS[10])
if response_raw and response_raw ~= ARGV[15] then
  return {"a2a_response_conflict", response_raw}
end
local runtime_card_raw = redis.call("GET", KEYS[13])
if ARGV[21] == "__kolibri_missing__" then
  if runtime_card_raw then
    return {"stale_runtime_agent_card", runtime_card_raw}
  end
elseif runtime_card_raw ~= ARGV[21] then
  return {"stale_runtime_agent_card", runtime_card_raw or ""}
end
local requester_card_raw = redis.call("GET", KEYS[14])
if ARGV[22] == "__kolibri_missing__" then
  if requester_card_raw then
    return {"stale_requester_agent_card", requester_card_raw}
  end
elseif requester_card_raw ~= ARGV[22] then
  return {"stale_requester_agent_card", requester_card_raw or ""}
end
if redis.call("SISMEMBER", KEYS[15], ARGV[18]) ~= 1 then
  local runtime_assignment = cjson.decode(ARGV[9])
  if runtime_assignment["status"] ~= "revoked" then
    return {"stale_agent_card_assignment_index", "runtime"}
  end
end
if redis.call("SISMEMBER", KEYS[16], ARGV[19]) ~= 1 then
  local requester_assignment = cjson.decode(ARGV[11])
  if requester_assignment["status"] ~= "revoked" then
    return {"stale_agent_card_assignment_index", "requester"}
  end
end
if redis.call("SISMEMBER", KEYS[17], ARGV[18]) ~= 1 or
   redis.call("SISMEMBER", KEYS[17], ARGV[19]) ~= 1 then
  return {"stale_assignment_index", "global"}
end
if redis.call("SCARD", KEYS[18]) ~= 2 or
   redis.call("SISMEMBER", KEYS[18], ARGV[18]) ~= 1 or
   redis.call("SISMEMBER", KEYS[18], ARGV[19]) ~= 1 then
  return {"stale_task_assignment_index", "task"}
end
redis.call("SET", KEYS[10], ARGV[15])
redis.call("SET", KEYS[9], ARGV[14])
redis.call("LREM", KEYS[11], 0, ARGV[16])
redis.call("RPUSH", KEYS[11], ARGV[16])
redis.call("SET", KEYS[8], ARGV[12])
redis.call("SET", KEYS[7], ARGV[10])
redis.call("SET", KEYS[6], ARGV[8])
redis.call("SET", KEYS[5], ARGV[6])
redis.call("SET", KEYS[4], ARGV[4])
redis.call("SET", KEYS[1], ARGV[2])
redis.call("SREM", KEYS[2], ARGV[17])
redis.call("LREM", KEYS[3], 0, ARGV[17])
redis.call("LREM", KEYS[19], 0, ARGV[17])
if ARGV[20] == "dead" then
  redis.call("RPUSH", KEYS[19], ARGV[17])
end
redis.call("SREM", KEYS[15], ARGV[18])
redis.call("SREM", KEYS[16], ARGV[19])
return {"committed", ARGV[2]}
"""

PRODUCT_DEVELOPER_HEARTBEAT_LUA = r"""
-- PRODUCT_DEVELOPER_HEARTBEAT_ATOMIC_V5
for i = 1, 8 do
  local current_raw = redis.call("GET", KEYS[i])
  if not current_raw then
    return {"record_not_found", tostring(i)}
  end
  if current_raw ~= ARGV[((i - 1) * 2) + 1] then
    return {"stale_record", tostring(i)}
  end
end
if redis.call("SISMEMBER", KEYS[9], ARGV[17]) ~= 1 then
  return {"stale_agent_card_assignment_index", "runtime"}
end
if redis.call("SISMEMBER", KEYS[10], ARGV[18]) ~= 1 then
  return {"stale_agent_card_assignment_index", "requester"}
end
if redis.call("SISMEMBER", KEYS[11], ARGV[17]) ~= 1 or
   redis.call("SISMEMBER", KEYS[11], ARGV[18]) ~= 1 then
  return {"stale_assignment_index", "global"}
end
if redis.call("SCARD", KEYS[12]) ~= 2 or
   redis.call("SISMEMBER", KEYS[12], ARGV[17]) ~= 1 or
   redis.call("SISMEMBER", KEYS[12], ARGV[18]) ~= 1 then
  return {"stale_task_assignment_index", "task"}
end
for i = 1, 6 do
  redis.call("SET", KEYS[i], ARGV[i * 2])
end
return {"committed", ARGV[2]}
"""

EXECUTION_TASK_FENCED_MUTATION_LUA = r"""
local current_raw = redis.call("GET", KEYS[1])
if not current_raw then
  return {"task_not_found", ""}
end
if current_raw ~= ARGV[1] then
  return {"stale_task_revision", current_raw}
end
redis.call("SET", KEYS[1], ARGV[2])
if ARGV[4] == "1" then
  redis.call("SADD", KEYS[2], ARGV[3])
else
  redis.call("SREM", KEYS[2], ARGV[3])
end
if ARGV[5] == "1" then
  redis.call("LREM", KEYS[3], 0, ARGV[3])
  redis.call("RPUSH", KEYS[3], ARGV[3])
else
  redis.call("LREM", KEYS[3], 0, ARGV[3])
end
return {"committed", ARGV[2]}
"""

EXECUTION_TASK_EXPIRE_LUA = r"""
local current_raw = redis.call("GET", KEYS[1])
if not current_raw then
  return {"task_not_found", ""}
end
if current_raw ~= ARGV[1] then
  return {"stale_task_revision", current_raw}
end
redis.call("SET", KEYS[1], ARGV[2])
redis.call("SREM", KEYS[2], ARGV[3])
redis.call("LREM", KEYS[3], 0, ARGV[3])
if ARGV[4] == "retry" then
  redis.call("RPUSH", KEYS[3], ARGV[3])
else
  redis.call("RPUSH", KEYS[4], ARGV[3])
end
return {"committed", ARGV[2]}
"""

EXECUTION_TASK_EXPIRE_CANONICAL_LUA = r"""
local current_raw = redis.call("GET", KEYS[1])
if not current_raw then
  return {"task_not_found", ""}
end
if current_raw ~= ARGV[1] then
  return {"stale_task_revision", current_raw}
end
local graph_raw = redis.call("GET", KEYS[5])
if not graph_raw then
  return {"task_graph_not_found", ""}
end
if graph_raw ~= ARGV[5] then
  return {"stale_task_graph_revision", graph_raw}
end
redis.call("SET", KEYS[1], ARGV[2])
redis.call("SREM", KEYS[2], ARGV[3])
redis.call("LREM", KEYS[3], 0, ARGV[3])
if ARGV[4] == "retry" then
  redis.call("RPUSH", KEYS[3], ARGV[3])
else
  redis.call("RPUSH", KEYS[4], ARGV[3])
end
redis.call("SET", KEYS[5], ARGV[6])
return {"committed", ARGV[2]}
"""

FABRIC_NODE_CATALOG = {
    "home": {
        "node_id": "home",
        "role": "command_node_gateway",
        "display_name": "Связной",
        "api_paths": ["fabric_api", "fallback_relay"],
        "ssh": "emergency_bootstrap_diagnostic_only",
    },
    "main": {
        "node_id": "main",
        "role": "orchestrator_fallback",
        "display_name": "Резервный оркестратор",
        "api_paths": ["fabric_api", "artifact_api"],
        "ssh": "emergency_bootstrap_diagnostic_only",
    },
    "uiap": {
        "node_id": "uiap",
        "role": "knowledge_model_node",
        "display_name": "Знания",
        "api_paths": ["fabric_api", "fallback_relay"],
        "ssh": "emergency_bootstrap_diagnostic_only",
    },
    "qjns": {
        "node_id": "qjns",
        "role": "remote_agent",
        "display_name": "Тестировщик",
        "api_paths": ["fabric_api", "agent_host_api", "fallback_relay"],
        "ssh": "emergency_bootstrap_diagnostic_only",
    },
    "9fts": {
        "node_id": "9fts",
        "role": "implementation_model_node",
        "display_name": "Инженер",
        "api_paths": ["fabric_api", "agent_host_api", "model_node_api", "fallback_relay"],
        "ssh": "emergency_bootstrap_diagnostic_only",
    },
    "new": {
        "node_id": "new",
        "role": "review_agent",
        "display_name": "Ревьюер",
        "api_paths": ["fabric_api", "agent_host_api", "fallback_relay"],
        "ssh": "emergency_bootstrap_diagnostic_only",
    },
}

OWNER_RIGHTS_POLICY = {
    "policy_id": "kolibri-owner-full-control-api",
    "rights": ["fleet:read", "fleet:route", "task:submit", "task:cancel", "node:drain", "artifact:read", "bootstrap:create"],
    "requires": ["authentication", "authorization", "scope", "audit_logging", "key_rotation"],
    "default_scope": "least_privilege_per_command",
    "secret_handling": "tokens and private keys are never returned by Fabric API responses",
    "rotation": "node credentials rotate on bootstrap, compromise, owner request, and at least every 90 days",
}

NODE_IDENTITY_ROTATION_POLICY = {
    "identity": {
        "node_id": "stable non-secret node identifier",
        "agent_id": "process-level API identity",
        "display_name": "human-readable Russian role name for owner reports",
    },
    "key_rotation": {
        "required": True,
        "maximum_age_days": 90,
        "events": ["new_bootstrap", "suspected_compromise", "operator_rotation", "node_reimage"],
        "overlap": "old key remains valid only for a short audited drain window",
    },
    "audit": "all privileged Fabric API calls must record actor, scope, node_id, request_id and outcome",
}

BOOTSTRAP_CONTRACT = {
    "endpoint": "POST /v1/fabric/bootstrap",
    "purpose": "register a new server through the protected Fabric API without printing secrets",
    "required_fields": ["node_id", "role", "display_name", "capabilities", "requested_by"],
    "safe_stub": True,
    "result": "returns bootstrap task metadata and next API action; privileged installers remain external until authenticated",
}

MODEL_CATALOG = [
    {
        "id": "mimo-auto",
        "object": "model",
        "owned_by": "kolibri-fabric",
        "capabilities": ["chat", "responses"],
        "route": "safe_stub_until_model_node_authenticated",
    }
]
MODEL_RUNTIME_REQUEST_TIMEOUT = int(os.environ.get("FACTORY_MODEL_RUNTIME_TIMEOUT_SECONDS", "120"))
MODEL_RUNTIME_ACTIVITY_ATTEMPTS = int(os.environ.get("FACTORY_MODEL_RUNTIME_ACTIVITY_ATTEMPTS", "3"))
MODEL_RUNTIME_ACTIVITY_HEARTBEAT_SECONDS = float(
    os.environ.get("FACTORY_MODEL_RUNTIME_ACTIVITY_HEARTBEAT_SECONDS", "0"),
)
MODEL_RUNTIME_BASES = [u.strip().rstrip("/") for u in os.environ.get("FACTORY_MODEL_RUNTIME_BASE_URLS", "http://127.0.0.1:8000").split(",") if u.strip()]
MODEL_RUNTIME_RETRY_STATUS = {401, 403, 428, 429, 500, 502, 503, 504, 405}
MODEL_RUNTIME_PROVIDER_SWAP_STATUS = {404, 405, 409, 428, 429, 500, 502, 503, 504}
MODEL_RUNTIME_MAX_ROUTE_ATTEMPTS = max(1, int(os.environ.get("FACTORY_MODEL_RUNTIME_MAX_ROUTE_ATTEMPTS", "12")))
MODEL_RUNTIME_MAX_BASES_TO_TRY = max(
    1,
    int(
        os.environ.get(
            "FACTORY_MODEL_RUNTIME_MAX_BASES_TO_TRY",
            str(max(1, len(MODEL_RUNTIME_BASES))),
        )
    ),
)
MODEL_RUNTIME_ADAPTER = ActivityAdapter(
    default_timeout=MODEL_RUNTIME_REQUEST_TIMEOUT,
    default_attempts=MODEL_RUNTIME_ACTIVITY_ATTEMPTS,
)

ADMIN_ENDPOINTS = {
    "/v1/admin/exec": "admin_exec",
    "/v1/admin/service": "admin_service",
    "/v1/admin/git": "admin_git",
    "/v1/admin/bootstrap-node": "admin_bootstrap_node",
    "/v1/admin/rotate-keys": "admin_rotate_keys",
}

OS_CAPABILITY_CATALOG = [
    {"id": "chat.compose", "target": "kolibri-core", "approval": "auto"},
    {"id": "workspace.open", "target": "kolibri-core", "approval": "auto"},
    {"id": "artifact.present", "target": "kolibri-core", "approval": "auto"},
    {"id": "task.create", "target": "control-plane", "approval": "owner-gated"},
    {"id": "agent.delegate", "target": "control-plane", "approval": "owner-gated"},
    {"id": "system.change", "target": "control-plane", "approval": "explicit"},
]

OS_CAPABILITY_BY_ID = {capability["id"]: capability for capability in OS_CAPABILITY_CATALOG}

PROMPT3_REQUIRED_ENDPOINTS = {
    "GET": [
        "/v1/health",
        "/v1/fleet/nodes",
        "/v1/fleet/topology",
        "/v1/fleet/route",
        "/v1/fleet/capabilities",
        "/v1/os/capabilities",
        "/v1/fabric/manifest",
        "/v1/models",
        "/v1/agents/assignments",
        "/v1/agents/status/{task_id}",
        "/v1/agents/artifacts/{task_id}",
    ],
    "POST": [
        "/v1/responses",
        "/v1/chat/completions",
        "/v1/os/capabilities/invoke",
        "/v1/agents/assignments",
        "/v1/agents/tasks",
        "/v1/agents/cancel/{task_id}",
        "/v1/agents/assignments/{assignment_id}/revoke",
        "/v1/admin/exec",
        "/v1/admin/service",
        "/v1/admin/git",
        "/v1/admin/bootstrap-node",
        "/v1/admin/rotate-keys",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_ts() -> float:
    return time.time()


def parse_iso_ts(value: Any) -> float | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError):
        return None


def key(name: str) -> str:
    return f"{NAMESPACE}:{name}"


class RedisError(RuntimeError):
    pass


class Redis:
    def __init__(self, host: str = REDIS_HOST, port: int = REDIS_PORT, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def command(self, *parts: Any) -> Any:
        payload = self._encode(parts)
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.sendall(payload)
            reader = sock.makefile("rb")
            return self._read(reader)

    @staticmethod
    def _encode(parts: tuple[Any, ...]) -> bytes:
        out = [f"*{len(parts)}\r\n".encode()]
        for part in parts:
            data = str(part).encode("utf-8")
            out.append(f"${len(data)}\r\n".encode())
            out.append(data + b"\r\n")
        return b"".join(out)

    def _read(self, reader: Any) -> Any:
        prefix = reader.read(1)
        if not prefix:
            raise RedisError("empty redis response")
        line = reader.readline().rstrip(b"\r\n")
        if prefix == b"+":
            return line.decode("utf-8")
        if prefix == b"-":
            raise RedisError(line.decode("utf-8", "replace"))
        if prefix == b":":
            return int(line)
        if prefix == b"$":
            length = int(line)
            if length == -1:
                return None
            data = reader.read(length)
            reader.read(2)
            return data.decode("utf-8")
        if prefix == b"*":
            count = int(line)
            if count == -1:
                return None
            return [self._read(reader) for _ in range(count)]
        raise RedisError(f"unknown redis response prefix: {prefix!r}")


redis = Redis()


def goal_control_service() -> GoalControlService:
    """Bind Goal commands to the current canonical Redis authority."""

    return GoalControlService(
        redis=redis,
        namespace=NAMESPACE,
        contracts=HOME_CONTRACTS_V1,
        transitions=GOAL_TRANSITIONS,
        workflow_service=workflow_control_service(),
        now=utc_now,
    )


def product_text_run_control_service() -> ProductTextRunControlService:
    """Bind Product text runs to the existing durable Home task authority."""

    return ProductTextRunControlService(
        redis=redis,
        namespace=NAMESPACE,
        contracts=HOME_CONTRACTS_V1,
        create_task=lambda envelope: create_task(
            envelope,
            allow_legacy=True,
        ),
        load_task=load_task,
        dispatch_developer_run=admit_product_developer_run,
        auto_profile=lambda: os.environ.get(
            "FACTORY_PRODUCT_TEXT_AUTO_PROFILE",
        ),
        now=utc_now,
    )


def product_goal_initialize_control_service() -> ProductGoalInitializeControlService:
    """Bind trusted Product initialization to the canonical Goal authority."""

    goal_service = goal_control_service()
    return ProductGoalInitializeControlService(
        redis=redis,
        namespace=NAMESPACE,
        contracts=HOME_CONTRACTS_V1,
        goal_service=goal_service,
        project_case_service=ProjectCaseControlService(
            redis=redis,
            namespace=NAMESPACE,
            contracts=HOME_CONTRACTS_V1,
            goal_service=goal_service,
        ),
        home_authority_grant=logical_home_server_authority_grant,
        now=utc_now,
    )


def workflow_control_service() -> ProjectWorkflowControlService:
    """Bind ProjectWorkflow read-model projection to the same Redis authority."""

    return ProjectWorkflowControlService(
        redis=redis,
        namespace=NAMESPACE,
        now=utc_now,
    )


def task_graph_control_service() -> TaskGraphControlService:
    """Bind TaskGraph commands to the same Redis authority as Goal."""

    return TaskGraphControlService(
        redis=redis,
        namespace=NAMESPACE,
        contracts=HOME_CONTRACTS_V1,
        now=utc_now,
    )


def project_case_control_service() -> ProjectCaseControlService:
    """Bind ProjectCase read model projection to the same Redis authority."""

    return ProjectCaseControlService(
        redis=redis,
        namespace=NAMESPACE,
        contracts=HOME_CONTRACTS_V1,
        goal_service=goal_control_service(),
    )


def policy_decision_service() -> PolicyDecisionService:
    """Bind deterministic policy engine to the same Redis authority."""

    return PolicyDecisionService(
        redis=redis,
        namespace=f"{NAMESPACE}:policy",
        assignment_resolver=load_assignment,
        now=utc_now,
    )


# ── Truth Factory: Claims, Evidence, Verdicts ──────────────────────────

VerdictType = Literal["true", "false", "partial", "not_proven", "blocked", "stale", "degraded"]
ConfidenceLevel = Literal["high", "medium", "low"]
ClaimStatus = Literal["proposed", "challenged", "verified", "rejected", "partial", "not_proven"]
DisputeScope = Literal["technical", "commercial", "legal", "director"]
DisputeDecision = Literal["approved", "rejected", "escalated", "needs_more_evidence", "deadlock"]
DisputeStatus = Literal["resolved", "escalated", "pending", "deadlock", "not_found"]


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class Claim:
    claim_id: str
    task_id: str
    made_by: str
    claim: str
    scope: str
    status: ClaimStatus = "proposed"
    evidence: list[str] = field(default_factory=list)
    counterclaims: list[str] = field(default_factory=list)
    verdict: str = ""
    confidence: str = "low"
    next_action: str = ""
    created_at: str = field(default_factory=utc_now)


@dataclass
class Evidence:
    evidence_id: str
    claim_id: str
    type: str
    source: str
    timestamp: str = field(default_factory=utc_now)
    content_hash: str = ""
    summary: str = ""
    redacted: bool = True
    path: str = ""
    valid: bool = True


@dataclass
class Verdict:
    verdict_id: str
    claim_id: str
    verdict: VerdictType
    confidence: ConfidenceLevel
    evidence: list[str] = field(default_factory=list)
    reasoning: str = ""
    next_action: str = ""
    owner_summary: str = ""
    created_at: str = field(default_factory=utc_now)


@dataclass
class Dispute:
    dispute_id: str
    tenant_id: str
    scope: DisputeScope
    claim_id: str
    actor_id: str
    claim_verdict: str
    claim_evidence_count: int
    risk: str
    decision: DisputeDecision
    status: DisputeStatus
    reason: str
    next_action: str
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    events: list[dict[str, Any]] = field(default_factory=list)


# In-memory truth ledger (persisted via Redis)
_truth_claims: dict[str, Claim] = {}
_truth_evidence: dict[str, Evidence] = {}
_truth_verdicts: dict[str, Verdict] = {}
_dispute_records: dict[str, Dispute] = {}


def truth_key(name: str) -> str:
    return key(f"truth:{name}")


def save_claim(claim: Claim) -> None:
    _truth_claims[claim.claim_id] = claim
    try:
        set_json(truth_key(f"claim:{claim.claim_id}"), asdict(claim))
        redis.command("SADD", truth_key("claim_ids"), claim.claim_id)
    except Exception:
        pass  # In-memory only if Redis unavailable


def save_evidence(ev: Evidence) -> None:
    _truth_evidence[ev.evidence_id] = ev
    try:
        set_json(truth_key(f"evidence:{ev.evidence_id}"), asdict(ev))
        redis.command("SADD", truth_key("evidence_ids"), ev.evidence_id)
    except Exception:
        pass  # In-memory only if Redis unavailable


def save_verdict(v: Verdict) -> None:
    _truth_verdicts[v.verdict_id] = v
    try:
        set_json(truth_key(f"verdict:{v.verdict_id}"), asdict(v))
        redis.command("SADD", truth_key("verdict_ids"), v.verdict_id)
    except Exception:
        pass  # In-memory only if Redis unavailable


def dispute_key(dispute_id: str) -> str:
    return key(f"dispute:{dispute_id}")


def dispute_ids_key() -> str:
    return key("dispute_ids")


def _normalize_dispute_scope(raw_scope: str | None) -> DisputeScope:
    scope = (raw_scope or "").strip().lower()
    if scope in {"technical", "commercial", "legal", "director"}:
        return scope
    return "technical"


def _normalize_dispute_decision(raw_decision: str | None) -> DisputeDecision:
    decision = (raw_decision or "").strip()
    if decision in {
        "approved",
        "rejected",
        "needs_more_evidence",
        "escalated",
        "deadlock",
    }:
        return decision
    return "escalated"


def _normalize_dispute_status(raw_status: str | None) -> DisputeStatus:
    status = (raw_status or "").strip()
    if status in {"resolved", "escalated", "pending", "deadlock", "not_found"}:
        return status
    return "escalated"


def claim_confidence_level(claim: Claim | None) -> str:
    if not claim:
        return "low"
    return str(claim.confidence or "low")


def claim_evidence_count(claim: Claim | None) -> int:
    if not claim:
        return 0
    return len(claim.evidence)


def _claim_required_confidence(scope: DisputeScope) -> str:
    required = {
        "technical": "low",
        "commercial": "low",
        "legal": "high",
        "director": "low",
    }
    return required.get(scope, "low")


def _claim_required_evidence(scope: DisputeScope) -> int:
    required = {
        "technical": 1,
        "commercial": 1,
        "legal": 2,
        "director": 1,
    }
    return required.get(scope, 1)


def evaluate_dispute_risk(scope: DisputeScope, claim: Claim | None) -> str:
    if not claim:
        return "high"
    confidence = claim_confidence_level(claim)
    evidence_count = claim_evidence_count(claim)
    required_evidence = _claim_required_evidence(scope)
    if confidence == "low":
        return "high"
    if confidence == "medium" and _claim_required_confidence(scope) == "high":
        return "high"
    if evidence_count < required_evidence:
        return "high"
    if confidence == "high" and evidence_count >= max(required_evidence, 2):
        return "low"
    return "medium"


def resolve_dispute(scope: DisputeScope, claim: Claim | None, requested_decision: str | None) -> tuple[DisputeDecision, DisputeStatus, str]:
    if requested_decision:
        if requested_decision not in {"approved", "rejected", "needs_more_evidence", "escalated", "deadlock"}:
            return "escalated", "deadlock", "invalid requested_decision"
        if requested_decision == "needs_more_evidence":
            return "needs_more_evidence", "pending", "independent reviewer requested additional evidence"
        if requested_decision in {"approved", "rejected"}:
            return requested_decision, "resolved", "director explicit outcome"
        if requested_decision == "deadlock":
            return "deadlock", "deadlock", "director marked deadlock"
        return requested_decision, "escalated", "director escalated dispute"

    if not claim:
        return "escalated", "not_found", "claim not found"
    risk = evaluate_dispute_risk(scope, claim)
    if risk == "high":
        return "escalated", "escalated", "low confidence or insufficient evidence triggered escalation"
    if claim.verdict == "true":
        return "approved", "resolved", "truth verdict accepted with required evidence/risk"
    if claim.verdict == "false":
        return "rejected", "resolved", "truth verdict rejected with required evidence/risk"
    if claim.verdict in {"partial", "not_proven", "stale", "degraded"}:
        return "needs_more_evidence", "pending", "truth verdict is partial/not_proven"
    return "needs_more_evidence", "pending", "insufficient deterministic evidence for final decision"


def save_dispute(dispute: Dispute) -> None:
    _dispute_records[dispute.dispute_id] = dispute
    dispute.updated_at = utc_now()
    try:
        set_json(dispute_key(dispute.dispute_id), asdict(dispute))
        redis.command("SADD", dispute_ids_key(), dispute.dispute_id)
    except Exception:
        pass


def load_dispute(dispute_id: str) -> Dispute | None:
    stored = _dispute_records.get(dispute_id)
    if stored is not None:
        return stored
    raw = get_json(dispute_key(dispute_id), default=None)
    if not raw:
        return None
    if not isinstance(raw, dict):
        return None
    claim = raw.get("claim_verdict") or "not_proven"
    dispute = Dispute(
        dispute_id=raw.get("dispute_id", ""),
        tenant_id=raw.get("tenant_id", ""),
        scope=_normalize_dispute_scope(str(raw.get("scope", ""))),
        claim_id=raw.get("claim_id", ""),
        actor_id=raw.get("actor_id", ""),
        claim_verdict=str(claim),
        claim_evidence_count=int(raw.get("claim_evidence_count", 0) or 0),
        risk=raw.get("risk", "high"),
        decision=_normalize_dispute_decision(str(raw.get("decision", ""))),
        status=_normalize_dispute_status(str(raw.get("status", ""))),
        reason=raw.get("reason", ""),
        next_action=raw.get("next_action", "independent_reviewer"),
        created_at=raw.get("created_at", utc_now()),
        updated_at=raw.get("updated_at", utc_now()),
        events=raw.get("events", []) if isinstance(raw.get("events"), list) else [],
    )
    _dispute_records[dispute_id] = dispute
    return dispute


def list_disputes(tenant_id: str | None = None, scope: str | None = None) -> list[dict[str, Any]]:
    result = []
    normalized_scope = _normalize_dispute_scope(scope) if scope else None
    for dispute_id in redis.command("SMEMBERS", dispute_ids_key()) or []:
        dispute = load_dispute(dispute_id)
        if not dispute:
            continue
        if tenant_id and dispute.tenant_id != tenant_id:
            continue
        if normalized_scope and dispute.scope != normalized_scope:
            continue
        result.append(asdict(dispute))
    result.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return result


def create_claim(task_id: str, made_by: str, claim_text: str, scope: str) -> Claim:
    c = Claim(claim_id=_id("C"), task_id=task_id, made_by=made_by, claim=claim_text, scope=scope)
    save_claim(c)
    return c


def add_evidence(claim_id: str, ev_type: str, source: str, summary: str = "", path: str = "") -> Evidence:
    e = Evidence(evidence_id=_id("E"), claim_id=claim_id, type=ev_type, source=source, summary=summary, path=path)
    save_evidence(e)
    c = _truth_claims.get(claim_id)
    if c:
        c.evidence.append(e.evidence_id)
        if c.status == "proposed":
            c.status = "challenged"
        save_claim(c)
    return e


def set_verdict(claim_id: str, verdict: VerdictType, confidence: ConfidenceLevel,
                reasoning: str = "", next_action: str = "", owner_summary: str = "") -> Verdict:
    v = Verdict(verdict_id=_id("V"), claim_id=claim_id, verdict=verdict, confidence=confidence,
                reasoning=reasoning, next_action=next_action, owner_summary=owner_summary)
    save_verdict(v)
    c = _truth_claims.get(claim_id)
    if c:
        c.verdict = verdict
        c.confidence = confidence
        status_map = {"true": "verified", "false": "rejected", "partial": "partial",
                      "not_proven": "not_proven", "blocked": "not_proven",
                      "stale": "not_proven", "degraded": "partial"}
        c.status = status_map.get(verdict, c.status)
        save_claim(c)
    return v


def require_evidence_for_truth(claim_id: str) -> bool:
    c = _truth_claims.get(claim_id)
    return bool(c and c.evidence)


def reject_generic_completion(claim_id: str) -> bool:
    c = _truth_claims.get(claim_id)
    if not c:
        return False
    ev_list = [_truth_evidence[eid] for eid in c.evidence if eid in _truth_evidence]
    has_artifact = any(e.type == "artifact" for e in ev_list)
    has_api = any(e.type == "api_response" for e in ev_list)
    return has_artifact or has_api


def get_claims_for_task(task_id: str) -> list[dict]:
    return [asdict(c) for c in _truth_claims.values() if c.task_id == task_id]


def get_truth_summary() -> dict:
    from collections import Counter
    status_counts = Counter(c.status for c in _truth_claims.values())
    verdict_counts = Counter(v.verdict for v in _truth_verdicts.values())
    return {
        "total_claims": len(_truth_claims),
        "total_evidence": len(_truth_evidence),
        "total_verdicts": len(_truth_verdicts),
        "claim_statuses": dict(status_counts),
        "verdict_types": dict(verdict_counts),
    }


# ── Truth Gate: automatic verification on task completion ──────────────

def truth_gate_on_complete(task: dict, result: dict) -> dict:
    """Run truth gate when task completes. Returns gate result."""
    task_id = task.get("task_id", "unknown")
    envelope = task.get("envelope", {})

    # Create claim: task completed
    claim = create_claim(task_id, task.get("lease_owner", "agent"), f"Task {task_id} completed", "task")

    # Check evidence requirements
    has_result = bool(result)
    has_artifact_ref = bool(task.get("result_reference"))
    has_content = bool(result.get("status") and result["status"] != "generic_completion")

    # Add evidence
    if has_result:
        add_evidence(claim.claim_id, "api_response", "POST /v1/tasks/complete", "200 OK")
    if has_artifact_ref:
        add_evidence(claim.claim_id, "artifact", task["result_reference"], "artifact reference present")
    if has_content:
        add_evidence(claim.claim_id, "result_content", "task result", "non-generic content")

    # Set verdict
    evidence_count = len(claim.evidence)
    if evidence_count >= 2 and has_content:
        verdict = "true"
        confidence = "high"
        reasoning = "Task completed with artifact and non-generic content"
    elif evidence_count >= 1:
        verdict = "partial"
        confidence = "medium"
        reasoning = "Task completed but limited evidence"
    else:
        verdict = "not_proven"
        confidence = "low"
        reasoning = "Task completed without verifiable evidence"

    v = set_verdict(claim.claim_id, verdict, confidence, reasoning)

    # Update task with truth gate result
    task["truth_gate"] = {
        "claim_id": claim.claim_id,
        "verdict": v.verdict,
        "confidence": v.confidence,
        "evidence_count": evidence_count,
    }
    return task


def truth_gate_on_fail(task: dict, error_type: str, error: str) -> dict:
    """Run truth gate when task fails. Logs contradiction."""
    task_id = task.get("task_id", "unknown")

    # Create claim: task failed
    claim = create_claim(task_id, task.get("lease_owner", "agent"), f"Task {task_id} failed: {error_type}", "task")

    # Add evidence of failure
    add_evidence(claim.claim_id, "error_record", f"error_type={error_type}", error[:200])

    # Set verdict
    set_verdict(claim.claim_id, "false", "high", f"Task failed: {error_type} - {error[:100]}")

    task["truth_gate"] = {
        "claim_id": claim.claim_id,
        "verdict": "false",
        "confidence": "high",
        "error_type": error_type,
    }
    return task


# ── Redis helpers ──────────────────────────────────────────────────────

def get_json(redis_key: str, default: Any = None) -> Any:
    raw = redis.command("GET", redis_key)
    if raw is None:
        return default
    return json.loads(raw)


def get_json_many(redis_keys: list[str]) -> list[Any]:
    """Fetch a Redis collection in one round trip.

    Fleet endpoints used to open two Redis connections per node. With hundreds
    of historical cards and 21 workers polling leases, that amplified a normal
    status request into Control Plane timeouts.
    """
    if not redis_keys:
        return []
    values = redis.command("MGET", *redis_keys) or []
    return [json.loads(value) if value is not None else None for value in values]


def set_json(redis_key: str, value: Any) -> None:
    redis.command("SET", redis_key, json.dumps(value, sort_keys=True, separators=(",", ":")))


def task_key(task_id: str) -> str:
    return key(f"task:{task_id}")


def node_key(node_id: str) -> str:
    return key(f"node:{node_id}")


def drain_key(node_id: str) -> str:
    return key(f"drain:{node_id}")


def classify_node_freshness(node: dict[str, Any], current: float | None = None) -> dict[str, Any]:
    current_ts = now_ts() if current is None else current
    heartbeat_ts = parse_iso_ts(node.get("heartbeat_at"))
    observed_health = str(node.get("health") or "unknown")
    classified = dict(node)
    classified["reported_health"] = observed_health
    if heartbeat_ts is None:
        freshness = "stale"
        heartbeat_age = None
    else:
        heartbeat_age = max(0, int(current_ts - heartbeat_ts))
        if heartbeat_age > NODE_STALE_AFTER:
            freshness = "stale"
        elif heartbeat_age > NODE_DEGRADED_AFTER:
            freshness = "degraded"
        else:
            freshness = "fresh"
    classified["freshness"] = freshness
    classified["heartbeat_age_seconds"] = heartbeat_age
    if freshness == "fresh":
        classified["health"] = observed_health
    else:
        classified["health"] = freshness
    return classified


def node_health_counts(nodes: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"fresh": 0, "degraded": 0, "stale": 0, "online": 0, "total": len(nodes)}
    for node in nodes:
        freshness = node.get("freshness") or "stale"
        if freshness in {"fresh", "degraded", "stale"}:
            counts[freshness] += 1
        if node.get("health") == "online":
            counts["online"] += 1
    return counts


def all_task_ids() -> list[str]:
    values = redis.command("SMEMBERS", key("task_ids")) or []
    return sorted(values)


def registered_nodes() -> list[dict[str, Any]]:
    node_ids = sorted(redis.command("SMEMBERS", key("node_ids")) or [])
    raw_nodes = get_json_many([node_key(node_id) for node_id in node_ids])
    drains = redis.command("MGET", *[drain_key(node_id) for node_id in node_ids]) if node_ids else []
    current = now_ts()
    nodes = []
    for node_id, raw_node, draining in zip(node_ids, raw_nodes, drains):
        node = raw_node or {"node_id": node_id}
        node["draining"] = bool(draining)
        node = refresh_node_effective_state(node, current)
        nodes.append(classify_node_freshness(node, current))
    return nodes


def queue_ids() -> list[str]:
    return redis.command("LRANGE", key("queue"), 0, -1) or []


def load_task(task_id: str) -> dict[str, Any] | None:
    return get_json(task_key(task_id))


def canonical_response_envelope(
    *,
    status: str,
    task_id: str | None = None,
    trace_id: str | None = None,
    node: str | None = None,
    route_used: str | None = None,
    fallback_nodes: list[str] | None = None,
    artifacts: list[Any] | None = None,
    blocked_reason: str | None = None,
    repair_task: Any = None,
    next_action: str | None = None,
    data: Any = None,
) -> dict[str, Any]:
    if status not in CANONICAL_RESPONSE_STATUSES:
        status = "failed"
        blocked_reason = blocked_reason or "unknown"
    return {
        "task_id": task_id or "",
        "trace_id": trace_id or task_id or "",
        "status": status,
        "node": node or "home",
        "route_used": route_used or "protected_fabric_api",
        "fallback_nodes": fallback_nodes or [],
        "artifacts": artifacts or [],
        "blocked_reason": blocked_reason or "",
        "repair_task": repair_task or "",
        "next_action": next_action or "",
        "data": data or {},
    }


def task_envelope_from_request(body: dict[str, Any], default_kind: str = "owner_remote_task") -> dict[str, Any]:
    envelope = dict(body)
    envelope.setdefault("kind", default_kind)
    envelope.setdefault("source", "fabric_api")
    envelope.setdefault("command_node", body.get("command_node") or body.get("source") or "home")
    envelope.setdefault("requested_role", "remote_agent")
    envelope.setdefault("fallback_allowed", True)
    envelope.setdefault("write_scope", [])
    envelope.setdefault("constraints", {})
    return envelope


def fleet_capabilities(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    by_capability: dict[str, list[str]] = {}
    for node in nodes:
        for capability in node.get("capabilities") or []:
            by_capability.setdefault(capability, []).append(node["node_id"])
    return {"capabilities": by_capability, "nodes": nodes}


def fleet_topology(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    edges = []
    for node in nodes:
        node_id = node.get("node_id")
        if not node_id or node_id == "home":
            continue
        edges.append({"from": "home", "to": node_id, "type": "protected_fabric_api"})
    return {
        "nodes": nodes,
        "edges": edges,
        "relay_endpoint": "/v1/fabric/relay",
    }


def manifest_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    manifest_items = []
    for node in nodes:
        node_id = node.get("node_id")
        if not node_id:
            continue
        node_id = str(node_id)
        manifest_items.append({
            "node_id": node_id,
            "display_name": node.get("display_name", node.get("hostname") or node_id),
            "role": node.get("role", "control"),
            "api_paths": node.get("api_paths", ["fabric_api", "fallback_relay"]),
            "health": node.get("health"),
            "freshness": node.get("freshness"),
            "heartbeat_at": node.get("heartbeat_at"),
            "capabilities": node.get("capabilities", []),
            "base_capabilities": node.get("base_capabilities", []),
            "agent_slots": node.get("agent_slots", {}),
            "agent_id": node.get("agent_id"),
            "runners": node.get("runners", {}),
            "draining": node.get("draining"),
            "management_path": node.get("management_path", "protected_fabric_api"),
            "fallback_api_relay": node.get("fallback_api_relay", "/v1/fabric/relay"),
        })
    return manifest_items


def fabric_manifest_payload(nodes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    catalog = nodes if nodes is not None else fabric_nodes(registered_nodes())
    return {
        "manifest_version": FABRIC_MANIFEST_VERSION,
        "generated_at": utc_now(),
        "primary_control_node": "home",
        "source": "fabric_control_plane",
        "management_path": "protected_fabric_api",
        "bootstrap_policy": {
            "safe_stub": True,
            "ssh_policy": "emergency_bootstrap_diagnostic_only",
            "required_fields": BOOTSTRAP_CONTRACT["required_fields"],
        },
        "nodes": manifest_nodes(catalog),
        "topology": fleet_topology(catalog),
    }


def model_stub_envelope(body: dict[str, Any], *, endpoint: str) -> dict[str, Any]:
    task_id = body.get("task_id") or body.get("id") or ""
    trace_id = body.get("trace_id") or task_id
    return canonical_response_envelope(
        status="blocked",
        task_id=task_id,
        trace_id=trace_id,
        node=body.get("target_node") or "model-node",
        route_used=endpoint,
        fallback_nodes=["9fts", "uiap"],
        blocked_reason="model_runtime_unavailable",
        repair_task={
            "kind": "repair_model_runtime_route",
            "endpoint": endpoint,
            "action": "authenticate a model node route before enabling responses or chat completions",
        },
        next_action="submit work through /v1/agents/tasks or retry after model-node registration",
    )


def model_runtime_blocked_envelope(
    body: dict[str, Any],
    *,
    endpoint: str,
    blocked_reason: str,
    detail: str | None = None,
) -> dict[str, Any]:
    task_id = body.get("task_id") or body.get("id") or ""
    return canonical_response_envelope(
        status="blocked",
        task_id=task_id,
        trace_id=body.get("trace_id") or task_id,
        node=body.get("target_node") or "model-node",
        route_used=endpoint,
        fallback_nodes=["9fts", "uiap", "qjns"],
        blocked_reason=blocked_reason,
        repair_task={
            "kind": "repair_model_runtime_route",
            "endpoint": endpoint,
            "action": "verify model runtime base list, credentials and route budget",
            "detail": detail,
        },
        next_action="verify provider route budget and retry",
    )


def admin_denied_envelope(body: dict[str, Any], *, endpoint: str) -> dict[str, Any]:
    task_id = body.get("task_id") or ""
    trace_id = body.get("trace_id") or task_id
    return canonical_response_envelope(
        status="blocked",
        task_id=task_id,
        trace_id=trace_id,
        node=body.get("target_node") or "home",
        route_used=endpoint,
        blocked_reason="admin_scope_denied",
        repair_task={
            "kind": "request_admin_scope",
            "endpoint": endpoint,
            "action": "obtain authenticated owner scope and audited approval before privileged execution",
        },
        next_action="resubmit with an authenticated admin capability token through the protected Fabric API",
    )


def os_capabilities_envelope() -> dict[str, Any]:
    return canonical_response_envelope(
        status="completed",
        route_used="/v1/os/capabilities",
        data={"object": "list", "data": OS_CAPABILITY_CATALOG},
        next_action="invoke an allowed capability through /v1/os/capabilities/invoke",
    )


def os_capability_invoke_envelope(body: dict[str, Any], *, endpoint: str = "/v1/os/capabilities/invoke") -> dict[str, Any]:
    capability_id = str(body.get("capabilityId") or body.get("capability_id") or "")
    capability = OS_CAPABILITY_BY_ID.get(capability_id)
    trace_id = body.get("trace_id") or body.get("sourceIntentId") or body.get("source_intent_id") or capability_id
    if not capability:
        return canonical_response_envelope(
            status="blocked",
            trace_id=trace_id,
            route_used=endpoint,
            blocked_reason="unknown",
            repair_task={"kind": "register_os_capability", "capability_id": capability_id},
            next_action="declare the capability in OS_CAPABILITY_CATALOG before invocation",
        )
    if capability["approval"] != "auto":
        return canonical_response_envelope(
            status="blocked",
            trace_id=trace_id,
            node=capability["target"],
            route_used=endpoint,
            blocked_reason="admin_scope_denied" if capability["approval"] == "explicit" else "auth_failed",
            repair_task={
                "kind": "request_capability_approval",
                "capability_id": capability_id,
                "approval": capability["approval"],
                "target": capability["target"],
            },
            next_action="request owner approval before creating control-plane work",
            data={"capability": capability, "input": body.get("input") or {}},
        )
    return canonical_response_envelope(
        status="completed",
        trace_id=trace_id,
        node=capability["target"],
        route_used=endpoint,
        data={"capability": capability, "input": body.get("input") or {}, "accepted": True},
        next_action="stream shell/core events back to the avatar surface",
    )


def task_artifact_envelope(task: dict[str, Any] | None, task_id: str) -> dict[str, Any]:
    if not task:
        return canonical_response_envelope(
            status="blocked",
            task_id=task_id,
            blocked_reason="unknown",
            repair_task={"kind": "locate_task_artifacts", "task_id": task_id},
            next_action="verify task_id and retry artifact lookup",
        )
    result = task.get("result") or {}
    artifacts = []
    for key_name in ("result_path", "artifact_path", "artifact_paths", "artifacts"):
        value = result.get(key_name) or task.get(key_name)
        if not value:
            continue
        if isinstance(value, list):
            artifacts.extend(value)
        else:
            artifacts.append(value)
    return canonical_response_envelope(
        status="completed" if artifacts else "partial",
        task_id=task_id,
        node=(task.get("lease_owner") or "home").split(":", 1)[0],
        artifacts=artifacts,
        data={"task_state": task.get("state"), "result_reference": task.get("result_reference")},
        next_action="collect listed artifact paths from the authenticated artifact API" if artifacts else "wait for task completion or annotate result artifacts",
    )


def fabric_blocked_envelope(
    *,
    reason: str,
    target_node: str | None,
    fallback_nodes: list[str] | None = None,
    repair_task: dict[str, Any] | None = None,
    route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason": reason,
        "target_node": target_node,
        "fallback_nodes": fallback_nodes or [],
        "fallback_route": route or {"type": "fabric_relay", "endpoint": "/v1/fabric/relay"},
        "repair_task": repair_task or {
            "kind": "repair_fabric_route",
            "target_node": target_node,
            "action": "restore node heartbeat or register an API relay before retrying direct control",
        },
        "can_continue_elsewhere": bool(fallback_nodes),
    }


def _node_online(node: dict[str, Any]) -> bool:
    return node.get("health") == "online"


def fabric_nodes(registered_nodes: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    merged = {node_id: dict(node) for node_id, node in FABRIC_NODE_CATALOG.items()}
    for registered in registered_nodes or []:
        node_id = str(registered.get("node_id") or registered.get("id") or "")
        if not node_id:
            continue
        catalog = merged.get(node_id, {"node_id": node_id, "api_paths": ["fabric_api", "fallback_relay"], "ssh": "emergency_bootstrap_diagnostic_only"})
        catalog.update(registered)
        catalog.setdefault("display_name", registered.get("hostname") or node_id)
        catalog.setdefault("api_paths", ["fabric_api", "fallback_relay"])
        catalog["ssh"] = "emergency_bootstrap_diagnostic_only"
        merged[node_id] = catalog
    for node in merged.values():
        node.setdefault("health", "unknown")
        node.setdefault("fallback_api_relay", "/v1/fabric/relay")
        node.setdefault("management_path", "protected_fabric_api")
    return sorted(merged.values(), key=lambda item: item["node_id"])


def fabric_route(
    *,
    target_node: str | None = None,
    required_capability: str | None = None,
    registered_nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    nodes = fabric_nodes(registered_nodes)
    online = [node for node in nodes if _node_online(node)]
    candidates = nodes
    if target_node:
        candidates = [node for node in candidates if node.get("node_id") == target_node]
    if required_capability:
        candidates = [node for node in candidates if required_capability in (node.get("capabilities") or [])]
    direct = next((node for node in candidates if _node_online(node)), None)
    fallback_nodes = [
        node["node_id"]
        for node in online
        if node.get("node_id") != target_node
        and (not required_capability or required_capability in (node.get("capabilities") or []))
    ]
    if direct:
        return {
            "status": "ok",
            "route": {
                "type": "direct_fabric_api",
                "target_node": direct["node_id"],
                "endpoint": f"/v1/nodes/{direct['node_id']}",
                "relay_endpoint": "/v1/fabric/relay",
            },
            "fallback_nodes": fallback_nodes,
            "can_continue_elsewhere": True,
        }
    reason = "target_node_unavailable" if target_node else "no_node_matches_capability"
    return fabric_blocked_envelope(
        reason=reason,
        target_node=target_node,
        fallback_nodes=fallback_nodes,
        repair_task={
            "kind": "repair_fabric_route",
            "target_node": target_node,
            "required_capability": required_capability,
            "action": "register node heartbeat, clear drain state, or choose a fallback node via Fabric API",
        },
    )


def bootstrap_node_contract(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    required = set(BOOTSTRAP_CONTRACT["required_fields"])
    missing = sorted(field for field in required if not body.get(field))
    if missing:
        return 400, {
            "status": "blocked",
            "reason": "bootstrap_contract_missing_fields",
            "missing_fields": missing,
            "fallback_nodes": [],
            "repair_task": {
                "kind": "repair_bootstrap_request",
                "action": "resubmit bootstrap request with required non-secret identity and capability fields",
            },
            "can_continue_elsewhere": False,
        }

    node_id = str(body["node_id"])
    node = get_json(node_key(node_id), {
        "node_id": node_id,
        "health": "stale",
        "freshness": "stale",
        "capabilities": [],
    })
    node["node_id"] = node_id
    node["display_name"] = body.get("display_name") or body.get("hostname") or node.get("display_name")
    node["role"] = body.get("role")
    node["capabilities"] = body.get("capabilities", node.get("capabilities", []))
    node["ip"] = body.get("ip") or body.get("hostname")
    node["public_ip"] = body.get("public_ip")
    node["api_paths"] = node.get("api_paths", ["fabric_api", "fallback_relay"])
    node["bootstrap_state"] = "pending_identity_approval"
    node["requested_by"] = body.get("requested_by")
    node["requested_at"] = node.get("requested_at") or utc_now()
    node["bootstrap_contract_version"] = BOOTSTRAP_CONTRACT["endpoint"]

    set_json(node_key(node_id), node)
    redis.command("SADD", key("node_ids"), node_id)
    manifest = fabric_manifest_payload(fabric_nodes(registered_nodes() + [{"node_id": node_id}]))
    return 202, {
        "status": "accepted",
        "bootstrap": "safe_stub",
        "node_id": body["node_id"],
        "display_name": body.get("display_name"),
        "capabilities": body.get("capabilities", []),
        "node": node,
        "manifest": {
            "version": manifest["manifest_version"],
            "generated_at": manifest["generated_at"],
            "primary_control_node": manifest["primary_control_node"],
        },
        "next_action": "approve scoped credentials through authenticated Fabric API and start agent-host registration",
        "secrets_returned": False,
    }


def save_task(task: dict[str, Any]) -> None:
    task["updated_at"] = utc_now()
    set_json(task_key(task["task_id"]), task)
    redis.command("SADD", key("task_ids"), task["task_id"])
    if task.get("state") in ACTIVE_LEASE_STATES:
        redis.command("SADD", key("active_lease_ids"), task["task_id"])
    else:
        redis.command("SREM", key("active_lease_ids"), task["task_id"])


def assignment_key(assignment_id: str) -> str:
    return key(f"assignment:{assignment_id}")


def assignment_ids_key() -> str:
    return key("assignment_ids")


def assignment_task_index_key(task_id: str) -> str:
    return key(f"assignment_task:{task_id}")


def assignment_status_event_ids_key(assignment_id: str) -> str:
    return key(f"assignment_status_events:{assignment_id}")


def assignment_status_event_key(event_id: str) -> str:
    return key(f"assignment_status_event:{event_id}")


def assignment_status_event_global_ids_key() -> str:
    return key("assignment_status_event_ids")


def a2a_agent_card_key(agent_card_id: str) -> str:
    return key(f"a2a_agent_card:{agent_card_id}")


def a2a_agent_card_active_assignments_key(
    agent_card_id: str,
) -> str:
    return key(f"a2a_agent_card_active_assignments:{agent_card_id}")


def a2a_runtime_profile_agent_card_key(
    runtime_profile: str,
) -> str:
    digest = hashlib.sha256(
        _concrete_developer_runtime_profile(
            runtime_profile,
        ).encode("utf-8"),
    ).hexdigest()
    return key(f"a2a_runtime_profile_agent_card:{digest}")


def a2a_agent_card_ids_key() -> str:
    return key("a2a_agent_card_ids")


def a2a_agent_cards_by_scope_key(scope: str) -> str:
    return key(f"a2a_agent_cards:{scope}")


def a2a_message_id_key(a2a_message_id: str) -> str:
    return key(f"a2a_message:{a2a_message_id}")


def a2a_cursor_key(tenant_id: str, channel_id: str) -> str:
    return key(f"a2a_cursor:{tenant_id}:{channel_id}")


def a2a_channel_messages_key(tenant_id: str, channel_id: str) -> str:
    return key(f"a2a_messages:{tenant_id}:{channel_id}")


def _canonical_a2a_content(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": message["tenant_id"],
        "goal_id": message["goal_id"],
        "case_id": message["case_id"],
        "task_id": message["task_id"],
        "task_version": message["task_version"],
        "channel_id": message["channel_id"],
        "sequence": message["sequence"],
        "previous_message_id": message["previous_message_id"],
        "sender_actor_id": message["sender_actor_id"],
        "sender_assignment_id": message["sender_assignment_id"],
        "recipient_assignment_ids": message["recipient_assignment_ids"],
        "recipient_capability": message["recipient_capability"],
        "message_type": message["message_type"],
        "purpose": message["purpose"],
        "response_to_message_id": message["response_to_message_id"],
        "content": message["content"],
    }


def a2a_content_hash(message: dict[str, Any]) -> str:
    payload = json.dumps(
        _canonical_a2a_content(message),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def canonical_a2a_content(message: dict[str, Any]) -> dict[str, Any]:
    return _canonical_a2a_content(message)


def load_assignment(assignment_id: str) -> dict[str, Any] | None:
    return get_json(assignment_key(assignment_id))


def _json_record(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _write_assignment_registry(
    assignment: dict[str, Any],
    *,
    mode: str,
    expected_raw: str | None,
) -> tuple[str, dict[str, Any] | None]:
    assignment_id = str(assignment.get("assignment_id") or "")
    if not assignment_id:
        raise ValueError("assignment_id required")
    task_id = str(assignment.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("task_id required")
    existing = (
        json.loads(expected_raw)
        if expected_raw not in {None, "__kolibri_missing__"}
        else None
    )
    old_task_id = str((existing or {}).get("task_id") or task_id).strip()
    assignment_json = _json_record(assignment)
    reply = redis.command(
        "EVAL",
        ASSIGNMENT_REGISTRY_WRITE_LUA,
        4,
        assignment_key(assignment_id),
        assignment_ids_key(),
        assignment_task_index_key(task_id),
        assignment_task_index_key(old_task_id),
        assignment_json,
        assignment_id,
        task_id,
        expected_raw or "__kolibri_missing__",
        mode,
    )
    outcome = str(reply[0])
    stored = json.loads(reply[1]) if len(reply) > 1 and reply[1] else None
    return outcome, stored


def save_assignment(assignment: dict[str, Any]) -> None:
    assignment_id = str(assignment.get("assignment_id") or "")
    if not assignment_id:
        raise ValueError("assignment_id required")
    for _ in range(5):
        expected_raw = redis.command("GET", assignment_key(assignment_id))
        outcome, _stored = _write_assignment_registry(
            assignment,
            mode="cas",
            expected_raw=expected_raw,
        )
        if outcome == "committed":
            return
        if outcome != "stale":
            raise RuntimeError(f"assignment_registry_write_failed:{outcome}")
    raise RuntimeError("assignment_registry_write_conflict")


def create_assignment_atomically(
    assignment: dict[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    return _write_assignment_registry(
        assignment,
        mode="create",
        expected_raw=None,
    )


def list_assignment_ids(task_id: str | None = None) -> list[str]:
    if task_id:
        return sorted(redis.command("SMEMBERS", assignment_task_index_key(task_id)) or [])
    return sorted(redis.command("SMEMBERS", assignment_ids_key()) or [])


def load_a2a_agent_card(agent_card_id: str) -> dict[str, Any] | None:
    return get_json(a2a_agent_card_key(agent_card_id))


def _write_a2a_agent_card_registry(
    agent_card: dict[str, Any],
    *,
    mode: str,
    expected_raw: str | None,
) -> tuple[str, dict[str, Any] | None]:
    card_id = str(agent_card.get("agent_card_id") or "").strip()
    if not card_id:
        raise ValueError("agent_card_id required")
    scope = str(agent_card.get("tenant_scope") or "").strip() or "platform"
    existing = (
        json.loads(expected_raw)
        if expected_raw not in {None, "__kolibri_missing__"}
        else None
    )
    old_scope = str((existing or {}).get("tenant_scope") or scope).strip()
    card_json = _json_record(agent_card)
    reply = redis.command(
        "EVAL",
        A2A_AGENT_CARD_REGISTRY_WRITE_LUA,
        4,
        a2a_agent_card_key(card_id),
        a2a_agent_card_ids_key(),
        a2a_agent_cards_by_scope_key(scope),
        a2a_agent_cards_by_scope_key(old_scope),
        card_json,
        card_id,
        scope,
        expected_raw or "__kolibri_missing__",
        mode,
    )
    outcome = str(reply[0])
    stored = json.loads(reply[1]) if len(reply) > 1 and reply[1] else None
    return outcome, stored


def save_a2a_agent_card(agent_card: dict[str, Any]) -> None:
    card_id = str(agent_card.get("agent_card_id") or "").strip()
    if not card_id:
        raise ValueError("agent_card_id required")
    for _ in range(5):
        expected_raw = redis.command("GET", a2a_agent_card_key(card_id))
        outcome, _stored = _write_a2a_agent_card_registry(
            agent_card,
            mode="cas",
            expected_raw=expected_raw,
        )
        if outcome == "committed":
            return
        if outcome != "stale":
            raise RuntimeError(f"a2a_agent_card_registry_write_failed:{outcome}")
    raise RuntimeError("a2a_agent_card_registry_write_conflict")


def create_a2a_agent_card_atomically(
    agent_card: dict[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    return _write_a2a_agent_card_registry(
        agent_card,
        mode="create",
        expected_raw=None,
    )


def load_a2a_cursor(tenant_id: str, channel_id: str) -> dict[str, Any]:
    stored = get_json(a2a_cursor_key(tenant_id, channel_id))
    if stored is not None:
        if all(
            key_name in stored
            for key_name in (
                "schema_id",
                "schema_version",
                "tenant_id",
                "channel_id",
                "last_sequence",
                "last_message_id",
                "accepted_messages",
                "deduplication_index",
            )
        ):
            return stored
    return {
        "schema_id": "kolibri.a2a.delivery_cursor",
        "schema_version": "1.0",
        "tenant_id": tenant_id,
        "channel_id": channel_id,
        "last_sequence": 0,
        "last_message_id": None,
        "accepted_messages": {},
        "deduplication_index": {},
    }


def save_a2a_cursor(cursor: dict[str, Any]) -> None:
    if not isinstance(cursor, dict):
        raise ValueError("cursor must be dict")
    tenant_id = str(cursor.get("tenant_id") or "").strip()
    channel_id = str(cursor.get("channel_id") or "").strip()
    if not tenant_id or not channel_id:
        raise ValueError("tenant_id and channel_id required")
    set_json(a2a_cursor_key(tenant_id, channel_id), cursor)


def load_a2a_messages(tenant_id: str, channel_id: str) -> list[str]:
    return redis.command("LRANGE", a2a_channel_messages_key(tenant_id, channel_id), 0, -1) or []


def parse_declared_a2a_message_v1(container: dict[str, Any]) -> dict[str, Any]:
    candidate = container.get("payload") if "payload" in container else container
    if not isinstance(candidate, dict):
        raise DeclaredContractV1Error(
            "invalid_a2a_message",
            [{"path": "/payload", "code": "type"}],
        )
    result = HOME_CONTRACTS_V1.validate_inbound(
        candidate,
        "kolibri.a2a.message_appended.event",
    )
    if not result.ok:
        raise DeclaredContractV1Error(
            result.code or "invalid_a2a_message",
            [
                {"path": violation.path, "code": violation.code}
                for violation in result.violations
            ],
        )
    parsed = HOME_CONTRACTS_V1.prepare_outbound(candidate, "kolibri.a2a.message_appended.event")
    expected_hash = a2a_content_hash(parsed)
    if str(parsed.get("content_hash")) != expected_hash:
        raise DeclaredContractV1Error(
            "invalid_a2a_message",
            [{"path": "/content_hash", "code": "content_hash_mismatch"}],
        )
    violations = validate_a2a_interaction_payload(parsed)
    if violations:
        raise DeclaredContractV1Error("invalid_a2a_message", violations)
    return parsed


def validate_a2a_interaction_payload(message: dict[str, Any]) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    content = message.get("content")
    if not isinstance(content, dict):
        return [{"path": "/content", "code": "typed_content_required"}]

    references = content.get("reference_ids")
    if not isinstance(references, list) or not references:
        violations.append({"path": "/content/reference_ids", "code": "references_required"})

    structured = content.get("structured_data")
    if not isinstance(structured, dict):
        violations.append({"path": "/content/structured_data", "code": "typed_structured_data_required"})
        return violations

    expected_response = structured.get("expected_response")
    status = structured.get("status")
    if not isinstance(expected_response, str) or not expected_response.strip():
        violations.append({"path": "/content/structured_data/expected_response", "code": "expected_response_required"})
    if not isinstance(status, str) or not status.strip():
        violations.append({"path": "/content/structured_data/status", "code": "status_required"})
    return violations


def parse_declared_a2a_agent_card_v1(container: dict[str, Any]) -> dict[str, Any]:
    candidate = container.get("contract_v1") if "contract_v1" in container else container
    if not isinstance(candidate, dict):
        raise DeclaredContractV1Error(
            "invalid_a2a_agent_card",
            [{"path": "/contract_v1" if "contract_v1" in container else "/", "code": "type"}],
        )
    result = HOME_CONTRACTS_V1.validate_inbound(
        candidate,
        "kolibri.agent_card",
    )
    if not result.ok:
        raise DeclaredContractV1Error(
            result.code or "invalid_a2a_agent_card",
            [
                {"path": violation.path, "code": violation.code}
                for violation in result.violations
            ],
        )
    return HOME_CONTRACTS_V1.prepare_outbound(candidate, "kolibri.agent_card")


def parse_declared_a2a_event_v1(container: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(container, dict):
        raise DeclaredContractV1Error(
            "invalid_a2a_event",
            [{"path": "/", "code": "type"}],
        )
    result = HOME_CONTRACTS_V1.validate_inbound(
        container,
        "kolibri.event",
    )
    if not result.ok:
        raise DeclaredContractV1Error(
            result.code or "invalid_a2a_event",
            [
                {"path": violation.path, "code": violation.code}
                for violation in result.violations
            ],
        )
    event = HOME_CONTRACTS_V1.prepare_outbound(container, "kolibri.event")
    violations: list[dict[str, str]] = []
    checks = {
        "/event_name": (event.get("event_name"), "a2a.message_appended"),
        "/payload_schema_id": (event.get("payload_schema_id"), "kolibri.a2a.message_appended.event"),
        "/payload_schema_version": (event.get("payload_schema_version"), "1.0"),
        "/producer_owner": (event.get("producer_owner"), "logical_home_control_plane"),
    }
    for path_value, (actual, expected) in checks.items():
        if actual != expected:
            violations.append({"path": path_value, "code": "incorrect_a2a_event"})
    identity = event.get("identity") if isinstance(event.get("identity"), dict) else {}
    authority = identity.get("authority") if isinstance(identity, dict) else {}
    if not isinstance(authority, dict) or authority.get("authority_role") != "logical_home_control_plane":
        violations.append({"path": "/identity/authority/authority_role", "code": "incorrect_authority_role"})
    if not isinstance(authority.get("capabilities"), list) or "a2a.message.append" not in authority["capabilities"]:
        violations.append({"path": "/identity/authority/capabilities", "code": "required_capability_missing"})

    payload = parse_declared_a2a_message_v1(event)
    bindings = {
        "/payload/tenant_id": (payload["tenant_id"], identity.get("tenant_id")),
        "/payload/goal_id": (payload["goal_id"], (identity.get("subject_refs") or {}).get("goal_id")),
        "/payload/case_id": (payload["case_id"], (identity.get("subject_refs") or {}).get("case_id")),
        "/payload/task_id": (payload["task_id"], (identity.get("subject_refs") or {}).get("task_id")),
        "/payload/sender_actor_id": (payload["sender_actor_id"], (identity.get("actor") or {}).get("actor_id")),
        "/identity/actor/actor_id": ((identity.get("actor") or {}).get("actor_id"), payload["sender_actor_id"]),
    }
    for path_value, (left, right) in bindings.items():
        if left != right:
            violations.append({"path": path_value, "code": "identity_binding_mismatch"})

    aggregate = event.get("aggregate") if isinstance(event.get("aggregate"), dict) else {}
    aggregate_id = aggregate.get("aggregate_id")
    aggregate_version = aggregate.get("aggregate_version")
    if aggregate.get("aggregate_type") != "task" or aggregate_id != payload["task_id"] or aggregate_version != payload["task_version"]:
        violations.append({"path": "/aggregate", "code": "task_aggregate_binding_mismatch"})
    if str(event.get("deduplication_key") or "") != str(payload.get("deduplication_key") or ""):
        violations.append({"path": "/deduplication_key", "code": "deduplication_binding_mismatch"})

    if violations:
        raise DeclaredContractV1Error(
            "invalid_a2a_event",
            violations,
        )
    return event, payload


def parse_declared_a2a_cursor_v1(container: dict[str, Any]) -> dict[str, Any]:
    candidate = container.get("contract_v1") if "contract_v1" in container else container
    if not isinstance(candidate, dict):
        raise DeclaredContractV1Error(
            "invalid_a2a_cursor",
            [{"path": "/cursor", "code": "type"}],
        )
    result = HOME_CONTRACTS_V1.validate_inbound(
        candidate,
        "kolibri.a2a.delivery_cursor",
    )
    if not result.ok:
        raise DeclaredContractV1Error(
            result.code or "invalid_a2a_cursor",
            [
                {"path": violation.path, "code": violation.code}
                for violation in result.violations
            ],
        )
    return HOME_CONTRACTS_V1.prepare_outbound(candidate, "kolibri.a2a.delivery_cursor")


def classify_a2a_delivery(message: dict[str, Any], cursor: dict[str, Any], now: str) -> dict[str, str | None]:
    now_ts_value = parse_iso_ts(now) or now_ts()
    if message.get("tenant_id") != cursor.get("tenant_id") or message.get("channel_id") != cursor.get("channel_id"):
        return {"decision": "rejected_scope", "code": "cursor_scope_mismatch"}
    if parse_iso_ts(message.get("expires_at")) is None:
        return {"decision": "rejected_invalid", "code": "invalid_expiry"}
    if parse_iso_ts(message.get("expires_at")) <= now_ts_value:
        return {"decision": "rejected_expired", "code": "message_expired"}
    accepted = cursor.get("accepted_messages") or {}
    cursor_message = accepted.get(message["a2a_message_id"])
    if cursor_message is not None:
        if cursor_message == message["content_hash"]:
            return {"decision": "duplicate_noop", "code": None}
        return {"decision": "rejected_conflict", "code": "message_id_hash_conflict"}
    dedup = (cursor.get("deduplication_index") or {}).get(message["deduplication_key"])
    if dedup is not None:
        if dedup.get("message_id") == message["a2a_message_id"] and dedup.get("content_hash") == message["content_hash"]:
            return {"decision": "duplicate_noop", "code": None}
        return {"decision": "rejected_conflict", "code": "deduplication_key_conflict"}
    last_sequence = int(cursor.get("last_sequence") or 0)
    if message["sequence"] > last_sequence + 1:
        return {"decision": "deferred_out_of_order", "code": "sequence_gap"}
    if message["sequence"] <= last_sequence:
        return {"decision": "rejected_out_of_order", "code": "unknown_old_sequence"}
    if message["previous_message_id"] != cursor.get("last_message_id"):
        return {"decision": "rejected_out_of_order", "code": "previous_message_mismatch"}
    return {"decision": "accepted", "code": None}


def validate_a2a_sender_recipient_at_owner(
    message: dict[str, Any],
    event: dict[str, Any],
    assignments: list[dict[str, Any]],
    now: str,
) -> tuple[bool, list[dict[str, str]]]:
    now_ts_value = parse_iso_ts(now) or now_ts()
    candidate = {str(assignment.get("assignment_id") or ""): assignment for assignment in assignments if assignment}
    sender_id = str(message["sender_assignment_id"])
    sender = candidate.get(sender_id)
    violations: list[dict[str, str]] = []

    authority = (event.get("identity") or {}).get("authority") or {}
    authority_id = str(authority.get("authority_id") or "")
    authority_epoch = int(authority.get("authority_epoch") or 0)

    def check_scope(assignment: dict[str, Any], expected_path: str) -> bool:
        scope_matches = (
            assignment.get("tenant_id") == message["tenant_id"] and
            assignment.get("goal_id") == message["goal_id"] and
            assignment.get("case_id") == message["case_id"] and
            assignment.get("task_id") == message["task_id"] and
            assignment.get("task_version") == message["task_version"] and
            assignment.get("status") == "active"
        )
        if not scope_matches:
            return False
        if expected_path == "/payload/sender_assignment_id":
            return (
                str(assignment.get("assignee_actor_id") or "")
                == str(message["sender_actor_id"])
            )
        return True

    if sender is None or not check_scope(sender, "/payload/sender_assignment_id"):
        violations.append({"path": "/payload/sender_assignment_id", "code": "sender_assignment_invalid"})
    else:
        if str(sender.get("authority_profile", {}).get("authority_id") or "") != authority_id:
            violations.append({"path": "/payload/sender_assignment_id", "code": "sender_assignment_invalid"})
        elif int(sender.get("authority_profile", {}).get("authority_epoch") or 0) != authority_epoch:
            violations.append({"path": "/payload/sender_assignment_id", "code": "sender_assignment_invalid"})
        elif parse_iso_ts(sender.get("authority_profile", {}).get("expires_at")) is None:
            violations.append({"path": "/payload/sender_assignment_id", "code": "sender_assignment_invalid"})
        elif parse_iso_ts(sender["authority_profile"]["expires_at"]) <= now_ts_value:
            violations.append({"path": "/payload/sender_assignment_id", "code": "sender_assignment_invalid"})
        elif "a2a.message.append" not in (sender.get("authority_profile") or {}).get("capabilities", []):
            violations.append({"path": "/payload/sender_assignment_id", "code": "sender_assignment_invalid"})

    for assignment_id in message["recipient_assignment_ids"]:
        recipient = candidate.get(str(assignment_id))
        if recipient is None:
            violations.append({"path": "/payload/recipient_assignment_ids", "code": "recipient_assignment_invalid"})
            continue
        if not check_scope(recipient, "/payload/recipient_assignment_ids"):
            violations.append({"path": "/payload/recipient_assignment_ids", "code": "recipient_assignment_invalid"})
            continue
        if recipient.get("status") != "active":
            violations.append({"path": "/payload/recipient_assignment_ids", "code": "recipient_assignment_invalid"})
            continue
        if str(recipient.get("authority_profile", {}).get("authority_id") or "") != authority_id:
            violations.append({"path": "/payload/recipient_assignment_ids", "code": "recipient_assignment_invalid"})
            continue
        if int(recipient.get("authority_profile", {}).get("authority_epoch") or 0) != authority_epoch:
            violations.append({"path": "/payload/recipient_assignment_ids", "code": "recipient_assignment_invalid"})
            continue
        expiry = parse_iso_ts(recipient.get("authority_profile", {}).get("expires_at"))
        if expiry is None or expiry <= now_ts_value:
            violations.append({"path": "/payload/recipient_assignment_ids", "code": "recipient_assignment_invalid"})
            continue
        payload_capability = message.get("recipient_capability")
        if payload_capability is not None and payload_capability not in (recipient.get("authority_profile") or {}).get("capabilities", []):
            violations.append({"path": "/payload/recipient_assignment_ids", "code": "recipient_assignment_invalid"})

    if violations:
        return False, violations
    return True, []


def _next_a2a_cursor(
    cursor: dict[str, Any],
    message: dict[str, Any],
) -> dict[str, Any]:
    updated = copy.deepcopy(cursor)
    updated.setdefault("accepted_messages", {})
    updated.setdefault("deduplication_index", {})
    message_id = str(message["a2a_message_id"])
    updated["last_sequence"] = int(message["sequence"])
    updated["last_message_id"] = message_id
    updated["accepted_messages"][message_id] = message["content_hash"]
    updated["deduplication_index"][str(message["deduplication_key"])] = {
        "message_id": message_id,
        "content_hash": message["content_hash"],
    }
    return parse_declared_a2a_cursor_v1(updated)


def append_a2a_message_atomically(
    message: dict[str, Any],
    event: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    tenant_id = str(message["tenant_id"])
    channel_id = str(message["channel_id"])
    message_id = str(message["a2a_message_id"])
    assignment_ids = sorted({
        str(message["sender_assignment_id"]),
        *(
            str(assignment_id)
            for assignment_id in message["recipient_assignment_ids"]
        ),
    })
    record = {
        "schema_id": "kolibri.event",
        "schema_version": "1.0",
        "message_id": event.get("message_id"),
        "message": message,
        "event": event,
    }
    for _ in range(8):
        cursor_key = a2a_cursor_key(tenant_id, channel_id)
        expected_cursor_raw = redis.command("GET", cursor_key)
        cursor = (
            json.loads(expected_cursor_raw)
            if expected_cursor_raw is not None
            else load_a2a_cursor(tenant_id, channel_id)
        )
        classification = classify_a2a_delivery(message, cursor, now)
        if classification["decision"] != "accepted":
            return {
                **classification,
                "cursor": cursor,
            }
        assignment_raws = [
            redis.command("GET", assignment_key(assignment_id))
            for assignment_id in assignment_ids
        ]
        assignments = [
            json.loads(raw)
            for raw in assignment_raws
            if raw is not None
        ]
        valid, violations = validate_a2a_sender_recipient_at_owner(
            message,
            event,
            assignments,
            now,
        )
        if not valid:
            return {
                "decision": "assignment_auth_rejected",
                "code": "assignment_auth_rejected",
                "violations": violations,
                "cursor": cursor,
            }
        next_cursor = _next_a2a_cursor(cursor, message)
        keys = [
            cursor_key,
            a2a_message_id_key(message_id),
            a2a_channel_messages_key(tenant_id, channel_id),
            assignment_task_index_key(message["task_id"]),
            *(
                assignment_key(assignment_id)
                for assignment_id in assignment_ids
            ),
        ]
        assignment_args: list[str] = []
        for assignment_id, raw in zip(
            assignment_ids,
            assignment_raws,
            strict=True,
        ):
            assignment_args.extend([
                assignment_id,
                raw or "__kolibri_missing__",
            ])
        reply = redis.command(
            "EVAL",
            A2A_MESSAGE_APPEND_LUA,
            len(keys),
            *keys,
            expected_cursor_raw or "__kolibri_missing__",
            _json_record(next_cursor),
            _json_record(record),
            message_id,
            *assignment_args,
        )
        outcome = str(reply[0])
        if outcome == "committed":
            return {
                "decision": "accepted",
                "code": None,
                "cursor": json.loads(reply[1]),
            }
        if outcome == "message_record_conflict":
            return {
                "decision": "rejected_conflict",
                "code": "message_id_hash_conflict",
                "cursor": cursor,
            }
        if outcome not in {
            "stale_cursor",
            "stale_assignment",
            "stale_assignment_index",
        }:
            raise RuntimeError(f"a2a_message_append_failed:{outcome}")
    raise RuntimeError("a2a_message_concurrent_update_retry_exhausted")


def a2a_agent_card_ids() -> list[str]:
    return sorted(redis.command("SMEMBERS", a2a_agent_card_ids_key()) or [])


def a2a_agent_cards_by_scope(scope: str) -> list[str]:
    return sorted(redis.command("SMEMBERS", a2a_agent_cards_by_scope_key(scope)) or [])


def a2a_scope_candidates() -> set[str]:
    return set(a2a_agent_card_ids())


def parse_declared_assignment_v1(container: dict[str, Any]) -> dict[str, Any]:
    candidate = container.get("contract_v1") if "contract_v1" in container else container
    if not isinstance(candidate, dict):
        raise DeclaredContractV1Error(
            "invalid_assignment",
            [{"path": "/contract_v1", "code": "type"}],
        )
    result = HOME_CONTRACTS_V1.validate_inbound(
        candidate,
        "kolibri.agent_assignment",
    )
    if not result.ok:
        raise DeclaredContractV1Error(
            result.code or "invalid_assignment",
            [
                {"path": violation.path, "code": violation.code}
                for violation in result.violations
            ],
        )
    return HOME_CONTRACTS_V1.prepare_outbound(candidate, "kolibri.agent_assignment")


def _assignment_status_event(
    *,
    previous: dict[str, Any],
    updated: dict[str, Any],
    reason: str,
    audit_context: dict[str, Any] | None,
) -> dict[str, Any]:
    assignment_id = str(updated["assignment_id"])
    status = str(updated["status"])
    version = int(updated["version"])
    event_seed = (
        f"{assignment_id}\0{version}\0{status}".encode("utf-8")
    )
    event_digest = hashlib.sha256(event_seed).hexdigest()
    event_id = f"evt_{event_digest}"
    authority_profile = updated.get("authority_profile") or {}
    if audit_context is not None:
        actor = copy.deepcopy(audit_context["actor"])
        user_id = audit_context.get("user_id")
        authority = copy.deepcopy(audit_context["authority"])
        causation_id = str(
            audit_context.get("transport_message_id") or event_id,
        )
    else:
        configured_authority = logical_home_server_authority_grant()
        actor = {
            "actor_id": str(updated["assignee_actor_id"]),
            "actor_type": "system",
        }
        user_id = None
        authority = {
            "authority_id": str(
                authority_profile.get("authority_id")
                or configured_authority.get("authority_id")
                or "auth_logical_home",
            ),
            "authority_role": "logical_home_control_plane",
            "authority_epoch": int(
                authority_profile.get("authority_epoch")
                or configured_authority.get("authority_epoch")
                or 1,
            ),
            "authority_placement_id": str(
                configured_authority.get("authority_placement_id")
                or "placement_logical_home",
            ),
            "authorization_decision_id": str(
                authority_profile.get("authorization_decision_id")
                or configured_authority.get("authorization_decision_id")
                or "decision_assignment_transition",
            ),
            "capabilities": normalized_string_list(
                authority_profile.get("capabilities")
                or configured_authority.get("capabilities")
                or ["agent_assignment.transition"],
            ),
        }
        causation_id = event_id
    now = str(updated["updated_at"])
    payload = HOME_CONTRACTS_V1.prepare_outbound(
        {
            "schema_id": (
                "kolibri.agent_assignment.status_changed.event"
            ),
            "schema_version": "1.0",
            "assignment_id": assignment_id,
            "previous_status": previous.get("status"),
            "new_status": status,
            "previous_version": int(previous.get("version") or 0),
            "new_version": version,
            "reason": reason,
        },
        "kolibri.agent_assignment.status_changed.event",
    )
    event = {
        "schema_id": "kolibri.event",
        "schema_version": "1.0",
        "message_id": event_id,
        "event_name": "agent_assignment.status_changed",
        "payload_schema_id": (
            "kolibri.agent_assignment.status_changed.event"
        ),
        "payload_schema_version": "1.0",
        "occurred_at": now,
        "recorded_at": now,
        "producer_owner": "logical_home_control_plane",
        "identity": {
            "tenant_id": updated["tenant_id"],
            "user_id": user_id,
            "actor": actor,
            "authority": authority,
            "subject_refs": {
                "goal_id": updated["goal_id"],
                "case_id": updated["case_id"],
                "task_id": updated["task_id"],
            },
        },
        "trace": {
            "trace_id": event_digest[:32],
            "span_id": event_digest[32:48],
            "parent_span_id": None,
            "correlation_id": assignment_id,
            "causation_id": causation_id,
        },
        "aggregate": {
            "aggregate_type": "agent_assignment",
            "aggregate_id": assignment_id,
            "aggregate_version": version,
        },
        "source_command_id": None,
        "deduplication_key": (
            f"{assignment_id}:status:{version}"
        ),
        "payload": payload,
    }
    result = HOME_CONTRACTS_V1.validate_inbound(
        event,
        "kolibri.event",
    )
    if not result.ok:
        raise RuntimeError(
            "assignment_status_event_invalid:"
            + ",".join(
                f"{violation.path}:{violation.code}"
                for violation in result.violations
            ),
        )
    return HOME_CONTRACTS_V1.prepare_outbound(
        event,
        "kolibri.event",
    )


def load_assignment_status_events(
    assignment_id: str,
) -> list[dict[str, Any]]:
    event_ids = redis.command(
        "LRANGE",
        assignment_status_event_ids_key(assignment_id),
        0,
        -1,
    ) or []
    return [
        event
        for event in (
            get_json(assignment_status_event_key(str(event_id)))
            for event_id in event_ids
        )
        if event is not None
    ]


def set_assignment_status(
    assignment: dict[str, Any],
    status: str,
    *,
    reason: str = "",
    audit_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assignment_id = str(
        assignment.get("assignment_id") or "",
    ).strip()
    if not assignment_id:
        raise ValueError("assignment_id required")
    reason = str(reason).strip() or "assignment status changed"
    if len(reason) > 2000:
        raise ValueError("assignment status reason too long")
    for _ in range(5):
        expected_raw = redis.command(
            "GET",
            assignment_key(assignment_id),
        )
        if expected_raw is None:
            raise RuntimeError("assignment_not_found")
        current = json.loads(expected_raw)
        current_status = str(current.get("status") or "").strip()
        if (
            current_status == status
            or current_status in ASSIGNMENT_TERMINAL_STATES
        ):
            assignment.clear()
            assignment.update(current)
            return assignment
        updated = dict(current)
        updated["status"] = status
        updated["version"] = int(updated.get("version") or 0) + 1
        updated["updated_at"] = utc_now()
        updated.pop("revoked_at", None)
        updated.pop("revocation_reason", None)
        declared_assignment = True
        try:
            parse_declared_assignment_v1(current)
        except DeclaredContractV1Error:
            # Legacy assignment projections can predate the v1 opaque-ID
            # contract. Preserve their compatibility surface without adding
            # schema-forbidden revocation metadata.
            declared_assignment = False
        else:
            updated = parse_declared_assignment_v1(updated)
        if declared_assignment:
            event = _assignment_status_event(
                previous=current,
                updated=updated,
                reason=reason,
                audit_context=audit_context,
            )
            event_id = str(event["message_id"])
            updated_raw = _json_record(updated)
            reply = redis.command(
                "EVAL",
                ASSIGNMENT_STATUS_EVENT_LUA,
                7,
                assignment_key(assignment_id),
                assignment_ids_key(),
                assignment_task_index_key(str(updated["task_id"])),
                a2a_agent_card_active_assignments_key(
                    str(updated["agent_card_id"]),
                ),
                assignment_status_event_key(event_id),
                assignment_status_event_global_ids_key(),
                assignment_status_event_ids_key(assignment_id),
                expected_raw,
                updated_raw,
                assignment_id,
                event_id,
                _json_record(event),
                (
                    "remove"
                    if (
                        status in ASSIGNMENT_TERMINAL_STATES
                        and status != "revoked"
                    )
                    else "keep"
                ),
            )
            outcome = str(reply[0])
            stored = (
                json.loads(reply[1])
                if len(reply) > 1 and reply[1]
                else None
            )
        else:
            outcome, stored = _write_assignment_registry(
                updated,
                mode="cas",
                expected_raw=expected_raw,
            )
        if outcome == "committed":
            assignment.clear()
            assignment.update(updated)
            return assignment
        if outcome != "stale":
            raise RuntimeError(
                f"assignment_status_transition_failed:{outcome}",
            )
        if stored is not None:
            assignment.clear()
            assignment.update(stored)
    raise RuntimeError("assignment_status_transition_conflict")


def mark_assignment_for_task_status(
    task: dict[str, Any],
    *,
    status: str,
    reason: str = "",
) -> None:
    assignment_id = str(task.get("current_assignment_id") or "").strip()
    if not assignment_id:
        return
    assignment = load_assignment(assignment_id)
    if assignment is None:
        return
    set_assignment_status(
        assignment,
        status,
        reason=reason,
    )


def mark_assignment_by_id(
    assignment_id: str,
    *,
    status: str,
    reason: str = "",
    audit_context: dict[str, Any] | None = None,
) -> None:
    assignment = load_assignment(assignment_id)
    if assignment is None:
        return
    set_assignment_status(
        assignment,
        status,
        reason=reason,
        audit_context=audit_context,
    )


def enqueue(task_id: str) -> None:
    # The execution queue is a recoverable projection of canonical work. Keep
    # one queue entry per task so replaying the graph projector cannot create
    # duplicate leases.
    redis.command("LREM", key("queue"), 0, task_id)
    redis.command("RPUSH", key("queue"), task_id)


def remove_from_queue(task_id: str) -> None:
    redis.command("LREM", key("queue"), 0, task_id)


class DeclaredContractV1Error(ValueError):
    """A declared canonical sidecar is invalid and cannot fall back to legacy."""

    def __init__(self, code: str, violations: list[dict[str, str]]) -> None:
        self.code = code
        self.violations = violations
        super().__init__(code)


def parse_declared_contract_v1(
    container: dict[str, Any],
    expected_schema_id: str,
    *,
    bound_id: str | None = None,
) -> dict[str, Any] | None:
    if "contract_v1" not in container:
        return None
    value = container["contract_v1"]
    result = HOME_CONTRACTS_V1.validate_inbound(value, expected_schema_id)
    if not result.ok:
        raise DeclaredContractV1Error(
            result.code or "invalid_contract",
            [
                {"path": violation.path, "code": violation.code}
                for violation in result.violations
            ],
        )
    parsed = HOME_CONTRACTS_V1.prepare_outbound(value, expected_schema_id)
    if (
        bound_id is not None
        and expected_schema_id in {"kolibri.task", "kolibri.artifact"}
        and parsed.get("task_id") != bound_id
    ):
        raise DeclaredContractV1Error(
            "contract_binding_mismatch",
            [{"path": "/contract_v1/task_id", "code": "binding"}],
        )
    return parsed


def project_declared_task_v1(
    envelope: dict[str, Any],
    canonical_task: dict[str, Any],
) -> dict[str, Any]:
    """Bind canonical task intent to the legacy execution projection.

    During expand/migrate the v1 sidecar is the source for execution intent,
    while the legacy queue owns lease state. Only pre-execution canonical
    states are accepted at create time; an already-running sidecar must never
    be re-enqueued as a different legacy task.
    """

    if (
        canonical_task.get("state") not in {"ready", "failed_retryable"}
        or canonical_task.get("current_attempt_id") is not None
        or canonical_task.get("current_assignment_id") is not None
    ):
        raise DeclaredContractV1Error(
            "contract_binding_mismatch",
            [{
                "path": "/contract_v1",
                "code": "task_not_ready_for_execution",
            }],
        )
    projected = dict(envelope)
    for field in ("kind", "objective", "title"):
        canonical_value = canonical_task[field]
        if field in projected and projected[field] != canonical_value:
            raise DeclaredContractV1Error(
                "contract_binding_mismatch",
                [{"path": f"/{field}", "code": "binding"}],
            )
        projected[field] = canonical_value

    canonical_capabilities = list(canonical_task["required_capabilities"])
    if "required_capabilities" in projected and (
        normalized_string_list(projected["required_capabilities"])
        != sorted(canonical_capabilities)
    ):
        raise DeclaredContractV1Error(
            "contract_binding_mismatch",
            [{"path": "/required_capabilities", "code": "binding"}],
        )
    singular = projected.get("required_capability")
    if singular is not None and singular not in canonical_capabilities:
        raise DeclaredContractV1Error(
            "contract_binding_mismatch",
            [{"path": "/required_capability", "code": "binding"}],
        )
    projected["required_capabilities"] = canonical_capabilities
    projected["contract_v1"] = canonical_task
    projected.setdefault("task_id", canonical_task["task_id"])
    return projected


def reject_unmaterialized_artifact_contract(
    result: Any,
    *,
    task_id: str,
) -> None:
    """Keep canonical artifacts off every result mutation boundary.

    Provider result dictionaries are not immutable Product/Data artifacts.
    A declared v1 artifact is therefore rejected on complete, annotate and
    fail until verified bytes and lineage have been materialized internally.
    """

    if not isinstance(result, dict):
        return
    canonical_artifact = parse_declared_contract_v1(
        result,
        "kolibri.artifact",
        bound_id=task_id,
    )
    if canonical_artifact is not None:
        raise DeclaredContractV1Error(
            "artifact_materialization_required",
            [{
                "path": "/result/contract_v1",
                "code": "unverified_materialization",
            }],
        )


def reject_direct_canonical_task_mutation(
    task: dict[str, Any],
    *,
    route: str,
) -> None:
    """Prevent legacy routes from becoming a second canonical authority.

    P03-T03 will own signed attempts and task transitions. Until that
    contract exists, canonical execution sidecars are read-only on legacy
    mutation routes.
    """

    canonical_task = parse_declared_contract_v1(
        task.get("envelope", {}),
        "kolibri.task",
        bound_id=str(task["task_id"]),
    )
    if canonical_task is not None:
        raise DeclaredContractV1Error(
            "canonical_task_transition_required",
            [{
                "path": route,
                "code": "signed_task_transition_command_required",
            }],
        )


def normalize_task(envelope: dict[str, Any]) -> dict[str, Any]:
    task_id = envelope.get("task_id") or f"KOL-TASK-{uuid.uuid4().hex[:12]}"
    created = utc_now()
    return {
        "task_id": task_id,
        "idempotency_key": envelope.get("idempotency_key") or task_id,
        "kind": envelope.get("kind", "read_only_probe"),
        "state": STATE_QUEUED,
        "attempt": 0,
        "max_retries": int(envelope.get("max_retries", MAX_RETRIES)),
        "lease_contract_version": LEASE_CONTRACT_VERSION,
        "attempt_id": None,
        "lease_id": None,
        "lease_slot_id": None,
        "fencing_token": None,
        "lease_owner": None,
        "lease_until": None,
        "heartbeat_at": None,
        "result_reference": None,
        "result": None,
        "error_type": None,
        "error": None,
        "created_at": created,
        "updated_at": created,
        "envelope": envelope,
    }


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def normalized_string_list(value: Any) -> list[str]:
    """Return a deterministic, non-empty capability/id list."""
    normalized = {
        str(item).strip()
        for item in ensure_list(value)
        if item is not None and str(item).strip()
    }
    return sorted(normalized)


def is_agent_slot_heartbeat(body: dict[str, Any]) -> bool:
    # An empty slot collection on a generic Agent Host heartbeat is not an
    # instruction to erase independently live slots.
    return bool(body.get("slot_id")) or bool(body.get("agent_slots"))


def resolve_logical_node_id(requested_node_id: str, body: dict[str, Any]) -> str:
    """Resolve a process identity to one logical node without implicit aliases.

    A legacy process such as ``home-codex-provider`` may migrate into the
    logical ``home`` record only by explicitly declaring ``logical_node_id``
    and a slot payload. A generic heartbeat cannot silently rename a node.
    """
    requested = str(requested_node_id).strip()
    logical = str(body.get("logical_node_id") or body.get("parent_node_id") or requested).strip()
    if not requested or not logical:
        raise ValueError("node_id_required")
    if logical != requested and not is_agent_slot_heartbeat(body):
        raise ValueError("logical_node_alias_requires_agent_slot")
    return logical


def _stored_agent_slots(node: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_slots = node.get("agent_slots")
    if isinstance(raw_slots, dict):
        result: dict[str, dict[str, Any]] = {}
        for raw_slot_id, raw_slot in raw_slots.items():
            if not isinstance(raw_slot, dict):
                continue
            slot_id = str(raw_slot.get("slot_id") or raw_slot_id).strip()
            if slot_id:
                result[slot_id] = dict(raw_slot, slot_id=slot_id)
        return result
    if isinstance(raw_slots, list):
        result = {}
        for raw_slot in raw_slots:
            if not isinstance(raw_slot, dict):
                continue
            slot_id = str(raw_slot.get("slot_id") or "").strip()
            if slot_id:
                result[slot_id] = dict(raw_slot, slot_id=slot_id)
        return result
    return {}


def _slot_payloads(body: dict[str, Any], logical_node_id: str) -> list[dict[str, Any]]:
    """Normalize top-level and batched slot heartbeats.

    ``agent_slots`` accepts either a list, a single slot object, or a mapping
    keyed by slot id. Repeated ids are deterministically merged in input order.
    """
    raw_entries: list[dict[str, Any]] = []
    if body.get("slot_id"):
        raw_entries.append({
            key_name: value
            for key_name, value in body.items()
            if key_name not in {"agent_slots", "logical_node_id", "parent_node_id", "node_id"}
        })

    if "agent_slots" in body:
        raw_slots = body.get("agent_slots")
        if isinstance(raw_slots, list):
            if not all(isinstance(item, dict) for item in raw_slots):
                raise ValueError("agent_slots_must_contain_objects")
            raw_entries.extend(dict(item) for item in raw_slots)
        elif isinstance(raw_slots, dict):
            if "slot_id" in raw_slots:
                raw_entries.append(dict(raw_slots))
            else:
                for mapped_slot_id, raw_slot in raw_slots.items():
                    if not isinstance(raw_slot, dict):
                        raise ValueError("agent_slots_must_contain_objects")
                    slot = dict(raw_slot)
                    declared_slot_id = slot.get("slot_id")
                    if declared_slot_id and str(declared_slot_id) != str(mapped_slot_id):
                        raise ValueError("agent_slot_id_mismatch")
                    slot["slot_id"] = str(mapped_slot_id)
                    raw_entries.append(slot)
        else:
            raise ValueError("agent_slots_must_be_object_or_list")

    if not raw_entries:
        raise ValueError("agent_slot_id_required")

    merged: dict[str, dict[str, Any]] = {}
    for raw_slot in raw_entries:
        slot_id = str(raw_slot.get("slot_id") or "").strip()
        if not slot_id or len(slot_id) > 200 or any(char.isspace() for char in slot_id):
            raise ValueError("invalid_agent_slot_id")
        declared_node = raw_slot.get("logical_node_id") or raw_slot.get("parent_node_id") or raw_slot.get("node_id")
        if declared_node and str(declared_node).strip() != logical_node_id:
            raise ValueError("agent_slot_node_mismatch")
        slot = merged.setdefault(slot_id, {"slot_id": slot_id})
        slot.update(raw_slot)
        slot["slot_id"] = slot_id
        slot["node_id"] = logical_node_id
    return [merged[slot_id] for slot_id in sorted(merged)]


def _agent_slot_projection(slot: dict[str, Any], current: float) -> dict[str, Any]:
    projected = dict(slot)
    heartbeat_ts = parse_iso_ts(slot.get("heartbeat_at"))
    age = None if heartbeat_ts is None else max(0, int(current - heartbeat_ts))
    freshness = "stale" if age is None or age > NODE_STALE_AFTER else "fresh"
    state = str(slot.get("status") or slot.get("health") or "online").strip().lower()
    operational = freshness == "fresh" and state not in INACTIVE_AGENT_SLOT_STATES and not bool(slot.get("draining"))
    projected["freshness"] = freshness
    projected["heartbeat_age_seconds"] = age
    projected["effective"] = operational
    return projected


def _runner_state_priority(value: Any) -> int:
    if isinstance(value, dict):
        state = str(value.get("status") or "").strip().lower()
    else:
        state = str(value or "").strip().lower()
    if state in {"available", "healthy", "online", "ready", "running"}:
        return 0
    if state in BLOCKED_RUNNER_STATES:
        return 2
    return 1


def refresh_node_effective_state(node: dict[str, Any], current: float | None = None) -> dict[str, Any]:
    """Rebuild effective capabilities/runners from base plus live slots."""
    projected = dict(node)
    current_ts = now_ts() if current is None else current
    slots = _stored_agent_slots(projected)

    if "base_capabilities" in projected:
        base_capabilities = normalized_string_list(projected.get("base_capabilities"))
    else:
        # One-time migration from the legacy flat representation. Slot caps are
        # subtracted because ``capabilities`` may already be an old union.
        slot_capabilities = {
            capability
            for slot in slots.values()
            for capability in normalized_string_list(slot.get("capabilities"))
        }
        base_capabilities = [
            capability
            for capability in normalized_string_list(projected.get("capabilities"))
            if capability not in slot_capabilities
        ]

    if "base_runners" in projected and isinstance(projected.get("base_runners"), dict):
        base_runners = dict(projected.get("base_runners") or {})
    else:
        slot_runner_names = {
            str(runner)
            for slot in slots.values()
            if isinstance(slot.get("runners"), dict)
            for runner in slot["runners"]
        }
        base_runners = {
            str(runner): value
            for runner, value in (projected.get("runners") or {}).items()
            if str(runner) not in slot_runner_names
        } if isinstance(projected.get("runners"), dict) else {}

    effective_capabilities = set(base_capabilities)
    effective_runners = dict(base_runners)
    capability_slots: dict[str, list[str]] = {}
    runner_slots: dict[str, list[str]] = {}
    projected_slots: dict[str, dict[str, Any]] = {}
    for slot_id in sorted(slots):
        slot = _agent_slot_projection(slots[slot_id], current_ts)
        projected_slots[slot_id] = slot
        if not slot["effective"]:
            continue
        for capability in normalized_string_list(slot.get("capabilities")):
            effective_capabilities.add(capability)
            capability_slots.setdefault(capability, []).append(slot_id)
        slot_runners = slot.get("runners") if isinstance(slot.get("runners"), dict) else {}
        for runner in sorted(slot_runners):
            runner_name = str(runner)
            runner_slots.setdefault(runner_name, []).append(slot_id)
            current_value = effective_runners.get(runner_name)
            candidate = slot_runners[runner]
            if current_value is None or _runner_state_priority(candidate) < _runner_state_priority(current_value):
                effective_runners[runner_name] = candidate

    projected["base_capabilities"] = base_capabilities
    projected["base_runners"] = base_runners
    projected["agent_slots"] = projected_slots
    projected["capabilities"] = sorted(effective_capabilities)
    projected["effective_capabilities"] = projected["capabilities"]
    projected["runners"] = {runner: effective_runners[runner] for runner in sorted(effective_runners)}
    projected["capability_slots"] = {name: ids for name, ids in sorted(capability_slots.items())}
    projected["runner_slots"] = {name: ids for name, ids in sorted(runner_slots.items())}
    return projected


def merge_node_heartbeat(
    node: dict[str, Any],
    logical_node_id: str,
    body: dict[str, Any],
    *,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Merge one process heartbeat without flattening other process slots."""
    observed = observed_at or utc_now()
    merged = refresh_node_effective_state(dict(node, node_id=logical_node_id))
    slots = _stored_agent_slots(merged)

    if is_agent_slot_heartbeat(body):
        for incoming in _slot_payloads(body, logical_node_id):
            slot_id = incoming["slot_id"]
            slot = dict(slots.get(slot_id) or {"slot_id": slot_id, "node_id": logical_node_id})
            for key_name, value in incoming.items():
                if key_name in {"logical_node_id", "parent_node_id", "heartbeat_at"}:
                    continue
                if key_name == "capabilities":
                    slot[key_name] = normalized_string_list(value)
                elif key_name == "runners":
                    if not isinstance(value, dict):
                        raise ValueError("agent_slot_runners_must_be_object")
                    slot[key_name] = dict(value)
                else:
                    slot[key_name] = value
            slot["slot_id"] = slot_id
            slot["node_id"] = logical_node_id
            slot["heartbeat_at"] = observed
            slot.setdefault("health", "online")
            slots[slot_id] = slot
        merged["agent_slots"] = slots
    else:
        reserved = {
            "agent_slots", "base_capabilities", "base_runners", "capabilities",
            "effective_capabilities", "health", "heartbeat_at", "logical_node_id",
            "node_id", "parent_node_id", "runners", "slot_id", "status",
        }
        for key_name, value in body.items():
            if key_name not in reserved:
                merged[key_name] = value
        if "capabilities" in body:
            merged["base_capabilities"] = normalized_string_list(body.get("capabilities"))
        if "runners" in body:
            if not isinstance(body.get("runners"), dict):
                raise ValueError("node_runners_must_be_object")
            merged["base_runners"] = dict(body.get("runners") or {})

    merged["node_id"] = logical_node_id
    merged["health"] = "online"
    merged["heartbeat_at"] = observed
    return refresh_node_effective_state(merged)


def persist_node_heartbeat(requested_node_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Persist a heartbeat under its logical node, never its process alias."""
    node_id = resolve_logical_node_id(requested_node_id, body)
    with NODE_UPDATE_LOCK:
        existing = get_json(node_key(node_id))
        if is_agent_slot_heartbeat(body) and not existing:
            raise LookupError("logical_node_not_registered")
        node = merge_node_heartbeat(existing or {"node_id": node_id}, node_id, body)
        set_json(node_key(node_id), node)
        redis.command("SADD", key("node_ids"), node_id)
        return node


def lease_claim_view(node: dict[str, Any], body: dict[str, Any]) -> tuple[list[str], dict[str, Any], str | None]:
    """Bind a lease poll to base agent state or one live process slot."""
    projected = refresh_node_effective_state(node)
    slots = _stored_agent_slots(projected)
    requested_slot_id = str(body.get("slot_id") or "").strip() or None
    agent_id = str(body.get("agent_id") or "").strip()

    if requested_slot_id is None and agent_id:
        matches = [
            slot_id
            for slot_id, slot in slots.items()
            if slot.get("effective") and agent_id in {slot_id, str(slot.get("agent_id") or "")}
        ]
        if len(matches) > 1:
            raise ValueError("agent_id_matches_multiple_slots")
        requested_slot_id = matches[0] if matches else None

    claim_node = dict(projected)
    if requested_slot_id is not None:
        slot = slots.get(requested_slot_id)
        if not slot:
            raise ValueError("agent_slot_not_registered")
        if str(slot.get("node_id") or projected.get("node_id")) != str(projected.get("node_id")):
            raise ValueError("agent_slot_node_mismatch")
        if not slot.get("effective"):
            raise ValueError("agent_slot_not_available")
        slot_agent_id = str(slot.get("agent_id") or "").strip()
        if agent_id and slot_agent_id and agent_id != slot_agent_id:
            raise ValueError("agent_slot_owner_mismatch")
        authorized_capabilities = normalized_string_list(slot.get("capabilities"))
        claim_node["runners"] = dict(slot.get("runners") or {}) if isinstance(slot.get("runners"), dict) else {}
        claim_node["claim_slot_id"] = requested_slot_id
    else:
        registered_agent_id = str(projected.get("agent_id") or "").strip()
        if (
            registered_agent_id
            and agent_id
            and not hmac.compare_digest(registered_agent_id, agent_id)
        ):
            raise ValueError("node_agent_owner_mismatch")
        authorized_capabilities = normalized_string_list(projected.get("base_capabilities"))
        claim_node["runners"] = dict(projected.get("base_runners") or {})
        claim_node["claim_slot_id"] = None

    if "capabilities" in body:
        reported = set(normalized_string_list(body.get("capabilities")))
        authorized_capabilities = [capability for capability in authorized_capabilities if capability in reported]
    if isinstance(body.get("runners"), dict):
        reported_runners = body["runners"]
        claim_node["runners"] = {
            runner: reported_runners.get(runner, value)
            for runner, value in claim_node["runners"].items()
        }
    claim_node["capabilities"] = authorized_capabilities
    return authorized_capabilities, claim_node, requested_slot_id


def validate_task_mutation_fence(task: dict[str, Any], body: dict[str, Any]) -> str | None:
    """Validate the complete durable lease fence for every task mutation.

    Agent-facing heartbeat/complete/fail never has an unfenced compatibility
    path, including terminal replays. Identity and slot are part of the fence,
    not optional metadata.
    """
    required_body_fields = (
        *LEASE_FENCE_FIELDS,
        "node_id",
        "agent_id",
        "slot_id",
    )
    provided = [
        field
        for field in required_body_fields
        if body.get(field) is not None and str(body.get(field)) != ""
    ]
    stored = [field for field in LEASE_FENCE_FIELDS if task.get(field) is not None]
    state = task.get("state")

    if len(provided) != len(required_body_fields):
        return "lease_fence_fields_required"
    if len(stored) != len(LEASE_FENCE_FIELDS):
        return "lease_fence_not_issued"
    if state not in ACTIVE_LEASE_STATES and state not in TERMINAL_STATES:
        return "lease_is_not_active"
    if state in ACTIVE_LEASE_STATES:
        lease_until = task.get("lease_until")
        if lease_until is None or str(lease_until).strip() == "":
            return "lease_expiry_not_issued"
        try:
            lease_expiry = float(lease_until)
        except (TypeError, ValueError):
            return "lease_expiry_invalid"
        if lease_expiry <= now_ts():
            return "lease_expired"
    for field in LEASE_FENCE_FIELDS:
        if str(body.get(field)) != str(task.get(field)):
            return f"stale_{field}"
    lease_owner = str(task.get("lease_owner") or "")
    expected_node, _, expected_agent = lease_owner.partition(":")
    if not expected_node or not expected_agent:
        return "lease_owner_not_issued"
    if str(body.get("node_id")) != expected_node:
        return "lease_node_mismatch"
    if str(body.get("agent_id")) != expected_agent:
        return "lease_agent_mismatch"
    expected_slot = str(task.get("lease_slot_id") or "")
    if not expected_slot:
        return "lease_slot_not_issued"
    if str(body.get("slot_id")) != expected_slot:
        return "lease_slot_mismatch"
    return None


def validate_task_assignment_state(task: dict[str, Any]) -> str | None:
    """Validate the active assignment for one mutable task lease."""
    assignment_id = str(task.get("current_assignment_id") or "").strip()
    if not assignment_id:
        return None
    assignment = load_assignment(assignment_id)
    if assignment is None:
        return "assignment_not_found"
    status = str(assignment.get("status") or "").strip()
    if status in ASSIGNMENT_REVOKED_STATES:
        return f"assignment_{status}"
    if status not in ASSIGNMENT_ACTIVE_STATES:
        return "assignment_inactive"
    if str(assignment.get("task_id") or "").strip() != str(task.get("task_id") or "").strip():
        return "assignment_task_mismatch"
    task_case_id = str(
        task.get("case_id")
        or task.get("envelope", {}).get("contract_v1", {}).get("case_id")
        or "",
    ).strip()
    assignment_case_id = str(assignment.get("case_id") or "").strip()
    if task_case_id and assignment_case_id and task_case_id != assignment_case_id:
        return "assignment_case_mismatch"
    task_tenant_id = str(
        task.get("tenant_id")
        or task.get("envelope", {}).get("contract_v1", {}).get("tenant_id")
        or "",
    ).strip()
    assignment_tenant_id = str(assignment.get("tenant_id") or "").strip()
    if task_tenant_id and assignment_tenant_id and task_tenant_id != assignment_tenant_id:
        return "assignment_tenant_mismatch"
    authority = assignment.get("authority_profile") or {}
    expected_authority_id = os.environ.get(
        "FACTORY_CONTROL_AUTHORITY_ID",
        "auth_lhcp_runtime",
    )
    expected_authority_epoch = os.environ.get(
        "FACTORY_CONTROL_AUTHORITY_EPOCH",
        "1",
    )
    if str(authority.get("authority_role") or "") != "logical_home_control_plane":
        return "assignment_authority_role_mismatch"
    if str(authority.get("authority_id") or "") != expected_authority_id:
        return "assignment_authority_id_mismatch"
    try:
        if int(authority.get("authority_epoch") or 0) != int(expected_authority_epoch):
            return "assignment_authority_epoch_mismatch"
    except (TypeError, ValueError):
        return "assignment_authority_epoch_malformed"
    authority_expires_at = parse_iso_ts(authority.get("expires_at"))
    if authority_expires_at is None:
        return "assignment_authority_expiry_malformed"
    assignment_deadline = parse_iso_ts(assignment.get("deadline_at"))
    if assignment_deadline is None:
        return "assignment_deadline_malformed"
    now = now_ts()
    if authority_expires_at <= now:
        set_assignment_status(
            assignment,
            "expired",
            reason="assignment authority expired",
        )
        return "assignment_expired"
    if assignment_deadline <= now:
        set_assignment_status(
            assignment,
            "expired",
            reason="assignment deadline exceeded",
        )
        return "assignment_expired"
    allowed_resource_refs = {
        str(ref).strip()
        for ref in ensure_list(authority.get("allowed_resource_refs"))
        if str(ref).strip()
    }
    task_goal_id = str(
        task.get("goal_id")
        or task.get("envelope", {}).get("goal_id")
        or task.get("contract_v1", {}).get("goal_id")
        or task.get("envelope", {}).get("contract_v1", {}).get("goal_id")
        or "",
    ).strip()
    required_refs = {
        str(task.get("task_id") or "").strip(),
        task_goal_id,
        assignment.get("case_id") if task_case_id else "",
    }
    missing_refs = {
        required
        for required in required_refs
        if required and required not in allowed_resource_refs
    }
    if missing_refs:
        return "assignment_scope_mismatch"
    return None


def _new_assignment_identifier(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _coerce_output_ids(task: dict[str, Any]) -> list[str]:
    outputs = task.get("expected_outputs")
    if isinstance(outputs, list) and outputs:
        collected: set[str] = set()
        for item in outputs:
            if isinstance(item, dict):
                output_id = item.get("output_id")
            else:
                output_id = item
            if output_id:
                collected.add(str(output_id))
        if collected:
            return sorted(collected)
    task_id = str(task.get("task_id") or "task").strip()
    return [f"output_{task_id}"]


def build_default_task_assignment(
    task: dict[str, Any],
    leased_task: dict[str, Any],
    node_id: str,
    agent_id: str,
    slot_id: str | None,
) -> dict[str, Any]:
    if (
        task.get("schema_id") == "kolibri.task"
        or (task.get("envelope") or {}).get("contract_v1")
        is not None
    ):
        raise ValueError(
            "canonical_task_requires_registered_agent_card",
        )
    assignment_id = str(leased_task.get("assignment_id") or _new_assignment_identifier("assignment"))
    task_id = str(task.get("task_id") or leased_task.get("task_id") or "task").strip()
    envelope = task.get("envelope") or {}
    objective = str(task.get("objective") or envelope.get("objective") or "runtime execution").strip()
    kind = str(task.get("kind") or envelope.get("kind") or "task").strip()
    if not task_id:
        task_id = str(leased_task.get("task_id") or "task").strip()
    tenant_id = str(task.get("tenant_id") or envelope.get("tenant_id") or f"ten_{uuid.uuid4().hex[:16]}").strip()
    if not tenant_id.startswith("ten_"):
        tenant_id = f"ten_{uuid.uuid4().hex[:16]}"
    goal_id = str(
        task.get("goal_id")
        or task.get("envelope", {}).get("goal_id")
        or task.get("contract_v1", {}).get("goal_id")
        or f"goal_{uuid.uuid4().hex[:16]}",
    ).strip()
    if not goal_id.startswith("goal_"):
        goal_id = f"goal_{uuid.uuid4().hex[:18]}"
    case_id = str(
        task.get("case_id")
        or task.get("envelope", {}).get("case_id")
        or task.get("contract_v1", {}).get("case_id")
        or f"case_{uuid.uuid4().hex[:16]}",
    ).strip()
    if not case_id.startswith("case_"):
        case_id = f"case_{uuid.uuid4().hex[:18]}"
    lease_until = leased_task.get("lease_until")
    lease_deadline = (
        datetime.fromtimestamp(float(lease_until), tz=timezone.utc).isoformat()
        if lease_until is not None
        else datetime.fromtimestamp(
            now_ts() + LEASE_DURATION,
            tz=timezone.utc,
        ).isoformat()
    )
    authority_expires_at = datetime.fromtimestamp(
        now_ts() + (2 * LEASE_DURATION),
        tz=timezone.utc,
    ).isoformat()
    authority_epoch = int(os.environ.get(
        "FACTORY_CONTROL_AUTHORITY_EPOCH",
        "1",
    ))
    allowed_resource_refs = [
        ref
        for ref in {task_id, goal_id, case_id}
        if str(ref).strip()
    ]
    assignment = {
        "schema_id": "kolibri.agent_assignment",
        "schema_version": "1.0",
        "assignment_id": assignment_id,
        "tenant_id": tenant_id,
        "goal_id": goal_id,
        "case_id": case_id,
        "task_id": task_id,
        "task_version": int(task.get("version") or 1),
        "attempt_id": leased_task.get("attempt_id"),
        "assignee_actor_id": f"actor_{uuid.uuid4().hex[:14]}",
        "agent_card_id": f"agentcard_{uuid.uuid4().hex}",
        "agent_card_version": 1,
        "temporary_role": kind if kind else "generic",
        "purpose": objective[:200] if objective else "execution support",
        "authority_profile": {
            "authority_id": os.environ.get(
                "FACTORY_CONTROL_AUTHORITY_ID",
                "auth_lhcp_runtime",
            ),
            "authority_role": "logical_home_control_plane",
            "authority_epoch": authority_epoch,
            "authorization_decision_id": f"decision_{uuid.uuid4().hex[:18]}",
            "capabilities": ["task_owner_state"],
            "allowed_tool_ids": [],
            "allowed_resource_refs": allowed_resource_refs,
            "expires_at": authority_expires_at,
        },
        "context_slice": {
            "case_version": int(task.get("version") or 1),
            "fact_ids": [],
            "assumption_ids": [],
            "decision_ids": [],
            "artifact_refs": [],
            "classification": "internal",
            "max_bytes": int(os.environ.get("FACTORY_ASSIGNMENT_MAX_BYTES", "1048576")),
        },
        "budget": {
            "compute_units_limit": int((task.get("budget") or {}).get("compute_units_limit", 0) or 0),
            "tool_calls_limit": int((task.get("budget") or {}).get("tool_calls_limit", 0) or 0),
            "external_spend_limit_minor": int((task.get("budget") or {}).get("external_spend_limit_minor", 0) or 0),
            "currency": str((task.get("budget") or {}).get("currency", "RUB")),
        },
        "lease_id": leased_task.get("lease_id"),
        "deadline_at": lease_deadline,
        "required_output_ids": _coerce_output_ids(task),
        "required_evidence_types": ["result"],
        "status": "active",
        "version": 1,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    return assignment


def canonical_task_required_tool_ids(
    canonical_task: dict[str, Any],
    leased_task: dict[str, Any],
) -> list[str]:
    candidates: list[Any] = [
        canonical_task.get("required_tool_ids"),
        (canonical_task.get("constraints") or {}).get(
            "required_tool_ids",
        ),
        (leased_task.get("envelope") or {}).get("required_tool_ids"),
        (
            (leased_task.get("envelope") or {}).get("constraints")
            or {}
        ).get("required_tool_ids"),
    ]
    tools: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, list):
            continue
        tools.update(
            str(tool_id).strip()
            for tool_id in candidate
            if str(tool_id).strip()
        )
    return sorted(tools)


def execution_claimant_policy_constraints(
    *,
    node_id: str,
    agent_id: str,
    slot_id: str,
) -> set[str]:
    def constraint(kind: str, value: str) -> str:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return f"claim.{kind}_sha256:{digest}"

    return {
        constraint("node", node_id),
        constraint("agent", agent_id),
        constraint("slot", slot_id),
    }


def agent_card_matches_execution_claimant(
    agent_card: dict[str, Any],
    leased_task: dict[str, Any],
) -> bool:
    lease_owner = str(leased_task.get("lease_owner") or "")
    node_id, separator, agent_id = lease_owner.partition(":")
    slot_id = str(leased_task.get("lease_slot_id") or "")
    if not separator or not node_id or not agent_id or not slot_id:
        return False
    required = execution_claimant_policy_constraints(
        node_id=node_id,
        agent_id=agent_id,
        slot_id=slot_id,
    )
    return required.issubset(
        set(agent_card.get("policy_constraints") or []),
    )


def resolve_canonical_execution_agent_card(
    canonical_task: dict[str, Any],
    leased_task: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    required_capabilities = {
        str(capability).strip()
        for capability in canonical_task.get("required_capabilities", [])
        if str(capability).strip()
    }
    required_capabilities.add("task_owner_state")
    required_tools = set(
        canonical_task_required_tool_ids(canonical_task, leased_task),
    )
    task_budget = canonical_task.get("budget") or {}
    required_spend = int(
        task_budget.get("external_spend_limit_minor") or 0,
    )
    required_currency = str(task_budget.get("currency") or "RUB")
    eligible: list[tuple[dict[str, Any], str]] = []
    for card_id in a2a_agent_card_ids():
        raw_card = redis.command("GET", a2a_agent_card_key(card_id))
        if raw_card is None:
            continue
        try:
            card = parse_declared_a2a_agent_card_v1(
                json.loads(raw_card),
            )
        except (DeclaredContractV1Error, json.JSONDecodeError):
            continue
        if card["tenant_scope"] not in {
            "platform",
            canonical_task["tenant_id"],
        }:
            continue
        if card["availability"] != "available":
            continue
        if not agent_card_matches_execution_claimant(
            card,
            leased_task,
        ):
            continue
        if card["agent_kind"] not in {
            "model",
            "worker",
            "hybrid",
            "service",
        }:
            continue
        if not required_capabilities.issubset(
            set(card["capabilities"]),
        ):
            continue
        if not required_tools.issubset(set(card["tool_ids"])):
            continue
        limits = card["limits"]
        if required_spend > int(
            limits.get("max_external_spend_minor") or 0,
        ):
            continue
        if (
            required_spend > 0
            and str(limits.get("currency") or "") != required_currency
        ):
            continue
        eligible.append((card, raw_card))
    if len(eligible) != 1:
        raise DeclaredContractV1Error(
            "canonical_execution_agent_card_unavailable",
            [{
                "path": "/agent_card",
                "code": (
                    "ambiguous_execution_agent_card"
                    if eligible
                    else "eligible_execution_agent_card_not_found"
                ),
            }],
        )
    return eligible[0]


def build_canonical_task_assignment(
    canonical_task: dict[str, Any],
    leased_task: dict[str, Any],
    *,
    agent_card: dict[str, Any],
) -> dict[str, Any]:
    lease_deadline = datetime.fromtimestamp(
        float(leased_task["lease_until"]),
        tz=timezone.utc,
    ).isoformat()
    required_capabilities = sorted({
        "task_owner_state",
        *(
            str(capability).strip()
            for capability in canonical_task.get(
                "required_capabilities",
                [],
            )
            if str(capability).strip()
        ),
    })
    required_tools = canonical_task_required_tool_ids(
        canonical_task,
        leased_task,
    )
    execution_digest = hashlib.sha256(
        (
            f"{canonical_task['tenant_id']}:"
            f"{canonical_task['task_id']}:"
            f"{leased_task['attempt_id']}:"
            f"{agent_card['agent_card_id']}"
        ).encode("utf-8"),
    ).hexdigest()
    budget = canonical_task.get("budget") or {}
    assignment = {
        "schema_id": "kolibri.agent_assignment",
        "schema_version": "1.0",
        "assignment_id": leased_task["assignment_id"],
        "tenant_id": canonical_task["tenant_id"],
        "goal_id": canonical_task["goal_id"],
        "case_id": canonical_task["case_id"],
        "task_id": canonical_task["task_id"],
        "task_version": int(canonical_task["version"]),
        "attempt_id": leased_task["attempt_id"],
        "assignee_actor_id": f"actor_{execution_digest[:24]}",
        "agent_card_id": agent_card["agent_card_id"],
        "agent_card_version": agent_card["version"],
        "temporary_role": canonical_task["kind"],
        "purpose": canonical_task["objective"][:2000],
        "authority_profile": {
            "authority_id": os.environ.get(
                "FACTORY_CONTROL_AUTHORITY_ID",
                "auth_lhcp_runtime",
            ),
            "authority_role": "logical_home_control_plane",
            "authority_epoch": int(os.environ.get(
                "FACTORY_CONTROL_AUTHORITY_EPOCH",
                "1",
            )),
            "authorization_decision_id": (
                f"decision_{execution_digest[24:48]}"
            ),
            "capabilities": required_capabilities,
            "allowed_tool_ids": required_tools,
            "allowed_resource_refs": sorted({
                canonical_task["goal_id"],
                canonical_task["case_id"],
                canonical_task["task_id"],
            }),
            "expires_at": lease_deadline,
        },
        "context_slice": {
            "case_version": int(canonical_task["version"]),
            "fact_ids": [],
            "assumption_ids": [],
            "decision_ids": [],
            "artifact_refs": [],
            "classification": "internal",
            "max_bytes": min(
                int(os.environ.get(
                    "FACTORY_ASSIGNMENT_MAX_BYTES",
                    "1048576",
                )),
                int(agent_card["limits"]["max_context_bytes"]),
            ),
        },
        "budget": {
            "compute_units_limit": int(
                budget.get("compute_units_limit") or 0,
            ),
            "tool_calls_limit": int(
                budget.get("tool_calls_limit") or 0,
            ),
            "external_spend_limit_minor": int(
                budget.get("external_spend_limit_minor") or 0,
            ),
            "currency": str(budget.get("currency") or "RUB"),
        },
        "lease_id": leased_task["lease_id"],
        "deadline_at": lease_deadline,
        "required_output_ids": _coerce_output_ids(canonical_task),
        "required_evidence_types": ["result"],
        "status": "active",
        "version": 1,
        "created_at": leased_task["updated_at"],
        "updated_at": leased_task["updated_at"],
    }
    return parse_declared_assignment_v1(
        {"contract_v1": assignment},
    )


def resolve_product_developer_agent_card(
    canonical_task: dict[str, Any],
    leased_task: dict[str, Any],
    source: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    runtime_profile = _concrete_developer_runtime_profile(
        source["runtime_profile"],
    )
    runtime_capability = source["runtime_capability"]
    runtime_constraint = developer_runtime_profile_constraint(
        runtime_profile,
    )
    required_tools = set(source["access_policy"]["tool_ids"])
    eligible: list[tuple[dict[str, Any], str]] = []
    for card_id in a2a_agent_card_ids():
        raw_card = redis.command(
            "GET",
            a2a_agent_card_key(card_id),
        )
        if raw_card is None:
            continue
        try:
            card = parse_declared_a2a_agent_card_v1(
                json.loads(raw_card),
            )
        except (DeclaredContractV1Error, json.JSONDecodeError):
            continue
        if card["tenant_scope"] not in {
            "platform",
            canonical_task["tenant_id"],
        }:
            continue
        if card["availability"] != "available":
            continue
        if not agent_card_matches_execution_claimant(
            card,
            leased_task,
        ):
            continue
        if (
            developer_agent_card_runtime_profile(card)
            != runtime_profile
            or runtime_constraint not in card["policy_constraints"]
        ):
            continue
        capabilities = set(card["capabilities"])
        if not {
            runtime_capability,
            "a2a.message.append",
            "task_owner_state",
        }.issubset(capabilities):
            continue
        if not required_tools.issubset(set(card["tool_ids"])):
            continue
        eligible.append((card, raw_card))
    if len(eligible) != 1:
        raise DeclaredContractV1Error(
            "product_developer_agent_card_unavailable",
            [{
                "path": "/agent_card",
                "code": (
                    "ambiguous_runtime_agent_card"
                    if len(eligible) > 1
                    else "eligible_runtime_agent_card_not_found"
                ),
            }],
        )
    return eligible[0]


def eligible_logical_home_requester_cards(
    *,
    tenant_id: str | None = None,
) -> list[tuple[dict[str, Any], str]]:
    allowed_scopes = {"platform"}
    if tenant_id is not None:
        allowed_scopes.add(tenant_id)
    eligible: list[tuple[dict[str, Any], str]] = []
    for card_id in a2a_agent_card_ids():
        raw_card = redis.command(
            "GET",
            a2a_agent_card_key(card_id),
        )
        if raw_card is None:
            continue
        try:
            card = parse_declared_a2a_agent_card_v1(
                json.loads(raw_card),
            )
        except (DeclaredContractV1Error, json.JSONDecodeError):
            continue
        if (
            card["tenant_scope"] not in allowed_scopes
            or card["availability"] != "available"
            or card["agent_kind"] != "service"
            or "logical_home_control_plane"
            not in card["policy_constraints"]
            or "logical_home_authority_projection"
            not in card["policy_constraints"]
            or not {
                "a2a.message.append",
                "task_owner_state",
            }.issubset(set(card["capabilities"]))
        ):
            continue
        eligible.append((card, raw_card))
    return eligible


def ensure_logical_home_authority_agent_card_projection(
) -> tuple[dict[str, Any], str]:
    """Persist the existing Logical Home authority's A2A identity projection.

    The AgentCard is a credential/capability projection required by the A2A
    contract. It is not another agent, scheduler, planner, or control plane.
    """

    eligible = eligible_logical_home_requester_cards()
    if len(eligible) == 1:
        return eligible[0]
    if not eligible:
        requester_card = parse_declared_a2a_agent_card_v1({
            "schema_id": "kolibri.agent_card",
            "schema_version": "1.0",
            "agent_card_id": LOGICAL_HOME_AUTHORITY_AGENT_CARD_ID,
            "tenant_scope": "platform",
            "display_name": "Logical Home authority A2A projection",
            "agent_kind": "service",
            "capabilities": [
                "a2a.message.append",
                "task_owner_state",
            ],
            "skills": [],
            "model_profiles": [],
            "tool_ids": [],
            "jurisdictions": [],
            "domain_tags": ["control_plane.authority"],
            "limits": {
                "max_concurrent_assignments": max(
                    1,
                    int(os.environ.get(
                        "FACTORY_LOGICAL_HOME_REQUESTER_MAX_CONCURRENT_ASSIGNMENTS",
                        "1024",
                    )),
                ),
                "max_context_bytes": max(
                    1,
                    int(os.environ.get(
                        "FACTORY_ASSIGNMENT_MAX_BYTES",
                        "1048576",
                    )),
                ),
                "max_external_spend_minor": 0,
                "currency": "RUB",
                "latency_slo_ms": max(
                    1,
                    int(os.environ.get(
                        "FACTORY_LOGICAL_HOME_REQUESTER_LATENCY_SLO_MS",
                        "120000",
                    )),
                ),
            },
            "availability": "available",
            "policy_constraints": [
                "logical_home_control_plane",
                "logical_home_authority_projection",
            ],
            "version": 1,
            "updated_at": utc_now(),
        })
        create_a2a_agent_card_atomically(requester_card)
        # Re-read after the atomic create so concurrent Home starts converge
        # on the same durable registry record.
        eligible = eligible_logical_home_requester_cards()
    if len(eligible) != 1:
        raise DeclaredContractV1Error(
            "logical_home_requester_card_unavailable",
            [{
                "path": "/requester_agent_card",
                "code": (
                    "ambiguous_requester_agent_card"
                    if len(eligible) > 1
                    else "requester_agent_card_not_found"
                ),
            }],
        )
    return eligible[0]


def resolve_logical_home_requester_card(
    canonical_task: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    eligible = eligible_logical_home_requester_cards(
        tenant_id=canonical_task["tenant_id"],
    )
    if len(eligible) != 1:
        raise DeclaredContractV1Error(
            "logical_home_requester_card_unavailable",
            [{
                "path": "/requester_agent_card",
                "code": (
                    "ambiguous_requester_agent_card"
                    if len(eligible) > 1
                    else "requester_agent_card_not_found"
                ),
            }],
        )
    return eligible[0]


def build_product_developer_assignment(
    canonical_task: dict[str, Any],
    leased_task: dict[str, Any],
    source: dict[str, Any],
    *,
    agent_card: dict[str, Any],
) -> dict[str, Any]:
    dispatch = leased_task["envelope"]["developer_dispatch"]
    runtime_profile = dispatch["runtime_profile"]
    runtime_capability = dispatch["runtime_capability"]
    identity_digest = _stable_developer_digest(
        canonical_task["tenant_id"],
        canonical_task["task_id"],
        leased_task["attempt_id"],
        runtime_profile,
    )
    actor_digest = _stable_developer_digest(
        agent_card["agent_card_id"],
        agent_card["version"],
        runtime_profile,
    )
    lease_deadline = datetime.fromtimestamp(
        float(leased_task["lease_until"]),
        tz=timezone.utc,
    ).isoformat()
    authority_id = os.environ.get(
        "FACTORY_CONTROL_AUTHORITY_ID",
        "auth_lhcp_runtime",
    )
    authority_epoch = int(os.environ.get(
        "FACTORY_CONTROL_AUTHORITY_EPOCH",
        "1",
    ))
    trusted_binding = product_developer_trusted_binding(
        source["source_command"]["payload"],
    )
    trusted_resource_refs = {
        trusted_binding[field_name]
        for field_name in (
            "trusted_agent_profile_id",
            "trusted_agent_workspace_binding_id",
        )
        if field_name in trusted_binding
    }
    assignment = {
        "schema_id": "kolibri.agent_assignment",
        "schema_version": "1.0",
        "assignment_id": leased_task["assignment_id"],
        "tenant_id": canonical_task["tenant_id"],
        "goal_id": canonical_task["goal_id"],
        "case_id": canonical_task["case_id"],
        "task_id": canonical_task["task_id"],
        "task_version": canonical_task["version"],
        "attempt_id": leased_task["attempt_id"],
        "assignee_actor_id": f"agent_{actor_digest[:40]}",
        "agent_card_id": agent_card["agent_card_id"],
        "agent_card_version": agent_card["version"],
        "temporary_role": "developer.runtime.executor",
        "purpose": canonical_task["objective"][:2000],
        "authority_profile": {
            "authority_id": authority_id,
            "authority_role": "logical_home_control_plane",
            "authority_epoch": authority_epoch,
            "authorization_decision_id": (
                f"decision_{identity_digest[:40]}"
            ),
            "capabilities": sorted({
                "a2a.message.append",
                "task_owner_state",
                runtime_capability,
            }),
            "allowed_tool_ids": source["access_policy"]["tool_ids"],
            "allowed_resource_refs": sorted({
                canonical_task["goal_id"],
                canonical_task["case_id"],
                canonical_task["task_id"],
                source["source_command_ref"],
                *trusted_resource_refs,
            }),
            "expires_at": lease_deadline,
        },
        "context_slice": {
            "case_version": canonical_task["version"],
            "fact_ids": [],
            "assumption_ids": [],
            "decision_ids": [],
            "artifact_refs": [source["source_command_ref"]],
            "classification": "restricted",
            "max_bytes": min(
                int(os.environ.get(
                    "FACTORY_ASSIGNMENT_MAX_BYTES",
                    "1048576",
                )),
                int(agent_card["limits"]["max_context_bytes"]),
            ),
        },
        "budget": canonical_task["budget"],
        "lease_id": leased_task["lease_id"],
        "deadline_at": lease_deadline,
        "required_output_ids": _coerce_output_ids(canonical_task),
        "required_evidence_types": ["a2a.handoff_or_rejection"],
        "status": "active",
        "version": 1,
        "created_at": leased_task["updated_at"],
        "updated_at": leased_task["updated_at"],
    }
    return parse_declared_assignment_v1({"contract_v1": assignment})


def build_logical_home_requester_assignment(
    canonical_task: dict[str, Any],
    leased_task: dict[str, Any],
    source: dict[str, Any],
    *,
    agent_card: dict[str, Any],
) -> dict[str, Any]:
    identity_digest = _stable_developer_digest(
        canonical_task["tenant_id"],
        canonical_task["task_id"],
        leased_task["attempt_id"],
        "logical_home_requester",
    )
    lease_deadline = datetime.fromtimestamp(
        float(leased_task["lease_until"]),
        tz=timezone.utc,
    ).isoformat()
    authority_id = os.environ.get(
        "FACTORY_CONTROL_AUTHORITY_ID",
        "auth_lhcp_runtime",
    )
    authority_epoch = int(os.environ.get(
        "FACTORY_CONTROL_AUTHORITY_EPOCH",
        "1",
    ))
    trusted_binding = product_developer_trusted_binding(
        source["source_command"]["payload"],
    )
    trusted_resource_refs = {
        trusted_binding[field_name]
        for field_name in (
            "trusted_agent_profile_id",
            "trusted_agent_workspace_binding_id",
        )
        if field_name in trusted_binding
    }
    assignment = {
        "schema_id": "kolibri.agent_assignment",
        "schema_version": "1.0",
        "assignment_id": f"assignment_{identity_digest[:40]}",
        "tenant_id": canonical_task["tenant_id"],
        "goal_id": canonical_task["goal_id"],
        "case_id": canonical_task["case_id"],
        "task_id": canonical_task["task_id"],
        "task_version": canonical_task["version"],
        "attempt_id": leased_task["attempt_id"],
        "assignee_actor_id": (
            "service_"
            + _stable_developer_digest(
                agent_card["agent_card_id"],
                agent_card["version"],
            )[:40]
        ),
        "agent_card_id": agent_card["agent_card_id"],
        "agent_card_version": agent_card["version"],
        "temporary_role": "developer.requester",
        "purpose": "Issue and receive the Home-owned developer A2A request.",
        "authority_profile": {
            "authority_id": authority_id,
            "authority_role": "logical_home_control_plane",
            "authority_epoch": authority_epoch,
            "authorization_decision_id": (
                f"decision_{identity_digest[:40]}"
            ),
            "capabilities": [
                "a2a.message.append",
                "task_owner_state",
            ],
            "allowed_tool_ids": [],
            "allowed_resource_refs": sorted({
                canonical_task["goal_id"],
                canonical_task["case_id"],
                canonical_task["task_id"],
                source["source_command_ref"],
                *trusted_resource_refs,
            }),
            "expires_at": lease_deadline,
        },
        "context_slice": {
            "case_version": canonical_task["version"],
            "fact_ids": [],
            "assumption_ids": [],
            "decision_ids": [],
            "artifact_refs": [source["source_command_ref"]],
            "classification": "restricted",
            "max_bytes": min(
                int(os.environ.get(
                    "FACTORY_ASSIGNMENT_MAX_BYTES",
                    "1048576",
                )),
                int(agent_card["limits"]["max_context_bytes"]),
            ),
        },
        "budget": {
            "compute_units_limit": 0,
            "tool_calls_limit": 0,
            "external_spend_limit_minor": 0,
            "currency": "RUB",
        },
        "lease_id": leased_task["lease_id"],
        "deadline_at": lease_deadline,
        "required_output_ids": _coerce_output_ids(canonical_task),
        "required_evidence_types": ["a2a.handoff_or_rejection"],
        "status": "active",
        "version": 1,
        "created_at": leased_task["updated_at"],
        "updated_at": leased_task["updated_at"],
    }
    return parse_declared_assignment_v1(assignment)


def build_product_developer_a2a_request(
    canonical_task: dict[str, Any],
    leased_task: dict[str, Any],
    source: dict[str, Any],
    assignment: dict[str, Any],
    requester_assignment: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    command = source["source_command"]
    payload = command["payload"]
    dispatch = leased_task["envelope"]["developer_dispatch"]
    trusted_binding = product_developer_trusted_binding(payload)
    trusted_reference_ids = {
        trusted_binding[field_name]
        for field_name in (
            "trusted_agent_profile_id",
            "trusted_agent_workspace_binding_id",
        )
        if field_name in trusted_binding
    }
    channel_digest = _stable_developer_digest(
        canonical_task["tenant_id"],
        payload["run_id"],
        canonical_task["task_id"],
    )
    channel_id = f"channel_{channel_digest[:40]}"
    message_id = (
        "a2amsg_"
        + _stable_developer_digest(channel_id, "1")[:40]
    )
    message = {
        "schema_id": "kolibri.a2a.message_appended.event",
        "schema_version": "1.0",
        "a2a_message_id": message_id,
        "tenant_id": canonical_task["tenant_id"],
        "goal_id": canonical_task["goal_id"],
        "case_id": canonical_task["case_id"],
        "task_id": canonical_task["task_id"],
        "task_version": canonical_task["version"],
        "channel_id": channel_id,
        "sequence": 1,
        "previous_message_id": None,
        "sender_actor_id": requester_assignment["assignee_actor_id"],
        "sender_assignment_id": requester_assignment["assignment_id"],
        "recipient_assignment_ids": [assignment["assignment_id"]],
        "recipient_capability": dispatch["runtime_capability"],
        "message_type": "request",
        "purpose": "Execute the Home-owned developer task.",
        "response_to_message_id": None,
        "content": {
            "trust": "untrusted_content",
            "text": developer_task_objective(
                source["source_command_ref"],
            ),
            "structured_data": {
                "expected_response": "a2a.handoff_or_rejection",
                "status": "requested",
                "source_command_ref": source["source_command_ref"],
                "runtime_profile": dispatch["runtime_profile"],
                "model": dispatch["model"],
                "reasoning_effort": dispatch["reasoning_effort"],
                "service_tier": dispatch["service_tier"],
                "workspace_ref": dispatch["workspace_ref"],
                "access_mode": dispatch["access_mode"],
                "sandbox": dispatch["sandbox"],
                "approval_policy": dispatch["approval_policy"],
                "reviewer": dispatch["reviewer"],
                **trusted_binding,
                "source_command_hash": source["command_hash"],
                "canonical_request_hash": source["request_hash"],
                "lease": {
                    "attempt_id": leased_task["attempt_id"],
                    "lease_id": leased_task["lease_id"],
                    "fencing_token": leased_task["fencing_token"],
                },
            },
            "reference_ids": sorted({
                source["source_command_ref"],
                canonical_task["task_id"],
                leased_task["attempt_id"],
                *trusted_reference_ids,
            }),
        },
        "content_hash": "sha256:" + ("0" * 64),
        "deduplication_key": (
            "a2a:developer-request:"
            + _stable_developer_digest(
                canonical_task["tenant_id"],
                canonical_task["task_id"],
                leased_task["attempt_id"],
            )
        ),
        "sent_at": leased_task["updated_at"],
        "expires_at": assignment["deadline_at"],
    }
    message["content_hash"] = a2a_content_hash(message)
    message = parse_declared_a2a_message_v1(message)
    cursor = {
        "schema_id": "kolibri.a2a.delivery_cursor",
        "schema_version": "1.0",
        "tenant_id": message["tenant_id"],
        "channel_id": message["channel_id"],
        "last_sequence": 1,
        "last_message_id": message["a2a_message_id"],
        "accepted_messages": {
            message["a2a_message_id"]: message["content_hash"],
        },
        "deduplication_index": {
            message["deduplication_key"]: {
                "message_id": message["a2a_message_id"],
                "content_hash": message["content_hash"],
            },
        },
    }
    cursor = parse_declared_a2a_cursor_v1(cursor)
    record = {
        "schema_id": "kolibri.a2a.home_delivery_record",
        "schema_version": "1.0",
        "source_command_ref": source["source_command_ref"],
        "message": message,
    }
    return message, cursor, record


def build_bound_product_developer_source_sidecar(
    canonical_task: dict[str, Any],
    leased_task: dict[str, Any],
    source: dict[str, Any],
    assignment: dict[str, Any],
) -> dict[str, Any]:
    """Bind the exact command to the selected assignment and lease fence."""

    trusted_binding = product_developer_trusted_binding(
        source["source_command"]["payload"],
    )
    return {
        "schema_id": (
            "kolibri.product.developer_lease_source.v1_1"
            if trusted_binding
            else "kolibri.product.developer_lease_source"
        ),
        "schema_version": "1.1" if trusted_binding else "1.0",
        "source_command_ref": source["source_command_ref"],
        "canonical_request_hash": source["request_hash"],
        "source_command_hash": source["command_hash"],
        "tenant_id": canonical_task["tenant_id"],
        "task_id": canonical_task["task_id"],
        "task_version": canonical_task["version"],
        "attempt_id": leased_task["attempt_id"],
        "assignment_id": assignment["assignment_id"],
        "effect_id": leased_task["effect_id"],
        "lease_id": leased_task["lease_id"],
        "fencing_token": leased_task["fencing_token"],
        "runtime_profile": source["runtime_profile"],
        "access_policy": source["access_policy"],
        **trusted_binding,
        "source_command": source["source_command"],
    }


def product_developer_effect_binding_error(
    task: dict[str, Any],
    attempt: dict[str, Any],
) -> str | None:
    """Verify the exact idempotent effect and lease binding end to end."""

    effect_id = str(task.get("effect_id") or "").strip()
    source_sidecar = task.get("source_command_sidecar")
    if not effect_id or not isinstance(source_sidecar, dict):
        return "effect_binding_missing"
    expected_bindings = {
        "task_id": task.get("task_id"),
        "attempt_id": task.get("attempt_id"),
        "assignment_id": task.get("assignment_id"),
        "effect_id": effect_id,
        "lease_id": task.get("lease_id"),
        "fencing_token": task.get("fencing_token"),
    }
    if attempt.get("effect_id") != effect_id:
        return "attempt_effect_id_mismatch"
    for field, expected in expected_bindings.items():
        if source_sidecar.get(field) != expected:
            return f"source_sidecar_{field}_mismatch"
    return None


def issue_task_lease(
    task: dict[str, Any],
    *,
    node_id: str,
    agent_id: str,
    slot_id: str | None,
    canonical_task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new opaque, durable lease identity for exactly one attempt."""
    leased = dict(task)
    leased["state"] = STATE_LEASED
    leased["attempt"] = int(leased.get("attempt", 0)) + 1
    if canonical_task is None:
        leased["attempt_id"] = f"{leased['task_id']}-attempt-{leased['attempt']}"
        leased["lease_id"] = uuid.uuid4().hex
    else:
        identity_seed = (
            f"{canonical_task['tenant_id']}:{leased['task_id']}:"
            f"{leased['attempt']}:{node_id}:{agent_id}"
        )
        digest = hashlib.sha256(identity_seed.encode("utf-8")).hexdigest()
        leased["attempt_id"] = f"attempt_{digest[:24]}"
        leased["assignment_id"] = f"assignment_{digest[24:48]}"
        leased["lease_id"] = f"lease_{uuid.uuid4().hex}"
    leased["lease_slot_id"] = slot_id
    leased["fencing_token"] = leased["attempt"]
    leased["lease_owner"] = f"{node_id}:{agent_id}"
    leased["lease_until"] = now_ts() + LEASE_DURATION
    leased["heartbeat_at"] = utc_now()
    leased["lease_contract_version"] = LEASE_CONTRACT_VERSION
    return leased


def claim_task_lease_atomically(
    task: dict[str, Any],
    *,
    node_id: str,
    agent_id: str,
    slot_id: str | None,
    canonical_task: dict[str, Any] | None = None,
    canonical_graph: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Issue exactly one lease across all control-plane processes."""

    leased = issue_task_lease(
        task,
        node_id=node_id,
        agent_id=agent_id,
        slot_id=slot_id,
        canonical_task=canonical_task,
    )
    developer_source: dict[str, Any] | None = None
    if canonical_task is not None:
        developer_source = load_product_developer_source(canonical_task)
        if developer_source is not None:
            assignment_digest = _stable_developer_digest(
                canonical_task["tenant_id"],
                canonical_task["task_id"],
                leased["attempt"],
                developer_source["runtime_profile"],
            )
            leased["assignment_id"] = (
                f"assignment_{assignment_digest[:40]}"
            )
        leased["current_assignment_id"] = leased["assignment_id"]
    leased["updated_at"] = utc_now()
    if canonical_task is not None:
        if canonical_graph is None:
            raise ValueError("canonical_graph_required")
        if (
            parse_iso_ts(leased["updated_at"]) or 0
        ) < (
            parse_iso_ts(canonical_task["updated_at"]) or 0
        ):
            leased["updated_at"] = canonical_task["updated_at"]
        transitioned_task = dict(canonical_task)
        transitioned_task["state"] = "leased"
        transitioned_task["version"] = int(canonical_task["version"]) + 1
        transitioned_task["current_attempt_id"] = leased["attempt_id"]
        transitioned_task["current_assignment_id"] = leased["assignment_id"]
        transitioned_task["updated_at"] = leased["updated_at"]
        transitioned_task = HOME_CONTRACTS_V1.prepare_outbound(
            transitioned_task,
            "kolibri.task",
        )
        leased["envelope"] = dict(leased["envelope"])
        leased["envelope"]["contract_v1"] = transitioned_task
        graph_service = task_graph_control_service()
        transitioned_graph = graph_service.project_task_transition(
            canonical_graph,
            transitioned_task,
            requested_at=leased["updated_at"],
        )
        graph_key = graph_service.graph_key(
            canonical_task["tenant_id"],
            canonical_graph["graph_id"],
        )
        expected_graph_json = redis.command("GET", graph_key)
        if expected_graph_json is None:
            return None
        if json.loads(expected_graph_json) != canonical_graph:
            return None
        previous_json = json.dumps(
            task,
            sort_keys=True,
            separators=(",", ":"),
        )
        transitioned_graph_json = json.dumps(
            transitioned_graph,
            sort_keys=True,
            separators=(",", ":"),
        )
        authority_id = os.environ.get(
            "FACTORY_CONTROL_AUTHORITY_ID",
            "auth_lhcp_runtime",
        )
        authority_epoch = int(os.environ.get(
            "FACTORY_CONTROL_AUTHORITY_EPOCH",
            "1",
        ))
        lease_expires_at = datetime.fromtimestamp(
            float(leased["lease_until"]),
            tz=timezone.utc,
        ).isoformat()
        execution_digest = hashlib.sha256(
            (
                f"{canonical_task['tenant_id']}:{task['task_id']}:"
                f"{leased['attempt_id']}:{node_id}:{agent_id}"
            ).encode("utf-8"),
            ).hexdigest()
        effect_id = (
            "effect_"
            + _stable_developer_digest(
                canonical_task["tenant_id"],
                (
                    developer_source["run_id"]
                    if developer_source is not None
                    else canonical_task["task_id"]
                ),
                canonical_task["task_id"],
            )[:40]
            if developer_source is not None
            else f"effect_{execution_digest[40:64]}"
        )
        leased["effect_id"] = effect_id
        runtime_agent_card: dict[str, Any] | None = None
        requester_agent_card: dict[str, Any] | None = None
        runtime_agent_card_raw: str | None = None
        requester_agent_card_raw: str | None = None
        canonical_agent_card: dict[str, Any] | None = None
        canonical_agent_card_raw: str | None = None
        if developer_source is not None:
            (
                runtime_agent_card,
                runtime_agent_card_raw,
            ) = resolve_product_developer_agent_card(
                transitioned_task,
                leased,
                developer_source,
            )
            (
                requester_agent_card,
                requester_agent_card_raw,
            ) = resolve_logical_home_requester_card(
                transitioned_task,
            )
        else:
            (
                canonical_agent_card,
                canonical_agent_card_raw,
            ) = resolve_canonical_execution_agent_card(
                transitioned_task,
                leased,
            )
        attempt_record = HOME_CONTRACTS_V1.prepare_outbound(
            {
                "schema_id": "kolibri.task_attempt",
                "schema_version": "1.0",
                "attempt_id": leased["attempt_id"],
                "tenant_id": canonical_task["tenant_id"],
                "goal_id": canonical_task["goal_id"],
                "case_id": canonical_task["case_id"],
                "task_id": canonical_task["task_id"],
                "attempt_number": leased["attempt"],
                "assignment_id": leased["assignment_id"],
                "status": "leased",
                "lease": {
                    "lease_id": leased["lease_id"],
                    "authority_id": authority_id,
                    "authority_epoch": authority_epoch,
                    "fencing_token": leased["fencing_token"],
                    "worker_id": f"worker_{execution_digest[:24]}",
                    "agent_card_id": (
                        runtime_agent_card["agent_card_id"]
                        if developer_source is not None
                        else canonical_agent_card["agent_card_id"]
                    ),
                    "acquired_at": leased["updated_at"],
                    "heartbeat_at": leased["updated_at"],
                    "expires_at": lease_expires_at,
                },
                "effect_id": effect_id,
                "result_artifact_refs": [],
                "result_hash": None,
                "error": None,
                "created_at": leased["updated_at"],
                "updated_at": leased["updated_at"],
            },
            "kolibri.task_attempt",
        )
        owner_state = HOME_CONTRACTS_V1.prepare_outbound(
            {
                "schema_id": "kolibri.task_owner_state",
                "schema_version": "1.0",
                "tenant_id": canonical_task["tenant_id"],
                "task_id": canonical_task["task_id"],
                "task_version": transitioned_task["version"],
                "current_status": "leased",
                "current_attempt_id": leased["attempt_id"],
                "current_assignment_id": leased["assignment_id"],
                "lease_id": leased["lease_id"],
                "authority_id": authority_id,
                "authority_epoch": authority_epoch,
                "fencing_token": leased["fencing_token"],
                "lease_expires_at": lease_expires_at,
                "committed_effects": {},
            },
            "kolibri.task_owner_state",
        )
        owner_state_key = key(
            "task_owner_state:"
            f"{canonical_task['tenant_id']}:{task['task_id']}",
        )
        expected_owner_state_raw = redis.command(
            "GET",
            owner_state_key,
        )
        if expected_owner_state_raw is not None:
            try:
                previous_owner_state = json.loads(
                    expected_owner_state_raw,
                )
            except json.JSONDecodeError:
                return None
            previous_attempt_id = str(
                task.get("attempt_id") or "",
            ).strip()
            previous_assignment_id = str(
                task.get("current_assignment_id")
                or task.get("assignment_id")
                or "",
            ).strip()
            if (
                not previous_attempt_id
                or not previous_assignment_id
                or previous_owner_state.get("tenant_id")
                != canonical_task["tenant_id"]
                or previous_owner_state.get("task_id")
                != canonical_task["task_id"]
                or previous_owner_state.get("current_attempt_id")
                != previous_attempt_id
                or previous_owner_state.get("current_assignment_id")
                != previous_assignment_id
                or previous_owner_state.get("authority_id")
                != authority_id
                or int(
                    previous_owner_state.get("authority_epoch") or 0,
                ) != authority_epoch
            ):
                return None
        if developer_source is not None:
            assignment = build_product_developer_assignment(
                transitioned_task,
                leased,
                developer_source,
                agent_card=runtime_agent_card,
            )
            requester_assignment = (
                build_logical_home_requester_assignment(
                    transitioned_task,
                    leased,
                    developer_source,
                    agent_card=requester_agent_card,
                )
            )
            request_message, request_cursor, request_record = (
                build_product_developer_a2a_request(
                    transitioned_task,
                    leased,
                    developer_source,
                    assignment,
                    requester_assignment,
                )
            )
            source_sidecar = (
                build_bound_product_developer_source_sidecar(
                    transitioned_task,
                    leased,
                    developer_source,
                    assignment,
                )
            )
            # Project the exact Home-owned durable attempt into the lease
            # response. AgentHost forwards this typed record to Provider
            # Execution; it must never reconstruct an authority record from
            # loose wrapper fields.
            leased["task_attempt"] = attempt_record
            leased["agent_assignment"] = assignment
            leased["requester_assignment"] = requester_assignment
            leased["a2a_request"] = request_message
            leased["source_command_sidecar"] = source_sidecar
            leased_json = json.dumps(
                leased,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            source_key = product_developer_source_key(
                canonical_task["tenant_id"],
                canonical_task["task_id"],
            )
            source_json = redis.command("GET", source_key)
            if source_json is None:
                return None
            reply = redis.command(
                "EVAL",
                PRODUCT_DEVELOPER_CANONICAL_LEASE_LUA,
                18,
                task_key(task["task_id"]),
                key("queue"),
                key("active_lease_ids"),
                graph_key,
                key(
                    "task_attempt:"
                    f"{canonical_task['tenant_id']}:{leased['attempt_id']}",
                ),
                key(
                    "task_owner_state:"
                    f"{canonical_task['tenant_id']}:{task['task_id']}",
                ),
                source_key,
                assignment_key(assignment["assignment_id"]),
                assignment_key(
                    requester_assignment["assignment_id"],
                ),
                assignment_ids_key(),
                assignment_task_index_key(task["task_id"]),
                a2a_message_id_key(request_message["a2a_message_id"]),
                a2a_cursor_key(
                    canonical_task["tenant_id"],
                    request_message["channel_id"],
                ),
                a2a_channel_messages_key(
                    canonical_task["tenant_id"],
                    request_message["channel_id"],
                ),
                a2a_agent_card_key(
                    runtime_agent_card["agent_card_id"],
                ),
                a2a_agent_card_key(
                    requester_agent_card["agent_card_id"],
                ),
                a2a_agent_card_active_assignments_key(
                    runtime_agent_card["agent_card_id"],
                ),
                a2a_agent_card_active_assignments_key(
                    requester_agent_card["agent_card_id"],
                ),
                previous_json,
                leased_json,
                int(task.get("attempt", 0)),
                expected_graph_json,
                task["task_id"],
                transitioned_graph_json,
                json.dumps(
                    attempt_record,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                json.dumps(
                    owner_state,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                source_json,
                json.dumps(
                    assignment,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                json.dumps(
                    requester_assignment,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                assignment["assignment_id"],
                requester_assignment["assignment_id"],
                json.dumps(
                    request_record,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ),
                json.dumps(
                    request_cursor,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                request_message["a2a_message_id"],
                runtime_agent_card_raw,
                requester_agent_card_raw,
                int(
                    runtime_agent_card["limits"][
                        "max_concurrent_assignments"
                    ],
                ),
                int(
                    requester_agent_card["limits"][
                        "max_concurrent_assignments"
                    ],
                ),
            )
            if str(reply[0]) != "committed":
                return None
            return json.loads(reply[1])
        assignment = build_canonical_task_assignment(
            transitioned_task,
            leased,
            agent_card=canonical_agent_card,
        )
        leased["agent_assignment"] = assignment
        leased_json = json.dumps(
            leased,
            sort_keys=True,
            separators=(",", ":"),
        )
        reply = redis.command(
            "EVAL",
            CANONICAL_EXECUTION_TASK_LEASE_LUA,
            11,
            task_key(task["task_id"]),
            key("queue"),
            key("active_lease_ids"),
            graph_key,
            key(
                "task_attempt:"
                f"{canonical_task['tenant_id']}:{leased['attempt_id']}",
            ),
            owner_state_key,
            assignment_key(assignment["assignment_id"]),
            assignment_ids_key(),
            assignment_task_index_key(task["task_id"]),
            a2a_agent_card_key(
                canonical_agent_card["agent_card_id"],
            ),
            a2a_agent_card_active_assignments_key(
                canonical_agent_card["agent_card_id"],
            ),
            previous_json,
            leased_json,
            int(task.get("attempt", 0)),
            expected_graph_json,
            task["task_id"],
            transitioned_graph_json,
            json.dumps(attempt_record, sort_keys=True, separators=(",", ":")),
            json.dumps(owner_state, sort_keys=True, separators=(",", ":")),
            _json_record(assignment),
            assignment["assignment_id"],
            canonical_agent_card_raw,
            expected_owner_state_raw or "__kolibri_missing__",
            int(
                canonical_agent_card["limits"][
                    "max_concurrent_assignments"
                ],
            ),
        )
        if str(reply[0]) != "committed":
            return None
        return json.loads(reply[1])
    reply = redis.command(
        "EVAL",
        EXECUTION_TASK_LEASE_LUA,
        3,
        task_key(task["task_id"]),
        key("queue"),
        key("active_lease_ids"),
        int(task.get("attempt", 0)),
        json.dumps(leased, sort_keys=True, separators=(",", ":")),
        task["task_id"],
    )
    if str(reply[0]) != "committed":
        return None
    return json.loads(reply[1])


def _canonical_execution_result_hash(result: dict[str, Any]) -> str:
    payload = json.dumps(
        result,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def rebase_canonical_task_graph_version(
    canonical_task: dict[str, Any],
    canonical_graph: dict[str, Any],
) -> dict[str, Any]:
    """Rebase only a task's graph revision after a same-case graph append."""

    graph_task = next(
        (
            task
            for task in canonical_graph["tasks"]
            if task["task_id"] == canonical_task["task_id"]
        ),
        None,
    )
    if graph_task is None:
        raise DeclaredContractV1Error(
            "contract_binding_mismatch",
            [{
                "path": "/contract_v1/task_id",
                "code": "canonical_graph_task_missing",
            }],
        )
    rebased_task = {
        **canonical_task,
        "graph_version": canonical_graph["graph_version"],
    }
    rebased_task = HOME_CONTRACTS_V1.prepare_outbound(
        rebased_task,
        "kolibri.task",
    )
    if rebased_task != graph_task:
        raise DeclaredContractV1Error(
            "contract_binding_mismatch",
            [{
                "path": "/contract_v1",
                "code": "canonical_graph_task_revision_mismatch",
            }],
        )
    return rebased_task


def _canonical_execution_transition_projection(
    canonical_task: dict[str, Any],
    canonical_graph: dict[str, Any],
    states: tuple[str, ...],
    *,
    requested_at: str,
    clear_current: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    task = rebase_canonical_task_graph_version(
        canonical_task,
        canonical_graph,
    )
    graph = canonical_graph
    graph_service = task_graph_control_service()
    for state in states:
        task = {
            **task,
            "state": state,
            "version": int(task["version"]) + 1,
            "updated_at": requested_at,
        }
        if clear_current:
            task["current_attempt_id"] = None
            task["current_assignment_id"] = None
        task = HOME_CONTRACTS_V1.prepare_outbound(
            task,
            "kolibri.task",
        )
        graph = graph_service.project_task_transition(
            graph,
            task,
            requested_at=requested_at,
        )
    return task, graph


def assignment_projection_matches_registry(
    assignment: dict[str, Any],
    projection: dict[str, Any],
    *,
    allow_control_plane_revocation: bool,
) -> bool:
    if assignment == projection:
        return True
    if (
        not allow_control_plane_revocation
        or assignment.get("status") != "revoked"
        or projection.get("status") != "active"
        or int(assignment.get("version") or 0)
        != int(projection.get("version") or 0) + 1
    ):
        return False
    projected = copy.deepcopy(projection)
    revoked = copy.deepcopy(assignment)
    for candidate in (projected, revoked):
        candidate.pop("status", None)
        candidate.pop("version", None)
        candidate.pop("updated_at", None)
    return revoked == projected


def _load_canonical_execution_durable_state(
    task: dict[str, Any],
    *,
    require_available_card: bool,
    require_active_assignment: bool = True,
) -> dict[str, Any]:
    canonical_task = parse_declared_contract_v1(
        task.get("envelope", {}),
        "kolibri.task",
        bound_id=str(task["task_id"]),
    )
    if canonical_task is None or is_product_developer_task(task):
        raise DeclaredContractV1Error(
            "canonical_task_transition_required",
            [{"path": "/task", "code": "unsupported"}],
        )
    canonical_graph = authoritative_graph_for_canonical_task(
        canonical_task,
        require_runnable=False,
    )
    assignment_projection = task.get("agent_assignment")
    assignment_id = str(
        task.get("current_assignment_id")
        or task.get("assignment_id")
        or "",
    ).strip()
    attempt_id = str(task.get("attempt_id") or "").strip()
    if (
        not assignment_id
        or not attempt_id
        or not isinstance(assignment_projection, dict)
    ):
        raise DeclaredContractV1Error(
            "canonical_execution_durable_state_missing",
            [{"path": "/task", "code": "lease_projection_missing"}],
        )
    tenant_id = canonical_task["tenant_id"]
    graph_key = task_graph_control_service().graph_key(
        tenant_id,
        canonical_graph["graph_id"],
    )
    attempt_key = key(f"task_attempt:{tenant_id}:{attempt_id}")
    owner_key = key(
        f"task_owner_state:{tenant_id}:{task['task_id']}",
    )
    assignment_record_key = assignment_key(assignment_id)
    task_raw = redis.command("GET", task_key(task["task_id"]))
    graph_raw = redis.command("GET", graph_key)
    attempt_raw = redis.command("GET", attempt_key)
    owner_raw = redis.command("GET", owner_key)
    assignment_raw = redis.command("GET", assignment_record_key)
    if any(
        value is None
        for value in (
            task_raw,
            graph_raw,
            attempt_raw,
            owner_raw,
            assignment_raw,
        )
    ):
        raise DeclaredContractV1Error(
            "canonical_execution_durable_state_missing",
            [{"path": "/task", "code": "durable_record_missing"}],
        )
    stored_task = json.loads(task_raw)
    if stored_task != task:
        raise DeclaredContractV1Error(
            "stale_or_invalid_lease",
            [{"path": "/task", "code": "stale_task_revision"}],
        )
    attempt = HOME_CONTRACTS_V1.prepare_outbound(
        json.loads(attempt_raw),
        "kolibri.task_attempt",
    )
    owner_state = HOME_CONTRACTS_V1.prepare_outbound(
        json.loads(owner_raw),
        "kolibri.task_owner_state",
    )
    assignment = parse_declared_assignment_v1(
        json.loads(assignment_raw),
    )
    card_id = str(assignment.get("agent_card_id") or "").strip()
    card_key = a2a_agent_card_key(card_id)
    card_raw = redis.command("GET", card_key)
    card = None
    if card_raw is not None:
        card = parse_declared_a2a_agent_card_v1(
            json.loads(card_raw),
        )
    assignment_error = (
        validate_task_assignment_state(task)
        if require_active_assignment
        else None
    )
    lease = attempt.get("lease") or {}
    authority = assignment.get("authority_profile") or {}
    allowed_refs = set(authority.get("allowed_resource_refs") or [])
    required_refs = {
        canonical_task["goal_id"],
        canonical_task["case_id"],
        canonical_task["task_id"],
    }
    assignment_projection_matches = (
        assignment_projection_matches_registry(
            assignment,
            assignment_projection,
            allow_control_plane_revocation=not require_active_assignment,
        )
    )
    binding_error = None
    if assignment_error:
        binding_error = assignment_error
    elif not assignment_projection_matches:
        binding_error = "assignment_projection_mismatch"
    elif task.get("assignment_id") != assignment_id:
        binding_error = "assignment_id_mismatch"
    elif canonical_task.get("current_attempt_id") != attempt_id:
        binding_error = "canonical_attempt_id_mismatch"
    elif canonical_task.get("current_assignment_id") != assignment_id:
        binding_error = "canonical_assignment_id_mismatch"
    elif attempt.get("attempt_id") != attempt_id:
        binding_error = "attempt_id_mismatch"
    elif attempt.get("assignment_id") != assignment_id:
        binding_error = "attempt_assignment_id_mismatch"
    elif attempt.get("status") != canonical_task.get("state"):
        binding_error = "attempt_status_mismatch"
    elif attempt.get("effect_id") != task.get("effect_id"):
        binding_error = "attempt_effect_id_mismatch"
    elif lease.get("lease_id") != task.get("lease_id"):
        binding_error = "attempt_lease_id_mismatch"
    elif lease.get("fencing_token") != task.get("fencing_token"):
        binding_error = "attempt_fencing_token_mismatch"
    elif lease.get("agent_card_id") != card_id:
        binding_error = "attempt_agent_card_id_mismatch"
    elif owner_state.get("tenant_id") != tenant_id:
        binding_error = "owner_tenant_id_mismatch"
    elif owner_state.get("task_id") != task.get("task_id"):
        binding_error = "owner_task_id_mismatch"
    elif owner_state.get("task_version") != canonical_task.get("version"):
        binding_error = "owner_task_version_mismatch"
    elif owner_state.get("current_status") != canonical_task.get("state"):
        binding_error = "owner_status_mismatch"
    elif owner_state.get("current_attempt_id") != attempt_id:
        binding_error = "owner_attempt_id_mismatch"
    elif owner_state.get("current_assignment_id") != assignment_id:
        binding_error = "owner_assignment_id_mismatch"
    elif owner_state.get("lease_id") != task.get("lease_id"):
        binding_error = "owner_lease_id_mismatch"
    elif owner_state.get("fencing_token") != task.get("fencing_token"):
        binding_error = "owner_fencing_token_mismatch"
    elif assignment.get("attempt_id") != attempt_id:
        binding_error = "assignment_attempt_id_mismatch"
    elif assignment.get("lease_id") != task.get("lease_id"):
        binding_error = "assignment_lease_id_mismatch"
    elif assignment.get("task_version") != canonical_task.get("version"):
        binding_error = "assignment_task_version_mismatch"
    elif not required_refs.issubset(allowed_refs):
        binding_error = "assignment_resource_scope_mismatch"
    elif require_available_card and card is None:
        binding_error = "agent_card_not_found"
    elif (
        require_available_card
        and
        card is not None
        and assignment.get("agent_card_version") != card.get("version")
    ):
        binding_error = "agent_card_version_mismatch"
    elif (
        require_available_card
        and card is not None
        and card.get("availability") != "available"
    ):
        binding_error = "agent_card_unavailable"
    elif require_available_card and card is not None and not set(
        authority.get("capabilities") or [],
    ).issubset(
        set(card.get("capabilities") or []),
    ):
        binding_error = "agent_card_capability_mismatch"
    elif require_available_card and card is not None and not set(
        authority.get("allowed_tool_ids") or [],
    ).issubset(
        set(card.get("tool_ids") or []),
    ):
        binding_error = "agent_card_tool_mismatch"
    elif require_available_card and card is not None and int(
        (assignment.get("context_slice") or {}).get("max_bytes") or 0,
    ) > int((card.get("limits") or {}).get("max_context_bytes") or 0):
        binding_error = "agent_card_context_limit_exceeded"
    if binding_error:
        raise DeclaredContractV1Error(
            "stale_or_invalid_assignment",
            [{"path": "/assignment", "code": binding_error}],
        )
    return {
        "task": task,
        "canonical_task": canonical_task,
        "canonical_graph": canonical_graph,
        "attempt": attempt,
        "owner_state": owner_state,
        "assignment": assignment,
        "agent_card": card,
        "keys": {
            "task": task_key(task["task_id"]),
            "graph": graph_key,
            "attempt": attempt_key,
            "owner": owner_key,
            "assignment": assignment_record_key,
            "card": card_key,
        },
        "raws": {
            "task": task_raw,
            "graph": graph_raw,
            "attempt": attempt_raw,
            "owner": owner_raw,
            "assignment": assignment_raw,
            "card": card_raw,
        },
    }


def _commit_canonical_execution_records(
    durable: dict[str, Any],
    *,
    task: dict[str, Any],
    graph: dict[str, Any],
    attempt: dict[str, Any],
    owner_state: dict[str, Any],
    assignment: dict[str, Any],
    active_action: str,
    queue_action: str,
    assignment_action: str,
) -> dict[str, Any] | None:
    assignment = parse_declared_assignment_v1(assignment)
    attempt = HOME_CONTRACTS_V1.prepare_outbound(
        attempt,
        "kolibri.task_attempt",
    )
    owner_state = HOME_CONTRACTS_V1.prepare_outbound(
        owner_state,
        "kolibri.task_owner_state",
    )
    keys = durable["keys"]
    raws = durable["raws"]
    reply = redis.command(
        "EVAL",
        CANONICAL_EXECUTION_TASK_MUTATION_LUA,
        12,
        keys["task"],
        key("active_lease_ids"),
        key("queue"),
        key("dead_letter"),
        keys["graph"],
        keys["attempt"],
        keys["owner"],
        keys["assignment"],
        keys["card"],
        assignment_ids_key(),
        assignment_task_index_key(task["task_id"]),
        a2a_agent_card_active_assignments_key(
            assignment["agent_card_id"],
        ),
        raws["task"],
        json.dumps(task, sort_keys=True, separators=(",", ":")),
        raws["graph"],
        json.dumps(graph, sort_keys=True, separators=(",", ":")),
        raws["attempt"],
        _json_record(attempt),
        raws["owner"],
        _json_record(owner_state),
        raws["assignment"],
        _json_record(assignment),
        raws["card"] or "__kolibri_missing__",
        task["task_id"],
        assignment["assignment_id"],
        active_action,
        queue_action,
        assignment_action,
    )
    if str(reply[0]) != "committed":
        return None
    return json.loads(reply[1])


def heartbeat_canonical_execution_task_atomically(
    task: dict[str, Any],
    body: dict[str, Any],
) -> dict[str, Any]:
    requested_state = body.get("state")
    if requested_state not in {None, "", STATE_RUNNING}:
        raise DeclaredContractV1Error(
            "invalid_heartbeat_state",
            [{
                "path": "/state",
                "code": "heartbeat_state_must_be_running",
            }],
        )
    task_id = str(task["task_id"])
    for _ in range(5):
        current = load_task(task_id)
        if current is None:
            raise DeclaredContractV1Error(
                "task_not_found",
                [{"path": "/task_id", "code": "not_found"}],
            )
        fence_error = validate_task_mutation_fence(current, body)
        if fence_error:
            raise DeclaredContractV1Error(
                "stale_or_invalid_lease",
                [{"path": "/lease", "code": fence_error}],
            )
        if current.get("state") in TERMINAL_STATES:
            return current
        durable = _load_canonical_execution_durable_state(
            current,
            require_available_card=True,
        )
        canonical_task = durable["canonical_task"]
        if canonical_task["state"] not in {"leased", "running"}:
            raise DeclaredContractV1Error(
                "canonical_task_transition_conflict",
                [{"path": "/task/state", "code": "lease_required"}],
            )
        heartbeat_at = utc_now()
        lease_until = now_ts() + LEASE_DURATION
        lease_expires_at = datetime.fromtimestamp(
            lease_until,
            tz=timezone.utc,
        ).isoformat()
        states = (
            ("running",)
            if canonical_task["state"] == "leased"
            else ()
        )
        transitioned_task, transitioned_graph = (
            _canonical_execution_transition_projection(
                canonical_task,
                durable["canonical_graph"],
                states,
                requested_at=heartbeat_at,
            )
        )
        updated_task = copy.deepcopy(current)
        updated_task.update({
            "state": STATE_RUNNING,
            "heartbeat_at": heartbeat_at,
            "lease_until": lease_until,
            "pid": body.get("pid", current.get("pid")),
            "worktree": body.get(
                "worktree",
                current.get("worktree"),
            ),
            "branch": body.get("branch", current.get("branch")),
            "log_paths": body.get(
                "log_paths",
                current.get("log_paths"),
            ),
            "updated_at": heartbeat_at,
        })
        updated_task["envelope"] = dict(updated_task["envelope"])
        updated_task["envelope"]["contract_v1"] = transitioned_task
        attempt = copy.deepcopy(durable["attempt"])
        attempt["status"] = "running"
        attempt["lease"]["heartbeat_at"] = heartbeat_at
        attempt["lease"]["expires_at"] = lease_expires_at
        attempt["updated_at"] = heartbeat_at
        owner_state = copy.deepcopy(durable["owner_state"])
        owner_state["task_version"] = transitioned_task["version"]
        owner_state["current_status"] = "running"
        owner_state["lease_expires_at"] = lease_expires_at
        assignment = copy.deepcopy(durable["assignment"])
        assignment["task_version"] = transitioned_task["version"]
        assignment["deadline_at"] = lease_expires_at
        assignment["authority_profile"]["expires_at"] = (
            lease_expires_at
        )
        assignment["version"] = int(assignment["version"]) + 1
        assignment["updated_at"] = heartbeat_at
        updated_task["agent_assignment"] = assignment
        committed = _commit_canonical_execution_records(
            durable,
            task=updated_task,
            graph=transitioned_graph,
            attempt=attempt,
            owner_state=owner_state,
            assignment=assignment,
            active_action="add",
            queue_action="remove",
            assignment_action="keep",
        )
        if committed is not None:
            return committed
    raise DeclaredContractV1Error(
        "stale_or_invalid_lease",
        [{"path": "/lease", "code": "stale_task_revision"}],
    )


def commit_canonical_execution_terminal_atomically(
    task: dict[str, Any],
    body: dict[str, Any],
    *,
    success: bool,
) -> dict[str, Any] | None:
    task_id = str(task["task_id"])
    for _ in range(5):
        current = load_task(task_id)
        if current is None:
            raise DeclaredContractV1Error(
                "task_not_found",
                [{"path": "/task_id", "code": "not_found"}],
            )
        fence_error = validate_task_mutation_fence(current, body)
        if fence_error:
            raise DeclaredContractV1Error(
                "stale_or_invalid_lease",
                [{"path": "/lease", "code": fence_error}],
            )
        if current.get("state") in TERMINAL_STATES:
            return current
        durable = _load_canonical_execution_durable_state(
            current,
            require_available_card=True,
        )
        canonical_task = durable["canonical_task"]
        if canonical_task["state"] not in {"leased", "running"}:
            raise DeclaredContractV1Error(
                "canonical_task_transition_conflict",
                [{"path": "/task/state", "code": "lease_required"}],
            )
        requested_at = utc_now()
        result = body.get("result", body) if success else body.get("result")
        if result is not None and not isinstance(result, dict):
            raise DeclaredContractV1Error(
                "invalid_result",
                [{"path": "/result", "code": "type"}],
            )
        if success:
            states = (
                ("running", "submitted", "verifying", "completed")
                if canonical_task["state"] == "leased"
                else ("submitted", "verifying", "completed")
            )
            queue_action = "remove"
        else:
            retry = (
                int(current.get("attempt", 0))
                < int(current.get("max_retries", MAX_RETRIES))
                and body.get("retry", True)
            )
            states = (
                ("failed_retryable",)
                if retry
                else ("failed_retryable", "failed_terminal")
            )
            queue_action = "enqueue" if retry else "remove"
        transitioned_task, transitioned_graph = (
            _canonical_execution_transition_projection(
                canonical_task,
                durable["canonical_graph"],
                states,
                requested_at=requested_at,
                clear_current=not success,
            )
        )
        updated_task = copy.deepcopy(current)
        updated_task["result"] = result
        updated_task["result_reference"] = (
            body.get("result_reference")
            or ((result or {}).get("result_path"))
        )
        updated_task["heartbeat_at"] = requested_at
        updated_task["updated_at"] = requested_at
        updated_task["envelope"] = dict(updated_task["envelope"])
        updated_task["envelope"]["contract_v1"] = transitioned_task
        attempt = copy.deepcopy(durable["attempt"])
        owner_state = copy.deepcopy(durable["owner_state"])
        assignment = copy.deepcopy(durable["assignment"])
        assignment["task_version"] = transitioned_task["version"]
        assignment["version"] = int(assignment["version"]) + 1
        assignment["updated_at"] = requested_at
        owner_state["task_version"] = transitioned_task["version"]
        owner_state["current_status"] = transitioned_task["state"]
        if success:
            result_hash = _canonical_execution_result_hash(result or {})
            updated_task["state"] = STATE_COMPLETED
            updated_task["error_type"] = None
            updated_task["error"] = None
            updated_task["lease_until"] = None
            attempt["status"] = "completed"
            attempt["result_hash"] = result_hash
            attempt["error"] = None
            owner_state["committed_effects"] = {
                **owner_state["committed_effects"],
                attempt["effect_id"]: {
                    "attempt_id": attempt["attempt_id"],
                    "result_hash": result_hash,
                },
            }
            assignment["status"] = "completed"
            preserve_terminal_lease_evidence(updated_task)
        else:
            error_type = str(
                body.get("error_type") or "runtime_error",
            )
            error_message = (
                str(body.get("error") or "").strip()
                or "Canonical execution failed."
            )
            retryable = queue_action == "enqueue"
            updated_task["state"] = (
                STATE_QUEUED if retryable else STATE_FAILED
            )
            updated_task["error_type"] = error_type
            updated_task["error"] = error_message
            updated_task["lease_until"] = None
            attempt["status"] = (
                "failed_retryable"
                if retryable
                else "failed_terminal"
            )
            attempt["error"] = {
                "error_type": error_type,
                "message": error_message[:2000],
                "retryable": retryable,
            }
            assignment["status"] = (
                "expired" if retryable else "superseded"
            )
            if retryable:
                updated_task["lease_owner"] = None
                updated_task["lease_id"] = None
                updated_task["lease_slot_id"] = None
                updated_task["current_assignment_id"] = None
                updated_task.pop("agent_assignment", None)
            else:
                preserve_terminal_lease_evidence(updated_task)
        attempt["updated_at"] = requested_at
        if updated_task.get("agent_assignment") is not None:
            updated_task["agent_assignment"] = assignment
        committed = _commit_canonical_execution_records(
            durable,
            task=updated_task,
            graph=transitioned_graph,
            attempt=attempt,
            owner_state=owner_state,
            assignment=assignment,
            active_action="remove",
            queue_action=queue_action,
            assignment_action="remove",
        )
        if committed is not None:
            return committed
    return None


def expire_canonical_execution_task_atomically(
    task: dict[str, Any],
    *,
    retry: bool,
) -> dict[str, Any] | None:
    """Close an expired canonical lease and every authority projection."""

    task_id = str(task["task_id"])
    for _ in range(5):
        current = load_task(task_id)
        if (
            current is None
            or current.get("state") not in ACTIVE_LEASE_STATES
        ):
            return None
        if float(current.get("lease_until") or 0) >= now_ts():
            return None
        durable = _load_canonical_execution_durable_state(
            current,
            require_available_card=False,
            require_active_assignment=False,
        )
        canonical_task = durable["canonical_task"]
        if canonical_task["state"] not in {"leased", "running"}:
            return None
        requested_at = utc_now()
        states = (
            ("failed_retryable",)
            if retry
            else ("failed_retryable", "failed_terminal")
        )
        transitioned_task, transitioned_graph = (
            _canonical_execution_transition_projection(
                canonical_task,
                durable["canonical_graph"],
                states,
                requested_at=requested_at,
                clear_current=True,
            )
        )
        updated_task = copy.deepcopy(current)
        updated_task["state"] = STATE_QUEUED if retry else STATE_DEAD
        updated_task["error_type"] = "lease_expired"
        updated_task["error"] = (
            "lease expired before task completion"
            if retry
            else "lease expired and retry budget exhausted"
        )
        updated_task["heartbeat_at"] = requested_at
        updated_task["updated_at"] = requested_at
        updated_task["envelope"] = dict(updated_task["envelope"])
        updated_task["envelope"]["contract_v1"] = transitioned_task
        if not retry:
            preserve_terminal_lease_evidence(updated_task)
        updated_task["lease_owner"] = None
        updated_task["lease_id"] = None
        updated_task["lease_slot_id"] = None
        updated_task["lease_until"] = None
        updated_task["current_assignment_id"] = None
        updated_task.pop("agent_assignment", None)
        attempt = copy.deepcopy(durable["attempt"])
        attempt["status"] = "expired"
        attempt["error"] = {
            "error_type": "lease_expired",
            "message": updated_task["error"],
            "retryable": retry,
        }
        attempt["updated_at"] = requested_at
        owner_state = copy.deepcopy(durable["owner_state"])
        owner_state["task_version"] = transitioned_task["version"]
        owner_state["current_status"] = transitioned_task["state"]
        owner_state["lease_expires_at"] = requested_at
        assignment = copy.deepcopy(durable["assignment"])
        if assignment.get("status") != "revoked":
            assignment["task_version"] = transitioned_task["version"]
            assignment["status"] = (
                "expired" if retry else "superseded"
            )
            assignment["version"] = int(assignment["version"]) + 1
            assignment["updated_at"] = requested_at
        committed = _commit_canonical_execution_records(
            durable,
            task=updated_task,
            graph=transitioned_graph,
            attempt=attempt,
            owner_state=owner_state,
            assignment=assignment,
            active_action="remove",
            queue_action="enqueue" if retry else "dead",
            assignment_action="remove",
        )
        if committed is not None:
            return committed
    return None


def commit_fenced_task_mutation(
    previous: dict[str, Any],
    updated: dict[str, Any],
    *,
    active: bool,
    enqueue_after: bool = False,
) -> dict[str, Any] | None:
    """CAS one fenced mutation so stale workers cannot overwrite a winner."""

    updated["updated_at"] = utc_now()
    previous_json = json.dumps(
        previous,
        sort_keys=True,
        separators=(",", ":"),
    )
    updated_json = json.dumps(
        updated,
        sort_keys=True,
        separators=(",", ":"),
    )
    reply = redis.command(
        "EVAL",
        EXECUTION_TASK_FENCED_MUTATION_LUA,
        3,
        task_key(previous["task_id"]),
        key("active_lease_ids"),
        key("queue"),
        previous_json,
        updated_json,
        previous["task_id"],
        "1" if active else "0",
        "1" if enqueue_after else "0",
    )
    if str(reply[0]) != "committed":
        return None
    return json.loads(reply[1])


def is_product_developer_task(task: dict[str, Any]) -> bool:
    envelope = task.get("envelope")
    if not isinstance(envelope, dict):
        return False
    source = envelope.get("source")
    dispatch = envelope.get("developer_dispatch")
    source_kind = (
        source.get("kind") if isinstance(source, dict) else None
    )
    dispatch_contract = (
        (
            dispatch.get("schema_id"),
            dispatch.get("schema_version"),
        )
        if isinstance(dispatch, dict)
        else (None, None)
    )
    return (
        isinstance(source, dict)
        and source_kind
        in {"product_run_execute_v1_2", "product_run_execute_v1_3"}
        and isinstance(dispatch, dict)
        and (
            (source_kind, dispatch_contract)
            in {
                (
                    "product_run_execute_v1_2",
                    ("kolibri.product.developer_dispatch", "1.0"),
                ),
                (
                    "product_run_execute_v1_3",
                    (
                        "kolibri.product.developer_dispatch.v1_1",
                        "1.1",
                    ),
                ),
            }
        )
    )


def product_developer_agent_card_binding_error(
    card: dict[str, Any] | None,
    assignment: dict[str, Any],
    *,
    require_available_revision: bool,
    runtime_profile: str | None = None,
) -> str | None:
    if card is None:
        return (
            "agent_card_not_found"
            if require_available_revision
            else None
        )
    if card.get("agent_card_id") != assignment.get("agent_card_id"):
        return "agent_card_id_mismatch"
    if not require_available_revision:
        return None
    if card.get("availability") != "available":
        return "agent_card_unavailable"
    if int(card.get("version") or 0) != int(
        assignment.get("agent_card_version") or 0,
    ):
        return "agent_card_version_mismatch"
    authority = assignment.get("authority_profile") or {}
    if not set(authority.get("capabilities") or []).issubset(
        set(card.get("capabilities") or []),
    ):
        return "agent_card_capability_mismatch"
    if not set(authority.get("allowed_tool_ids") or []).issubset(
        set(card.get("tool_ids") or []),
    ):
        return "agent_card_tool_mismatch"
    if int(
        (assignment.get("context_slice") or {}).get("max_bytes") or 0,
    ) > int((card.get("limits") or {}).get("max_context_bytes") or 0):
        return "agent_card_context_limit_exceeded"
    if (
        runtime_profile is not None
        and developer_agent_card_runtime_profile(card)
        != runtime_profile
    ):
        return "agent_card_runtime_profile_mismatch"
    return None


def heartbeat_product_developer_task_atomically(
    task: dict[str, Any],
    body: dict[str, Any],
) -> dict[str, Any]:
    """Extend one developer lease and both authority assignments atomically."""

    requested_state = body.get("state")
    if requested_state not in {None, "", STATE_RUNNING}:
        raise DeclaredContractV1Error(
            "invalid_heartbeat_state",
            [{
                "path": "/state",
                "code": "heartbeat_state_must_be_running",
            }],
        )
    task_id = str(task["task_id"])
    for _ in range(5):
        current = load_task(task_id)
        if current is None:
            raise DeclaredContractV1Error(
                "task_not_found",
                [{"path": "/task_id", "code": "not_found"}],
            )
        fence_error = validate_task_mutation_fence(current, body)
        if fence_error:
            raise DeclaredContractV1Error(
                "stale_or_invalid_lease",
                [{"path": "/lease", "code": fence_error}],
            )
        if current.get("state") in TERMINAL_STATES:
            return current
        canonical_task = parse_declared_contract_v1(
            current.get("envelope", {}),
            "kolibri.task",
            bound_id=task_id,
        )
        if (
            canonical_task is None
            or canonical_task.get("state") not in {"leased", "running"}
            or not is_product_developer_task(current)
        ):
            raise DeclaredContractV1Error(
                "canonical_task_transition_required",
                [{"path": "/task", "code": "unsupported"}],
            )
        canonical_graph = authoritative_graph_for_canonical_task(
            canonical_task,
            require_runnable=False,
        )
        assignment_projection = current.get("agent_assignment")
        requester_projection = current.get("requester_assignment")
        if (
            not isinstance(assignment_projection, dict)
            or not isinstance(requester_projection, dict)
        ):
            raise DeclaredContractV1Error(
                "stale_or_invalid_assignment",
                [{"path": "/assignment", "code": "missing"}],
            )
        assignment_id = str(
            assignment_projection.get("assignment_id") or "",
        )
        requester_assignment_id = str(
            requester_projection.get("assignment_id") or "",
        )
        tenant_id = canonical_task["tenant_id"]
        attempt_key = key(
            "task_attempt:"
            f"{tenant_id}:{current['attempt_id']}",
        )
        owner_key = key(
            f"task_owner_state:{tenant_id}:{task_id}",
        )
        runtime_assignment_key = assignment_key(assignment_id)
        requester_assignment_key = assignment_key(
            requester_assignment_id,
        )
        runtime_card_key = a2a_agent_card_key(
            str(assignment_projection.get("agent_card_id") or ""),
        )
        requester_card_key = a2a_agent_card_key(
            str(requester_projection.get("agent_card_id") or ""),
        )
        graph_key = task_graph_control_service().graph_key(
            tenant_id,
            canonical_graph["graph_id"],
        )
        keys = [
            task_key(task_id),
            attempt_key,
            owner_key,
            runtime_assignment_key,
            requester_assignment_key,
            graph_key,
            runtime_card_key,
            requester_card_key,
            a2a_agent_card_active_assignments_key(
                str(assignment_projection.get("agent_card_id") or ""),
            ),
            a2a_agent_card_active_assignments_key(
                str(requester_projection.get("agent_card_id") or ""),
            ),
            assignment_ids_key(),
            assignment_task_index_key(task_id),
        ]
        expected_raws = [
            redis.command("GET", record_key)
            for record_key in keys[:8]
        ]
        if any(raw is None for raw in expected_raws):
            raise DeclaredContractV1Error(
                "product_developer_durable_state_missing",
                [{"path": "/task", "code": "durable_record_missing"}],
            )
        (
            expected_task_raw,
            expected_attempt_raw,
            expected_owner_raw,
            expected_assignment_raw,
            expected_requester_raw,
            expected_graph_raw,
            expected_runtime_card_raw,
            expected_requester_card_raw,
        ) = expected_raws
        if json.loads(expected_task_raw) != current:
            continue
        attempt = json.loads(expected_attempt_raw)
        owner_state = json.loads(expected_owner_raw)
        assignment = json.loads(expected_assignment_raw)
        requester_assignment = json.loads(expected_requester_raw)
        expected_graph = json.loads(expected_graph_raw)
        runtime_card = parse_declared_a2a_agent_card_v1(
            json.loads(expected_runtime_card_raw),
        )
        requester_card = parse_declared_a2a_agent_card_v1(
            json.loads(expected_requester_card_raw),
        )
        effect_binding_error = product_developer_effect_binding_error(
            current,
            attempt,
        )
        runtime_error = validate_task_assignment_state(current)
        requester_error = validate_task_assignment_state({
            **current,
            "current_assignment_id": requester_assignment_id,
        })
        runtime_card_error = (
            product_developer_agent_card_binding_error(
                runtime_card,
                assignment,
                require_available_revision=True,
                runtime_profile=current["envelope"][
                    "developer_dispatch"
                ]["runtime_profile"],
            )
        )
        requester_card_error = (
            product_developer_agent_card_binding_error(
                requester_card,
                requester_assignment,
                require_available_revision=True,
            )
        )
        attempt_lease = attempt.get("lease") or {}
        if (
            effect_binding_error
            or runtime_error
            or requester_error
            or runtime_card_error
            or requester_card_error
            or assignment != assignment_projection
            or requester_assignment != requester_projection
            or current.get("assignment_id") != assignment_id
            or current.get("current_assignment_id") != assignment_id
            or attempt.get("attempt_id") != current["attempt_id"]
            or attempt.get("assignment_id") != assignment_id
            or attempt_lease.get("lease_id") != current["lease_id"]
            or attempt_lease.get("fencing_token")
            != current["fencing_token"]
            or attempt_lease.get("agent_card_id")
            != assignment.get("agent_card_id")
            or owner_state.get("current_attempt_id")
            != current["attempt_id"]
            or owner_state.get("current_assignment_id")
            != assignment_id
            or owner_state.get("lease_id") != current["lease_id"]
            or owner_state.get("fencing_token")
            != current["fencing_token"]
            or assignment.get("attempt_id") != current["attempt_id"]
            or assignment.get("lease_id") != current["lease_id"]
            or requester_assignment.get("attempt_id")
            != current["attempt_id"]
            or requester_assignment.get("lease_id")
            != current["lease_id"]
            or expected_graph != canonical_graph
            or attempt.get("status") != canonical_task["state"]
            or owner_state.get("task_version")
            != canonical_task["version"]
            or owner_state.get("current_status")
            != canonical_task["state"]
            or assignment.get("task_version")
            != canonical_task["version"]
            or requester_assignment.get("task_version")
            != canonical_task["version"]
        ):
            raise DeclaredContractV1Error(
                "stale_or_invalid_assignment",
                [{
                    "path": "/assignment",
                    "code": (
                        runtime_error
                        or requester_error
                        or runtime_card_error
                        or requester_card_error
                        or effect_binding_error
                        or "durable_binding_mismatch"
                    ),
                }],
            )
        heartbeat_at = utc_now()
        lease_until = now_ts() + LEASE_DURATION
        lease_expires_at = datetime.fromtimestamp(
            lease_until,
            tz=timezone.utc,
        ).isoformat()
        transitioned_task, transitioned_graph = (
            _canonical_execution_transition_projection(
                canonical_task,
                canonical_graph,
                (
                    ("running",)
                    if canonical_task["state"] == "leased"
                    else ()
                ),
                requested_at=heartbeat_at,
            )
        )
        updated_task = copy.deepcopy(current)
        updated_task.update({
            "state": STATE_RUNNING,
            "heartbeat_at": heartbeat_at,
            "lease_until": lease_until,
            "pid": body.get("pid", current.get("pid")),
            "worktree": body.get(
                "worktree",
                current.get("worktree"),
            ),
            "branch": body.get("branch", current.get("branch")),
            "log_paths": body.get(
                "log_paths",
                current.get("log_paths"),
            ),
            "updated_at": heartbeat_at,
        })
        updated_task["envelope"] = dict(updated_task["envelope"])
        updated_task["envelope"]["contract_v1"] = transitioned_task
        attempt["lease"] = {
            **attempt_lease,
            "heartbeat_at": heartbeat_at,
            "expires_at": lease_expires_at,
        }
        attempt["status"] = "running"
        attempt["updated_at"] = heartbeat_at
        attempt = HOME_CONTRACTS_V1.prepare_outbound(
            attempt,
            "kolibri.task_attempt",
        )
        updated_task["task_attempt"] = attempt
        owner_state.update({
            "task_version": transitioned_task["version"],
            "current_status": "running",
            "lease_expires_at": lease_expires_at,
        })
        owner_state = HOME_CONTRACTS_V1.prepare_outbound(
            owner_state,
            "kolibri.task_owner_state",
        )

        def extend_assignment(
            current_assignment: dict[str, Any],
        ) -> dict[str, Any]:
            extended = copy.deepcopy(current_assignment)
            extended["version"] = int(extended["version"]) + 1
            extended["task_version"] = transitioned_task["version"]
            extended["deadline_at"] = lease_expires_at
            extended["updated_at"] = heartbeat_at
            extended["authority_profile"]["expires_at"] = (
                lease_expires_at
            )
            return parse_declared_assignment_v1(extended)

        assignment = extend_assignment(assignment)
        requester_assignment = extend_assignment(
            requester_assignment,
        )
        updated_task["agent_assignment"] = assignment
        updated_task["requester_assignment"] = requester_assignment
        updated_raws = [
            json.dumps(
                updated_task,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ),
            _json_record(attempt),
            _json_record(owner_state),
            _json_record(assignment),
            _json_record(requester_assignment),
            _json_record(transitioned_graph),
            expected_runtime_card_raw,
            expected_requester_card_raw,
        ]
        arguments: list[str] = []
        for expected, updated in zip(
            expected_raws,
            updated_raws,
            strict=True,
        ):
            arguments.extend([expected, updated])
        reply = redis.command(
            "EVAL",
            PRODUCT_DEVELOPER_HEARTBEAT_LUA,
            12,
            *keys,
            *arguments,
            assignment_id,
            requester_assignment_id,
        )
        if str(reply[0]) == "committed":
            return json.loads(reply[1])
        if str(reply[0]) not in {"stale_record"}:
            raise DeclaredContractV1Error(
                "product_developer_durable_state_conflict",
                [{
                    "path": "/task",
                    "code": str(reply[0]),
                }],
            )
    raise DeclaredContractV1Error(
        "stale_or_invalid_lease",
        [{"path": "/lease", "code": "stale_task_revision"}],
    )


def _product_developer_terminal_projection(
    canonical_task: dict[str, Any],
    canonical_graph: dict[str, Any],
    *,
    success: bool,
    requested_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    graph_service = task_graph_control_service()
    states = (
        (
            (
                "running",
                "submitted",
                "verifying",
                "completed",
            )
            if canonical_task["state"] == "leased"
            else ("submitted", "verifying", "completed")
        )
        if success
        else ("failed_retryable", "failed_terminal")
    )
    task = rebase_canonical_task_graph_version(
        canonical_task,
        canonical_graph,
    )
    graph = canonical_graph
    for state in states:
        task = {
            **task,
            "state": state,
            "version": int(task["version"]) + 1,
            "updated_at": requested_at,
        }
        task = HOME_CONTRACTS_V1.prepare_outbound(
            task,
            "kolibri.task",
        )
        graph = graph_service.project_task_transition(
            graph,
            task,
            requested_at=requested_at,
        )
    return task, graph


def _product_developer_a2a_response(
    task: dict[str, Any],
    canonical_task: dict[str, Any],
    source: dict[str, Any],
    assignment: dict[str, Any],
    requester_assignment: dict[str, Any],
    *,
    success: bool,
    result: dict[str, Any] | None,
    error_type: str,
    error_message: str,
    sent_at: str,
    home_generated: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    request_message = parse_declared_a2a_message_v1(
        task["a2a_request"],
    )
    source_sidecar = task.get("source_command_sidecar")
    source_task_version = (
        source_sidecar.get("task_version")
        if isinstance(source_sidecar, dict)
        else None
    )
    if (
        request_message["task_id"] != canonical_task["task_id"]
        or request_message["task_version"] != source_task_version
        or request_message["recipient_assignment_ids"]
        != [assignment["assignment_id"]]
        or request_message["sender_assignment_id"]
        != requester_assignment["assignment_id"]
        or request_message["sender_actor_id"]
        != requester_assignment["assignee_actor_id"]
        or requester_assignment["assignment_id"]
        == assignment["assignment_id"]
        or requester_assignment["assignee_actor_id"]
        == assignment["assignee_actor_id"]
    ):
        raise DeclaredContractV1Error(
            "product_developer_a2a_request_invalid",
            [{"path": "/a2a_request", "code": "binding"}],
        )
    if success:
        raw_text = None if result is None else (
            result.get("response")
            if result.get("response") is not None
            else result.get("output_text")
        )
        text = (
            str(raw_text)
            if isinstance(raw_text, str) and raw_text.strip()
            else "Developer execution completed."
        )
        status = "completed"
        message_type = "handoff"
    else:
        text = (
            str(error_message).strip()
            or "Developer execution failed."
        )
        status = "failed"
        message_type = "rejection"
    text = text[:32000]
    response_id = (
        "a2amsg_"
        + _stable_developer_digest(
            request_message["channel_id"],
            "2",
            status,
        )[:40]
    )
    expires_at = datetime.fromtimestamp(
        max(
            now_ts() + LEASE_DURATION,
            (parse_iso_ts(sent_at) or now_ts()) + LEASE_DURATION,
        ),
        tz=timezone.utc,
    ).isoformat()
    sender_assignment = (
        requester_assignment
        if home_generated
        else assignment
    )
    recipient_assignments = [requester_assignment]

    def delivery_projection(
        current_assignment: dict[str, Any],
        *,
        extend_home_grant: bool,
    ) -> dict[str, Any]:
        projected = copy.deepcopy(current_assignment)
        projected["status"] = "active"
        projected["task_version"] = canonical_task["version"]
        if extend_home_grant:
            projected["deadline_at"] = expires_at
            projected["authority_profile"]["expires_at"] = expires_at
        return parse_declared_assignment_v1(projected)

    sender_projection = delivery_projection(
        sender_assignment,
        extend_home_grant=home_generated,
    )
    recipient_projections = [
        (
            sender_projection
            if recipient["assignment_id"]
            == sender_projection["assignment_id"]
            else delivery_projection(
                recipient,
                extend_home_grant=False,
            )
        )
        for recipient in recipient_assignments
    ]
    response_message = {
        "schema_id": "kolibri.a2a.message_appended.event",
        "schema_version": "1.0",
        "a2a_message_id": response_id,
        "tenant_id": canonical_task["tenant_id"],
        "goal_id": canonical_task["goal_id"],
        "case_id": canonical_task["case_id"],
        "task_id": canonical_task["task_id"],
        "task_version": canonical_task["version"],
        "channel_id": request_message["channel_id"],
        "sequence": 2,
        "previous_message_id": request_message["a2a_message_id"],
        "sender_actor_id": sender_projection["assignee_actor_id"],
        "sender_assignment_id": sender_projection["assignment_id"],
        "recipient_assignment_ids": [
            recipient["assignment_id"]
            for recipient in recipient_projections
        ],
        "recipient_capability": "task_owner_state",
        "message_type": message_type,
        "purpose": (
            "Return the fenced developer execution outcome to Logical Home."
        ),
        "response_to_message_id": request_message["a2a_message_id"],
        "content": {
            "trust": "untrusted_content",
            "text": text,
            "structured_data": {
                "expected_response": "none",
                "status": status,
                "source_command_ref": source["source_command_ref"],
                "attempt_id": task["attempt_id"],
                "lease_id": task["lease_id"],
                "fencing_token": task["fencing_token"],
                "error_type": None if success else error_type,
                "result": result if success else None,
            },
            "reference_ids": sorted({
                source["source_command_ref"],
                canonical_task["task_id"],
                task["attempt_id"],
            }),
        },
        "content_hash": "sha256:" + ("0" * 64),
        "deduplication_key": (
            "a2a:developer-response:"
            + _stable_developer_digest(
                canonical_task["tenant_id"],
                canonical_task["task_id"],
                task["attempt_id"],
                status,
            )
        ),
        "sent_at": sent_at,
        "expires_at": expires_at,
    }
    response_message["content_hash"] = a2a_content_hash(
        response_message,
    )
    response_message = parse_declared_a2a_message_v1(
        response_message,
    )
    valid_assignments, assignment_violations = (
        validate_a2a_sender_recipient_at_owner(
            response_message,
            {
                "identity": {
                    "authority": sender_projection[
                        "authority_profile"
                    ],
                },
            },
            [
                sender_projection,
                *recipient_projections,
            ],
            sent_at,
        )
    )
    if not valid_assignments:
        raise DeclaredContractV1Error(
            "product_developer_a2a_response_assignment_invalid",
            assignment_violations,
        )
    cursor = load_a2a_cursor(
        response_message["tenant_id"],
        response_message["channel_id"],
    )
    decision = classify_a2a_delivery(
        response_message,
        cursor,
        sent_at,
    )
    if decision["decision"] != "accepted":
        raise DeclaredContractV1Error(
            "product_developer_a2a_response_rejected",
            [{
                "path": "/a2a_response",
                "code": str(decision["code"] or decision["decision"]),
            }],
        )
    updated_cursor = {
        **cursor,
        "last_sequence": response_message["sequence"],
        "last_message_id": response_message["a2a_message_id"],
        "accepted_messages": {
            **cursor["accepted_messages"],
            response_message["a2a_message_id"]: response_message[
                "content_hash"
            ],
        },
        "deduplication_index": {
            **cursor["deduplication_index"],
            response_message["deduplication_key"]: {
                "message_id": response_message["a2a_message_id"],
                "content_hash": response_message["content_hash"],
            },
        },
    }
    updated_cursor = parse_declared_a2a_cursor_v1(updated_cursor)
    record = {
        "schema_id": "kolibri.a2a.home_delivery_record",
        "schema_version": "1.0",
        "source_command_ref": source["source_command_ref"],
        "message": response_message,
        "delivery_assignments": {
            candidate["assignment_id"]: candidate
            for candidate in {
                item["assignment_id"]: item
                for item in [
                    sender_projection,
                    *recipient_projections,
                ]
            }.values()
        },
    }
    return response_message, updated_cursor, record


def commit_product_developer_terminal(
    task: dict[str, Any],
    body: dict[str, Any],
    *,
    success: bool,
    expired: bool = False,
) -> dict[str, Any] | None:
    """Append terminal A2A and close the canonical task under one fence."""

    if not expired:
        fence_error = validate_task_mutation_fence(task, body)
        if fence_error:
            raise DeclaredContractV1Error(
                "stale_or_invalid_lease",
                [{"path": "/lease", "code": fence_error}],
            )
    if task.get("state") in TERMINAL_STATES:
        return task
    if not expired:
        assignment_error = validate_task_assignment_state(task)
        if assignment_error:
            raise DeclaredContractV1Error(
                "stale_or_invalid_assignment",
                [{"path": "/assignment", "code": assignment_error}],
            )
    canonical_task = parse_declared_contract_v1(
        task.get("envelope", {}),
        "kolibri.task",
        bound_id=str(task["task_id"]),
    )
    if canonical_task is None or not is_product_developer_task(task):
        raise DeclaredContractV1Error(
            "canonical_task_transition_required",
            [{"path": "/task", "code": "unsupported"}],
        )
    if canonical_task["state"] not in {"leased", "running"}:
        raise DeclaredContractV1Error(
            "canonical_task_transition_conflict",
            [{
                "path": "/task/state",
                "code": "active_lease_required",
            }],
        )
    canonical_graph = authoritative_graph_for_canonical_task(
        canonical_task,
        require_runnable=False,
    )
    source = load_product_developer_source(canonical_task)
    if source is None:
        raise DeclaredContractV1Error(
            "product_developer_source_invalid",
            [{"path": "/source_command_ref", "code": "missing"}],
        )
    assignment = load_assignment(task["assignment_id"])
    if assignment is None:
        raise DeclaredContractV1Error(
            "stale_or_invalid_assignment",
            [{"path": "/assignment", "code": "assignment_not_found"}],
        )
    assignment_projection = task.get("agent_assignment")
    if (
        not isinstance(assignment_projection, dict)
        or not assignment_projection_matches_registry(
            assignment,
            assignment_projection,
            allow_control_plane_revocation=expired,
        )
    ):
        raise DeclaredContractV1Error(
            "stale_or_invalid_assignment",
            [{
                "path": "/assignment",
                "code": "assignment_projection_mismatch",
            }],
        )
    requester_projection = task.get("requester_assignment")
    if not isinstance(requester_projection, dict):
        raise DeclaredContractV1Error(
            "stale_or_invalid_assignment",
            [{"path": "/requester_assignment", "code": "missing"}],
        )
    requester_assignment = load_assignment(
        requester_projection.get("assignment_id"),
    )
    if (
        requester_assignment is None
        or not assignment_projection_matches_registry(
            requester_assignment,
            requester_projection,
            allow_control_plane_revocation=expired,
        )
    ):
        raise DeclaredContractV1Error(
            "stale_or_invalid_assignment",
            [{
                "path": "/requester_assignment",
                "code": "requester_assignment_not_found",
            }],
        )
    if not expired:
        requester_error = validate_task_assignment_state({
            **task,
            "current_assignment_id": requester_assignment["assignment_id"],
        })
        if requester_error:
            raise DeclaredContractV1Error(
                "stale_or_invalid_assignment",
                [{
                    "path": "/requester_assignment",
                    "code": requester_error,
                }],
            )
    runtime_card_key = a2a_agent_card_key(
        str(assignment.get("agent_card_id") or ""),
    )
    requester_card_key = a2a_agent_card_key(
        str(requester_assignment.get("agent_card_id") or ""),
    )
    expected_runtime_card_json = redis.command(
        "GET",
        runtime_card_key,
    )
    expected_requester_card_json = redis.command(
        "GET",
        requester_card_key,
    )
    runtime_card = (
        None
        if expected_runtime_card_json is None
        else parse_declared_a2a_agent_card_v1(
            json.loads(expected_runtime_card_json),
        )
    )
    requester_card = (
        None
        if expected_requester_card_json is None
        else parse_declared_a2a_agent_card_v1(
            json.loads(expected_requester_card_json),
        )
    )
    runtime_card_error = product_developer_agent_card_binding_error(
        runtime_card,
        assignment,
        require_available_revision=not expired,
        runtime_profile=task["envelope"]["developer_dispatch"][
            "runtime_profile"
        ],
    )
    requester_card_error = product_developer_agent_card_binding_error(
        requester_card,
        requester_assignment,
        require_available_revision=not expired,
    )
    if runtime_card_error or requester_card_error:
        raise DeclaredContractV1Error(
            "stale_or_invalid_assignment",
            [{
                "path": "/agent_card",
                "code": runtime_card_error or requester_card_error,
            }],
        )
    result = body.get("result", body) if success else body.get("result")
    if result is not None and not isinstance(result, dict):
        raise DeclaredContractV1Error(
            "invalid_result",
            [{"path": "/result", "code": "type"}],
        )
    error_type = str(body.get("error_type") or "runtime_error")
    error_message = str(body.get("error") or "")
    requested_at = utc_now()
    terminal_task, terminal_graph = (
        _product_developer_terminal_projection(
            canonical_task,
            canonical_graph,
            success=success,
            requested_at=requested_at,
        )
    )
    response_message, updated_cursor, response_record = (
        _product_developer_a2a_response(
            task,
            terminal_task,
            source,
            assignment,
            requester_assignment,
            success=success,
            result=result,
            error_type=error_type,
            error_message=error_message,
            sent_at=requested_at,
            home_generated=expired,
        )
    )
    updated_task = dict(task)
    updated_task["state"] = (
        STATE_DEAD
        if expired
        else (STATE_COMPLETED if success else STATE_FAILED)
    )
    updated_task["result"] = result
    updated_task["result_reference"] = (
        body.get("result_reference")
        or ((result or {}).get("result_path"))
    )
    updated_task["error_type"] = None if success else error_type
    updated_task["error"] = None if success else error_message
    updated_task["lease_until"] = None
    updated_task["heartbeat_at"] = requested_at
    updated_task["updated_at"] = requested_at
    updated_task["envelope"] = dict(updated_task["envelope"])
    updated_task["envelope"]["contract_v1"] = terminal_task
    updated_task["a2a_response"] = response_message
    preserve_terminal_lease_evidence(updated_task)

    tenant_id = canonical_task["tenant_id"]
    attempt_key = key(
        "task_attempt:"
        f"{tenant_id}:{task['attempt_id']}",
    )
    owner_key = key(
        "task_owner_state:"
        f"{tenant_id}:{task['task_id']}",
    )
    expected_attempt_json = redis.command("GET", attempt_key)
    expected_owner_json = redis.command("GET", owner_key)
    expected_assignment_json = redis.command(
        "GET",
        assignment_key(assignment["assignment_id"]),
    )
    expected_requester_assignment_json = redis.command(
        "GET",
        assignment_key(requester_assignment["assignment_id"]),
    )
    expected_cursor_json = redis.command(
        "GET",
        a2a_cursor_key(
            tenant_id,
            response_message["channel_id"],
        ),
    )
    graph_service = task_graph_control_service()
    graph_key = graph_service.graph_key(
        tenant_id,
        canonical_graph["graph_id"],
    )
    expected_graph_json = redis.command("GET", graph_key)
    if any(
        value is None
        for value in (
            expected_attempt_json,
            expected_owner_json,
            expected_assignment_json,
            expected_requester_assignment_json,
            expected_cursor_json,
            expected_graph_json,
        )
    ):
        raise DeclaredContractV1Error(
            "product_developer_durable_state_missing",
            [{"path": "/task", "code": "durable_record_missing"}],
        )
    attempt = json.loads(str(expected_attempt_json))
    owner_state = json.loads(str(expected_owner_json))
    expected_assignment = json.loads(str(expected_assignment_json))
    expected_requester_assignment = json.loads(
        str(expected_requester_assignment_json),
    )
    attempt_lease = attempt.get("lease") or {}
    expected_graph = json.loads(str(expected_graph_json))
    if (
        product_developer_effect_binding_error(task, attempt)
        or attempt.get("attempt_id") != task["attempt_id"]
        or attempt.get("assignment_id") != assignment["assignment_id"]
        or attempt_lease.get("lease_id") != task["lease_id"]
        or attempt_lease.get("fencing_token")
        != task["fencing_token"]
        or attempt_lease.get("agent_card_id")
        != assignment["agent_card_id"]
        or owner_state.get("tenant_id") != canonical_task["tenant_id"]
        or owner_state.get("task_id") != task["task_id"]
        or owner_state.get("current_attempt_id") != task["attempt_id"]
        or owner_state.get("current_assignment_id")
        != assignment["assignment_id"]
        or owner_state.get("lease_id") != task["lease_id"]
        or owner_state.get("fencing_token") != task["fencing_token"]
        or expected_assignment != assignment
        or expected_requester_assignment != requester_assignment
        or expected_graph != canonical_graph
        or attempt.get("status") != canonical_task["state"]
        or owner_state.get("task_version")
        != canonical_task["version"]
        or owner_state.get("current_status")
        != canonical_task["state"]
        or assignment.get("task_version")
        != canonical_task["version"]
        or assignment.get("attempt_id") != task["attempt_id"]
        or assignment.get("lease_id") != task["lease_id"]
        or requester_assignment.get("task_version")
        != canonical_task["version"]
        or requester_assignment.get("attempt_id") != task["attempt_id"]
        or requester_assignment.get("lease_id") != task["lease_id"]
    ):
        raise DeclaredContractV1Error(
            "product_developer_durable_state_conflict",
            [{"path": "/task", "code": "binding"}],
        )
    terminal_hash = response_message["content_hash"]
    attempt.update({
        "status": (
            "expired"
            if expired
            else ("completed" if success else "failed_terminal")
        ),
        "result_hash": terminal_hash,
        "error": (
            None
            if success
            else {
                "error_type": error_type,
                "message": error_message or "Developer execution failed.",
                "retryable": False,
            }
        ),
        "updated_at": requested_at,
    })
    attempt = HOME_CONTRACTS_V1.prepare_outbound(
        attempt,
        "kolibri.task_attempt",
    )
    owner_state.update({
        "task_version": terminal_task["version"],
        "current_status": terminal_task["state"],
        "committed_effects": {
            **owner_state["committed_effects"],
            attempt["effect_id"]: {
                "attempt_id": attempt["attempt_id"],
                "result_hash": terminal_hash,
            },
        },
    })
    owner_state = HOME_CONTRACTS_V1.prepare_outbound(
        owner_state,
        "kolibri.task_owner_state",
    )
    updated_assignment = (
        assignment
        if assignment.get("status") == "revoked"
        else {
            **assignment,
            "task_version": terminal_task["version"],
            "status": "completed" if success else "superseded",
            "version": int(assignment["version"]) + 1,
            "updated_at": requested_at,
        }
    )
    updated_assignment = parse_declared_assignment_v1(
        updated_assignment,
    )
    updated_requester_assignment = (
        requester_assignment
        if requester_assignment.get("status") == "revoked"
        else {
            **requester_assignment,
            "task_version": terminal_task["version"],
            "status": "completed" if success else "superseded",
            "version": int(requester_assignment["version"]) + 1,
            "updated_at": requested_at,
        }
    )
    updated_requester_assignment = parse_declared_assignment_v1(
        updated_requester_assignment,
    )
    updated_task["agent_assignment"] = updated_assignment
    updated_task["requester_assignment"] = (
        updated_requester_assignment
    )
    updated_task["task_attempt"] = attempt
    previous_json = json.dumps(
        task,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    updated_json = json.dumps(
        updated_task,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    reply = redis.command(
        "EVAL",
        PRODUCT_DEVELOPER_TERMINAL_LUA,
        19,
        task_key(task["task_id"]),
        key("active_lease_ids"),
        key("queue"),
        graph_key,
        attempt_key,
        owner_key,
        assignment_key(assignment["assignment_id"]),
        assignment_key(requester_assignment["assignment_id"]),
        a2a_cursor_key(
            tenant_id,
            response_message["channel_id"],
        ),
        a2a_message_id_key(response_message["a2a_message_id"]),
        a2a_channel_messages_key(
            tenant_id,
            response_message["channel_id"],
        ),
        a2a_message_id_key(task["a2a_request"]["a2a_message_id"]),
        runtime_card_key,
        requester_card_key,
        a2a_agent_card_active_assignments_key(
            assignment["agent_card_id"],
        ),
        a2a_agent_card_active_assignments_key(
            requester_assignment["agent_card_id"],
        ),
        assignment_ids_key(),
        assignment_task_index_key(task["task_id"]),
        key("dead_letter"),
        previous_json,
        updated_json,
        expected_graph_json,
        json.dumps(
            terminal_graph,
            sort_keys=True,
            separators=(",", ":"),
        ),
        expected_attempt_json,
        json.dumps(attempt, sort_keys=True, separators=(",", ":")),
        expected_owner_json,
        json.dumps(owner_state, sort_keys=True, separators=(",", ":")),
        expected_assignment_json,
        json.dumps(
            updated_assignment,
            sort_keys=True,
            separators=(",", ":"),
        ),
        expected_requester_assignment_json,
        json.dumps(
            updated_requester_assignment,
            sort_keys=True,
            separators=(",", ":"),
        ),
        expected_cursor_json,
        json.dumps(
            updated_cursor,
            sort_keys=True,
            separators=(",", ":"),
        ),
        json.dumps(
            response_record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ),
        response_message["a2a_message_id"],
        task["task_id"],
        assignment["assignment_id"],
        requester_assignment["assignment_id"],
        "dead" if expired else "remove",
        expected_runtime_card_json or "__kolibri_missing__",
        expected_requester_card_json or "__kolibri_missing__",
    )
    if str(reply[0]) == "committed":
        return json.loads(reply[1])
    current = load_task(task["task_id"])
    if (
        current is not None
        and current.get("state") in TERMINAL_STATES
        and current.get("attempt_id") == task.get("attempt_id")
        and current.get("lease_id") == task.get("lease_id")
        and current.get("fencing_token") == task.get("fencing_token")
    ):
        return current
    return None


def expire_product_developer_task_atomically(
    task: dict[str, Any],
) -> dict[str, Any] | None:
    """Close an expired developer dispatch, including its typed A2A reply."""

    current = load_task(str(task["task_id"]))
    if (
        current is None
        or current.get("state") not in ACTIVE_LEASE_STATES
        or float(current.get("lease_until") or 0) >= now_ts()
    ):
        return None
    return commit_product_developer_terminal(
        current,
        {
            "error_type": "lease_expired",
            "error": "Developer lease expired before completion.",
            "result": None,
        },
        success=False,
        expired=True,
    )


def expire_task_lease_atomically(
    previous: dict[str, Any],
    updated: dict[str, Any],
    *,
    retry: bool,
) -> dict[str, Any] | None:
    """CAS lease expiration against a concurrent worker completion."""

    updated["updated_at"] = utc_now()
    previous_json = json.dumps(
        previous,
        sort_keys=True,
        separators=(",", ":"),
    )
    updated_json = json.dumps(
        updated,
        sort_keys=True,
        separators=(",", ":"),
    )
    reply = redis.command(
        "EVAL",
        EXECUTION_TASK_EXPIRE_LUA,
        4,
        task_key(previous["task_id"]),
        key("active_lease_ids"),
        key("queue"),
        key("dead_letter"),
        previous_json,
        updated_json,
        previous["task_id"],
        "retry" if retry else "dead",
    )
    if str(reply[0]) != "committed":
        return None
    return json.loads(reply[1])


def requeue_expired_canonical_lease_atomically(
    previous: dict[str, Any],
    updated: dict[str, Any],
    *,
    canonical_task: dict[str, Any],
    canonical_graph: dict[str, Any],
) -> dict[str, Any] | None:
    """CAS expired canonical lease requeue and reproject the graph."""

    updated["updated_at"] = utc_now()
    graph_service = task_graph_control_service()
    transitioned_task = dict(canonical_task)
    transitioned_task["state"] = "failed_retryable"
    transitioned_task["version"] = int(canonical_task["version"]) + 1
    transitioned_task["current_attempt_id"] = None
    transitioned_task["current_assignment_id"] = None
    transitioned_task["updated_at"] = updated["updated_at"]
    transitioned_task = HOME_CONTRACTS_V1.prepare_outbound(
        transitioned_task,
        "kolibri.task",
    )

    transitioned_graph = graph_service.project_task_transition(
        canonical_graph,
        transitioned_task,
        requested_at=updated["updated_at"],
    )
    graph_key = graph_service.graph_key(
        canonical_task["tenant_id"],
        canonical_graph["graph_id"],
    )
    expected_graph_json = redis.command("GET", graph_key)
    if expected_graph_json is None:
        return None
    if json.loads(expected_graph_json) != canonical_graph:
        return None

    updated["envelope"] = dict(updated.get("envelope") or {})
    updated["envelope"]["contract_v1"] = transitioned_task
    previous_json = json.dumps(
        previous,
        sort_keys=True,
        separators=(",", ":"),
    )
    updated_json = json.dumps(
        updated,
        sort_keys=True,
        separators=(",", ":"),
    )
    transitioned_graph_json = json.dumps(
        transitioned_graph,
        sort_keys=True,
        separators=(",", ":"),
    )
    reply = redis.command(
        "EVAL",
        EXECUTION_TASK_EXPIRE_CANONICAL_LUA,
        5,
        task_key(previous["task_id"]),
        key("active_lease_ids"),
        key("queue"),
        key("dead_letter"),
        graph_key,
        previous_json,
        updated_json,
        previous["task_id"],
        "retry",
        expected_graph_json,
        transitioned_graph_json,
    )
    if str(reply[0]) != "committed":
        return None
    return json.loads(reply[1])


def preserve_terminal_lease_evidence(task: dict[str, Any]) -> dict[str, Any]:
    """Freeze the lease binding that was authorized to create terminal state."""
    if task.get("terminal_lease_evidence") is not None:
        return task
    if task.get("state") not in TERMINAL_STATES:
        return task
    if not any(task.get(field) is not None for field in LEASE_FENCE_FIELDS):
        return task
    task["terminal_lease_evidence"] = {
        "lease_contract_version": task.get("lease_contract_version") or LEASE_CONTRACT_VERSION,
        "attempt_id": task.get("attempt_id"),
        "lease_id": task.get("lease_id"),
        "fencing_token": task.get("fencing_token"),
        "lease_owner": task.get("lease_owner"),
        "lease_slot_id": task.get("lease_slot_id"),
        "terminal_state": task.get("state"),
        "closed_at": utc_now(),
    }
    return task


def runner_capability_names(runner: str) -> set[str]:
    return {f"runner:{runner}", f"runner_{runner}", f"{runner}_runner"}


def runner_state(node: dict[str, Any], runner: str) -> str | None:
    runners = node.get("runners")
    if isinstance(runners, dict):
        value = runners.get(runner)
        if isinstance(value, dict):
            state = value.get("status")
            return str(state).strip().lower() if state is not None else None
        if isinstance(value, str):
            return value.strip().lower()
    runner_status = node.get("runner_status")
    if isinstance(runner_status, dict):
        value = runner_status.get(runner)
        if isinstance(value, dict):
            state = value.get("status")
            return str(state).strip().lower() if state is not None else None
        if isinstance(value, str):
            return value.strip().lower()
    return None


def mark_node_runner_failure(task: dict[str, Any], body: dict[str, Any]) -> None:
    error_type = body.get("error_type")
    if error_type not in {"runner_auth_blocked", "runner_unavailable"}:
        return
    result = body.get("result") if isinstance(body.get("result"), dict) else {}
    envelope = task.get("envelope", {})
    runner = result.get("runner") or envelope.get("runner")
    if not runner:
        return
    lease_owner = str(task.get("lease_owner") or "")
    node_id = lease_owner.split(":", 1)[0] if lease_owner else None
    if not node_id:
        return
    node = get_json(node_key(node_id), {"node_id": node_id})
    runner_failure = {
        "status": "blocked" if error_type == "runner_auth_blocked" else "unavailable",
        "error_type": error_type,
        "updated_at": utc_now(),
    }
    slot_id = task.get("lease_slot_id")
    with NODE_UPDATE_LOCK:
        node = refresh_node_effective_state(node)
        slots = _stored_agent_slots(node)
        if slot_id and slot_id in slots:
            slot = dict(slots[slot_id])
            runners = dict(slot.get("runners") or {}) if isinstance(slot.get("runners"), dict) else {}
            runners[str(runner)] = runner_failure
            slot["runners"] = runners
            slot["status"] = runner_failure["status"]
            slot["heartbeat_at"] = utc_now()
            slots[str(slot_id)] = slot
            node["agent_slots"] = slots
        else:
            runners = dict(node.get("base_runners") or {})
            runners[str(runner)] = runner_failure
            node["base_runners"] = runners
        set_json(node_key(node_id), refresh_node_effective_state(node))


def compatible(task: dict[str, Any], node_id: str, capabilities: list[str], node: dict[str, Any] | None = None) -> bool:
    envelope = task.get("envelope", {})
    target_node = envelope.get("target_node") or envelope.get("required_node")
    if target_node and target_node != node_id:
        return False
    allowed = envelope.get("allowed_nodes")
    if allowed and node_id not in allowed:
        return False
    avoided = set(str(item) for item in ensure_list(envelope.get("avoid_nodes") or envelope.get("avoided_nodes")))
    if node_id in avoided:
        return False
    required = envelope.get("required_capability")
    if required and required not in capabilities:
        return False
    required_many = normalized_string_list(envelope.get("required_capabilities"))
    if any(required_capability not in capabilities for required_capability in required_many):
        return False
    runner = str(envelope.get("runner") or "").strip().lower()
    source = envelope.get("source")
    product_text_run = (
        isinstance(source, dict)
        and source.get("kind") == "product_run_execute_command"
    )
    # Runner selection is an execution constraint for every AI task, not only
    # owner_remote_task. Without this gate, chat/image/orchestrator work can be
    # leased by a healthy node that has no matching authenticated runtime and
    # fail terminally before a capable worker gets a chance to claim it.
    if runner:
        # Product text runners intentionally expose only their dedicated
        # least-privilege capability. Requiring the broad ``runner:<name>``
        # capability here makes every canonical Product task permanently
        # unleaseable, while granting it would let the isolated workload claim
        # unrelated generic AI tasks. The signed Product command, source
        # binding and agent-host policy perform the remaining fail-closed
        # checks for this narrow path.
        accepted_runner_capabilities = (
            {f"product_text_runner:{runner}"}
            if product_text_run
            else runner_capability_names(runner)
        )
        if not accepted_runner_capabilities.intersection(set(capabilities)):
            return False
        node_state = runner_state(node or {}, runner)
        if node_state in BLOCKED_RUNNER_STATES:
            return False
    return True


def resume_active_product_developer_lease_for_claim(
    *,
    node_id: str,
    agent_id: str,
    slot_id: str,
    capabilities: list[str],
    node: dict[str, Any],
) -> dict[str, Any] | None:
    """Recover this exact worker's still-authoritative developer lease.

    The AgentHost may restart after the provider accepted an idempotent effect.
    Reissuing a new attempt or fence would make durable provider reconciliation
    ambiguous, so the same signed node/agent/slot first resumes its existing
    unexpired lease. The normal heartbeat mutation performs the full durable
    Task/Attempt/Assignment/Card validation before anything is returned.
    """

    expected_owner = f"{node_id}:{agent_id}"
    current = now_ts()
    active_ids = sorted(
        redis.command("SMEMBERS", key("active_lease_ids")) or [],
    )
    for task_id in active_ids:
        task = load_task(task_id)
        if (
            task is None
            or task.get("state") not in ACTIVE_LEASE_STATES
            or not is_product_developer_task(task)
            or str(task.get("lease_owner") or "") != expected_owner
            or str(task.get("lease_slot_id") or "") != slot_id
            or not compatible(task, node_id, capabilities, node)
        ):
            continue
        try:
            lease_until = float(task.get("lease_until") or 0)
        except (TypeError, ValueError):
            continue
        if lease_until <= current:
            continue
        try:
            return heartbeat_product_developer_task_atomically(
                task,
                {
                    "attempt_id": task.get("attempt_id"),
                    "lease_id": task.get("lease_id"),
                    "fencing_token": task.get("fencing_token"),
                    "node_id": node_id,
                    "agent_id": agent_id,
                    "slot_id": slot_id,
                    "state": STATE_RUNNING,
                },
            )
        except DeclaredContractV1Error:
            # A corrupt, revoked or concurrently replaced authority projection
            # is never repaired by the lease endpoint.
            continue
    return None


def requeue_expired_leases() -> None:
    current = now_ts()
    active_ids = sorted(redis.command("SMEMBERS", key("active_lease_ids")) or [])
    for task_id in active_ids:
        task = load_task(task_id)
        if not task or task.get("state") not in ACTIVE_LEASE_STATES:
            redis.command("SREM", key("active_lease_ids"), task_id)
            continue
        lease_until = float(task.get("lease_until") or 0)
        if lease_until >= current:
            continue
        previous = dict(task)
        assignment_id = str(task.get("current_assignment_id") or "").strip()
        assignment_status = "expired" if (
            int(task.get("attempt", 0))
            < int(task.get("max_retries", MAX_RETRIES))
        ) else "superseded"
        assignment_reason = (
            "task lease expired and retry budget remains"
            if assignment_status == "expired"
            else "task lease expired and retry budget exhausted"
        )
        retry = (
            int(task.get("attempt", 0))
            < int(task.get("max_retries", MAX_RETRIES))
        )
        canonical_task = parse_declared_contract_v1(
            task.get("envelope", {}),
            "kolibri.task",
            bound_id=task["task_id"],
        )
        if (
            canonical_task is not None
            and is_product_developer_task(task)
        ):
            try:
                expire_product_developer_task_atomically(task)
            except DeclaredContractV1Error:
                pass
            continue
        if (
            canonical_task is not None
            and not is_product_developer_task(task)
        ):
            try:
                expire_canonical_execution_task_atomically(
                    task,
                    retry=retry,
                )
            except DeclaredContractV1Error:
                pass
            continue
        if retry:
            task["state"] = STATE_QUEUED
            task["lease_owner"] = None
            task["lease_id"] = None
            task["lease_slot_id"] = None
            task["lease_until"] = None
            task["current_assignment_id"] = None
            task.pop("agent_assignment", None)
            task["error_type"] = "lease_expired"
            task["error"] = "lease expired before task completion"
            if canonical_task is not None:
                # Product developer tasks retain their dedicated terminal
                # protocol; no generic canonical task reaches this branch.
                requeued = expire_task_lease_atomically(
                    previous,
                    task,
                    retry=retry,
                )
                if requeued is None:
                    continue
                task = requeued
            else:
                requeued = expire_task_lease_atomically(
                    previous,
                    task,
                    retry=retry,
                )
                if requeued is None:
                    continue
                task = requeued
                if assignment_id:
                    mark_assignment_by_id(
                        assignment_id,
                        status=assignment_status,
                        reason=assignment_reason,
                    )
        else:
            task["state"] = STATE_DEAD
            task["error_type"] = "lease_expired"
            task["error"] = "lease expired and retry budget exhausted"
            preserve_terminal_lease_evidence(task)
            requeued = expire_task_lease_atomically(
                previous,
                task,
                retry=retry,
            )
            if requeued is None:
                continue
            if assignment_id:
                mark_assignment_by_id(
                    assignment_id,
                    status=assignment_status,
                    reason=assignment_reason,
                )
            task = requeued


def authoritative_graph_for_canonical_task(
    canonical_task: dict[str, Any],
    *,
    require_runnable: bool = True,
) -> dict[str, Any]:
    """Load and verify the sole authoritative graph for a canonical task."""

    graph_service = task_graph_control_service()
    graph_id = redis.command(
        "GET",
        graph_service.case_graph_key(
            canonical_task["tenant_id"],
            canonical_task["case_id"],
        ),
    )
    if not graph_id:
        raise DeclaredContractV1Error(
            "task_graph_required",
            [{
                "path": "/contract_v1/case_id",
                "code": "canonical_graph_not_found",
            }],
        )
    try:
        graph = graph_service.load_graph(
            canonical_task["tenant_id"],
            str(graph_id),
        )
    except TaskGraphCommandError as exc:
        raise DeclaredContractV1Error(
            "task_graph_invalid",
            exc.violations or [{
                "path": "/contract_v1/case_id",
                "code": exc.code,
            }],
        ) from exc
    if graph is None:
        raise DeclaredContractV1Error(
            "task_graph_required",
            [{
                "path": "/contract_v1/case_id",
                "code": "canonical_graph_not_found",
            }],
        )
    graph_task = next(
        (
            task
            for task in graph["tasks"]
            if task["task_id"] == canonical_task["task_id"]
        ),
        None,
    )
    if graph_task != canonical_task:
        if graph_task is None:
            raise DeclaredContractV1Error(
                "contract_binding_mismatch",
                [{
                    "path": "/contract_v1/task_id",
                    "code": "canonical_graph_task_missing",
                }],
            )
        dynamic_contract_fields = {
            "graph_version",
            "state",
            "version",
            "current_attempt_id",
            "current_assignment_id",
            "updated_at",
        }
        for field in graph_task:
            if field in dynamic_contract_fields:
                continue
            if canonical_task.get(field) != graph_task[field]:
                raise DeclaredContractV1Error(
                    "contract_binding_mismatch",
                    [{
                        "path": "/contract_v1",
                        "code": "canonical_graph_task_mismatch",
                    }],
                )
    if (
        require_runnable
        and canonical_task["task_id"] not in graph["runnable_task_ids"]
    ):
        raise DeclaredContractV1Error(
            "task_not_runnable",
            [{
                "path": "/contract_v1/task_id",
                "code": "dependency_or_state_blocked",
            }],
        )
    return graph


def persist_execution_task_atomically(
    task: dict[str, Any],
    *,
    canonical_task: dict[str, Any] | None,
    canonical_graph: dict[str, Any] | None,
) -> dict[str, Any]:
    """Atomically reserve identity, persist the task, and enqueue it."""

    service = task_graph_control_service()
    task_id = str(task["task_id"])
    if canonical_task is not None:
        if canonical_graph is None:
            raise DeclaredContractV1Error(
                "task_graph_required",
                [{"path": "/contract_v1", "code": "canonical_graph_not_found"}],
            )
        expected_owner = json.dumps(
            {
                "tenant_id": canonical_task["tenant_id"],
                "case_id": canonical_task["case_id"],
                "graph_id": canonical_graph["graph_id"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    else:
        expected_owner = json.dumps(
            {"kind": "legacy", "task_id": task_id},
            sort_keys=True,
            separators=(",", ":"),
        )
    task["updated_at"] = utc_now()
    reply = redis.command(
        "EVAL",
        EXECUTION_TASK_CREATE_LUA,
        6,
        service.task_identity_owner_key(task_id),
        task_key(task_id),
        (
            key(
                "idempotency:"
                f"{canonical_task['tenant_id']}:{canonical_task['case_id']}:"
                f"{task['idempotency_key']}"
            )
            if canonical_task is not None
            else key(f"idempotency:{task['idempotency_key']}")
        ),
        key("task_ids"),
        key("active_lease_ids"),
        key("queue"),
        expected_owner,
        json.dumps(task, sort_keys=True, separators=(",", ":")),
        task_id,
        "1" if canonical_task is not None else "0",
    )
    outcome = str(reply[0])
    payload = reply[1] if len(reply) > 1 else ""
    if outcome in {"committed", "existing"}:
        return json.loads(payload)
    code = (
        "task_id_already_bound_to_other_authority"
        if outcome == "task_identity_conflict"
        else "idempotency_key_already_bound_to_other_task"
    )
    raise DeclaredContractV1Error(
        "canonical_task_identity_conflict",
        [{"path": "/task_id", "code": code}],
    )


def create_task(
    envelope: dict[str, Any],
    *,
    allow_legacy: bool = False,
) -> dict[str, Any]:
    envelope = dict(envelope)
    canonical_graph: dict[str, Any] | None = None
    canonical_task = parse_declared_contract_v1(
        envelope,
        "kolibri.task",
        bound_id=str(envelope["task_id"]) if envelope.get("task_id") else None,
    )
    if canonical_task is None and not allow_legacy:
        raise DeclaredContractV1Error(
            "legacy_task_http_disabled",
            [{
                "path": "/contract_v1",
                "code": "signed_task_graph_command_required",
            }],
        )
    if canonical_task is not None:
        envelope = project_declared_task_v1(envelope, canonical_task)
        canonical_graph = authoritative_graph_for_canonical_task(
            canonical_task,
        )
    task = normalize_task(envelope)
    if canonical_task is not None:
        existing_by_id = load_task(task["task_id"])
        if existing_by_id is not None:
            existing_contract = parse_declared_contract_v1(
                existing_by_id.get("envelope", {}),
                "kolibri.task",
                bound_id=str(task["task_id"]),
            )
            if existing_contract != canonical_task:
                raise DeclaredContractV1Error(
                    "canonical_task_identity_conflict",
                    [{
                        "path": "/contract_v1/task_id",
                        "code": "task_id_already_bound_to_other_scope",
                    }],
                )
            return existing_by_id
        idem_key = key(
            "idempotency:"
            f"{canonical_task['tenant_id']}:{canonical_task['case_id']}:"
            f"{task['idempotency_key']}",
        )
    else:
        idem_key = key(f"idempotency:{task['idempotency_key']}")
    existing = redis.command("GET", idem_key)
    if existing:
        existing_task = load_task(existing)
        if existing_task:
            return existing_task
    with NODE_UPDATE_LOCK:
        # Re-check locally to avoid unnecessary writes. Cross-process
        # exclusion is enforced by persist_execution_task_atomically() in
        # the same Redis authority used by TaskGraph commits.
        existing = redis.command("GET", idem_key)
        if existing:
            existing_task = load_task(existing)
            if existing_task:
                return existing_task
        task = persist_execution_task_atomically(
            task,
            canonical_task=canonical_task,
            canonical_graph=canonical_graph,
        )
    return task


def unsigned_legacy_task_http_enabled() -> bool:
    """Explicit, temporary compatibility gate for old task producers."""

    return (
        os.environ.get("FACTORY_ALLOW_UNSIGNED_LEGACY_TASK_HTTP", "0")
        == "1"
    )


def _stable_developer_digest(*values: Any) -> str:
    return hashlib.sha256(
        "\0".join(str(value) for value in values).encode("utf-8"),
    ).hexdigest()


DEVELOPER_RUNTIME_PROFILE_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9._-]{1,95}$",
)
DEVELOPER_RUNTIME_PROFILE_CONSTRAINT_PREFIX = "runtime.profile:"
DEVELOPER_RUNTIME_CAPABILITY_PREFIX = "developer.runtime.execute."
TRUSTED_AGENT_BINDING_FIELDS = (
    "trusted_agent_profile_id",
    "trusted_agent_profile_epoch",
    "trusted_agent_workspace_binding_id",
    "trusted_agent_workspace_binding_epoch",
)


def product_developer_trusted_binding(
    payload: dict[str, Any],
) -> dict[str, Any]:
    payload_contract = (
        payload.get("schema_id"),
        payload.get("schema_version"),
    )
    if payload_contract == (
        "kolibri.product.run.execute.v1_2.command",
        "1.2",
    ):
        return {}
    if payload_contract != (
        "kolibri.product.run.execute.v1_3.command",
        "1.3",
    ):
        raise ProductTextRunControlError(
            422,
            "incorrect_payload_schema",
        )
    return {
        field_name: payload[field_name]
        for field_name in TRUSTED_AGENT_BINDING_FIELDS
    }


def _concrete_developer_runtime_profile(value: Any) -> str:
    profile = str(value or "")
    if (
        profile == "auto"
        or not DEVELOPER_RUNTIME_PROFILE_PATTERN.fullmatch(profile)
    ):
        raise ProductTextRunControlError(
            503,
            "product_developer_runtime_profile_invalid",
            [{
                "path": "/payload/runtime_profile",
                "code": "concrete_runtime_profile_required",
            }],
        )
    return profile


def developer_runtime_profile_constraint(runtime_profile: str) -> str:
    profile = _concrete_developer_runtime_profile(runtime_profile)
    return f"{DEVELOPER_RUNTIME_PROFILE_CONSTRAINT_PREFIX}{profile}"


def developer_agent_card_runtime_profile(
    card: dict[str, Any],
) -> str | None:
    markers = [
        constraint[len(DEVELOPER_RUNTIME_PROFILE_CONSTRAINT_PREFIX):]
        for constraint in card.get("policy_constraints", [])
        if isinstance(constraint, str)
        and constraint.startswith(
            DEVELOPER_RUNTIME_PROFILE_CONSTRAINT_PREFIX,
        )
    ]
    if len(markers) != 1:
        return None
    try:
        runtime_profile = _concrete_developer_runtime_profile(markers[0])
    except ProductTextRunControlError:
        return None
    expected_capability = developer_runtime_capability(runtime_profile)
    runtime_capabilities = {
        capability
        for capability in card.get("capabilities", [])
        if isinstance(capability, str)
        and capability.startswith(DEVELOPER_RUNTIME_CAPABILITY_PREFIX)
    }
    if runtime_capabilities != {expected_capability}:
        return None
    return runtime_profile


def resolve_product_developer_auto_profile(
    command: dict[str, Any],
) -> str:
    """Resolve Auto once at Home from exactly one live concrete runtime."""

    payload = command["payload"]
    required_tools = set(
        _product_developer_access_policy(payload)["tool_ids"],
    )
    eligible: list[tuple[str, str]] = []
    for card_id in a2a_agent_card_ids():
        raw_card = redis.command(
            "GET",
            a2a_agent_card_key(card_id),
        )
        if raw_card is None:
            continue
        try:
            card = parse_declared_a2a_agent_card_v1(
                json.loads(raw_card),
            )
        except (DeclaredContractV1Error, json.JSONDecodeError):
            continue
        runtime_profile = developer_agent_card_runtime_profile(card)
        if runtime_profile is None:
            continue
        runtime_capability = developer_runtime_capability(runtime_profile)
        if (
            card["tenant_scope"] not in {
                "platform",
                payload["tenant_id"],
            }
            or card["availability"] != "available"
            or card["agent_kind"] != "worker"
            or not {
                runtime_capability,
                "a2a.message.append",
                "task_owner_state",
            }.issubset(set(card["capabilities"]))
            or not required_tools.issubset(set(card["tool_ids"]))
        ):
            continue
        active_assignments = redis.command(
            "SMEMBERS",
            a2a_agent_card_active_assignments_key(
                card["agent_card_id"],
            ),
        )
        if len(active_assignments) >= int(
            card["limits"]["max_concurrent_assignments"],
        ):
            continue
        eligible.append((card["agent_card_id"], runtime_profile))
    if len(eligible) != 1:
        raise ProductTextRunControlError(
            503,
            "product_developer_auto_profile_unavailable",
            [{
                "path": "/payload/runtime_profile",
                "code": (
                    "ambiguous_runtime_agent_card"
                    if len(eligible) > 1
                    else "eligible_runtime_agent_card_not_found"
                ),
            }],
        )
    return eligible[0][1]


def product_developer_source_key(
    tenant_id: str,
    task_id: str,
) -> str:
    return key(f"product_developer_source:{tenant_id}:{task_id}")


def _product_developer_ids(
    command: dict[str, Any],
) -> dict[str, str]:
    payload = command["payload"]
    run_digest = _stable_developer_digest(
        payload["tenant_id"],
        payload["run_id"],
    )
    return {
        "task_id": f"task_{run_digest[:40]}",
        "graph_id": f"task_graph_{run_digest[:40]}",
        "source_command_ref": f"sourcecmd_{run_digest[:40]}",
        "criterion_id": f"criterion_{run_digest[:40]}",
        "output_id": f"output_{run_digest[:40]}",
        "graph_command_id": f"cmd_{run_digest[:40]}",
        "graph_actor_id": f"service_{run_digest[:40]}",
    }


def _product_developer_case_graph_id(
    command: dict[str, Any],
) -> str:
    payload = command["payload"]
    digest = _stable_developer_digest(
        payload["tenant_id"],
        payload["case_id"],
    )
    return f"task_graph_{digest[:40]}"


def _product_developer_source_record(
    command: dict[str, Any],
    *,
    state: str,
    requested_runtime_profile: str | None = None,
    graph_id: str | None = None,
) -> dict[str, Any]:
    payload = command["payload"]
    identifiers = _product_developer_ids(command)
    access_policy = _product_developer_access_policy(payload)
    runtime_profile = _concrete_developer_runtime_profile(
        payload["runtime_profile"],
    )
    requested_profile = (
        runtime_profile
        if requested_runtime_profile is None
        else str(requested_runtime_profile)
    )
    if not DEVELOPER_RUNTIME_PROFILE_PATTERN.fullmatch(requested_profile):
        raise ProductTextRunControlError(
            503,
            "product_developer_runtime_profile_invalid",
        )
    return {
        "schema_id": "kolibri.product.developer_source_command",
        "schema_version": "1.0",
        "source_command_ref": identifiers["source_command_ref"],
        "tenant_id": payload["tenant_id"],
        "goal_id": payload["goal_id"],
        "case_id": payload["case_id"],
        "run_id": payload["run_id"],
        "task_id": identifiers["task_id"],
        "graph_id": graph_id or identifiers["graph_id"],
        "request_hash": command["idempotency"]["canonical_request_hash"],
        "command_hash": (
            "sha256:"
            + hashlib.sha256(
                json.dumps(
                    command,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8"),
            ).hexdigest()
        ),
        "requested_runtime_profile": requested_profile,
        "runtime_profile": runtime_profile,
        "runtime_capability": developer_runtime_capability(
            runtime_profile,
        ),
        "access_policy": access_policy,
        "state": state,
        "source_command": command,
    }


def _verify_product_developer_source_record(
    record: Any,
    command: dict[str, Any],
    *,
    requested_runtime_profile: str | None = None,
    graph_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ProductTextRunControlError(
            503,
            "product_developer_source_command_invalid",
        )
    expected = _product_developer_source_record(
        command,
        state=str(record.get("state") or ""),
        requested_runtime_profile=requested_runtime_profile,
        graph_id=graph_id,
    )
    for field in (
        "schema_id",
        "schema_version",
        "source_command_ref",
        "tenant_id",
        "goal_id",
        "case_id",
        "run_id",
        "task_id",
        "graph_id",
        "runtime_profile",
        "runtime_capability",
        "access_policy",
    ):
        if record.get(field) != expected[field]:
            raise ProductTextRunControlError(
                503,
                "product_developer_source_command_scope_mismatch",
                [{"path": f"/source_command/{field}", "code": "binding"}],
            )
    record_requested_profile = record.get(
        "requested_runtime_profile",
        record.get("runtime_profile"),
    )
    if (
        record_requested_profile
        != expected["requested_runtime_profile"]
    ):
        raise ProductTextRunControlError(
            503,
            "product_developer_source_command_scope_mismatch",
            [{
                "path": "/source_command/requested_runtime_profile",
                "code": "binding",
            }],
        )
    if not hmac.compare_digest(
        str(record.get("request_hash") or ""),
        expected["request_hash"],
    ):
        raise ProductTextRunControlError(409, "idempotency_conflict")
    if not hmac.compare_digest(
        str(record.get("command_hash") or ""),
        expected["command_hash"],
    ) or record.get("source_command") != command:
        raise ProductTextRunControlError(
            409,
            "idempotency_provenance_conflict",
        )
    if record.get("state") not in {"reserved", "ready"}:
        raise ProductTextRunControlError(
            503,
            "product_developer_source_command_invalid",
        )
    return record


def _bind_product_developer_source_resolution(
    record: Any,
    command: dict[str, Any],
    *,
    requested_runtime_profile: str,
    graph_id: str,
) -> dict[str, Any]:
    """Bind a replay to the profile already frozen by the winning admission."""

    if not isinstance(record, dict):
        raise ProductTextRunControlError(
            503,
            "product_developer_source_command_invalid",
        )
    identifiers = _product_developer_ids(command)
    payload = command["payload"]
    expected_bindings = {
        "schema_id": "kolibri.product.developer_source_command",
        "schema_version": "1.0",
        "source_command_ref": identifiers["source_command_ref"],
        "tenant_id": payload["tenant_id"],
        "goal_id": payload["goal_id"],
        "case_id": payload["case_id"],
        "run_id": payload["run_id"],
        "task_id": identifiers["task_id"],
        "graph_id": graph_id,
    }
    for field, expected in expected_bindings.items():
        if record.get(field) != expected:
            raise ProductTextRunControlError(
                503,
                "product_developer_source_command_scope_mismatch",
                [{"path": f"/source_command/{field}", "code": "binding"}],
            )
    if not hmac.compare_digest(
        str(record.get("request_hash") or ""),
        str(command["idempotency"]["canonical_request_hash"]),
    ):
        raise ProductTextRunControlError(409, "idempotency_conflict")
    record_requested_profile = record.get(
        "requested_runtime_profile",
        record.get("runtime_profile"),
    )
    if record_requested_profile != requested_runtime_profile:
        raise ProductTextRunControlError(
            409,
            "idempotency_provenance_conflict",
        )
    runtime_profile = _concrete_developer_runtime_profile(
        record.get("runtime_profile"),
    )
    if record.get("runtime_capability") != developer_runtime_capability(
        runtime_profile,
    ):
        raise ProductTextRunControlError(
            503,
            "product_developer_source_command_scope_mismatch",
            [{
                "path": "/source_command/runtime_capability",
                "code": "binding",
            }],
        )
    source_command = record.get("source_command")
    if (
        not isinstance(source_command, dict)
        or not isinstance(source_command.get("payload"), dict)
        or source_command["payload"].get("runtime_profile")
        != runtime_profile
    ):
        raise ProductTextRunControlError(
            503,
            "product_developer_source_command_invalid",
        )
    command["payload"]["runtime_profile"] = runtime_profile
    return record


def _product_developer_access_policy(
    payload: dict[str, Any],
) -> dict[str, Any]:
    requested = (
        payload["access_mode"],
        payload["sandbox"],
        payload["approval_policy"],
        payload["reviewer"],
    )
    if requested == (
        "auto",
        "workspace-write",
        "on-request",
        "auto_review",
    ):
        return {
            "policy_id": "developer.workspace_guarded",
            "tool_ids": [
                "tool.repository.read",
                "tool.repository.write",
                "tool.shell.workspace",
            ],
            "compute_units_limit": 100_000,
            "tool_calls_limit": 2_000,
        }
    if requested == (
        "full",
        "danger-full-access",
        "never",
        None,
    ):
        if os.environ.get(
            "FACTORY_DEVELOPER_FULL_ACCESS_ENABLED",
            "0",
        ) != "1":
            raise ProductTextRunControlError(
                403,
                "product_developer_full_access_not_approved",
                [{
                    "path": "/payload/access_mode",
                    "code": "server_policy_denied",
                }],
            )
        return {
            "policy_id": "developer.full_owner_approved",
            "tool_ids": [
                "tool.filesystem.full",
                "tool.network.full",
                "tool.shell.full",
            ],
            "compute_units_limit": 1_000_000,
            "tool_calls_limit": 20_000,
        }
    raise ProductTextRunControlError(
        422,
        "product_developer_access_policy_mismatch",
        [{
            "path": "/payload/access_mode",
            "code": "unsupported_policy_combination",
        }],
    )


def _product_developer_canonical_task(
    command: dict[str, Any],
    *,
    requested_at: str,
    graph_version: int = 1,
) -> dict[str, Any]:
    payload = command["payload"]
    identifiers = _product_developer_ids(command)
    capability = developer_runtime_capability(payload["runtime_profile"])
    policy = _product_developer_access_policy(payload)
    risk_class = (
        "critical"
        if payload["sandbox"] == "danger-full-access"
        else "high"
    )
    return HOME_CONTRACTS_V1.prepare_outbound(
        {
            "schema_id": "kolibri.task",
            "schema_version": "1.0",
            "task_id": identifiers["task_id"],
            "tenant_id": payload["tenant_id"],
            "goal_id": payload["goal_id"],
            "case_id": payload["case_id"],
            "title": "Выполнить developer-команду владельца",
            "objective": developer_task_objective(
                identifiers["source_command_ref"],
            ),
            "kind": "developer.runtime.execute",
            "parent_task_id": None,
            "dependency_task_ids": [],
            "required_capabilities": [capability],
            "acceptance_criteria": [{
                "criterion_id": identifiers["criterion_id"],
                "statement": (
                    "Назначенный runtime вернул типизированный A2A handoff "
                    "или rejection с тем же lease fence."
                ),
                "verification_method": (
                    "Проверка TaskAttempt, AgentAssignment, A2A cursor и "
                    "fencing token кодом Logical Home."
                ),
                "required": True,
            }],
            "expected_outputs": [{
                "output_id": identifiers["output_id"],
                "artifact_type": "developer_execution_result",
                "schema_id": "kolibri.a2a.message_appended.event",
                "evidence_required": True,
            }],
            "budget": {
                "compute_units_limit": policy[
                    "compute_units_limit"
                ],
                "tool_calls_limit": policy["tool_calls_limit"],
                "external_spend_limit_minor": 0,
                "currency": "RUB",
            },
            "deadline_at": command["deadline_at"],
            "risk_class": risk_class,
            "state": "proposed",
            "graph_version": graph_version,
            "version": 1,
            "current_attempt_id": None,
            "current_assignment_id": None,
            "created_at": requested_at,
            "updated_at": requested_at,
        },
        "kolibri.task",
    )


def _product_developer_graph_command(
    command: dict[str, Any],
    task: dict[str, Any],
    *,
    requested_at: str,
    graph_id: str,
    previous_graph: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = command["payload"]
    identifiers = _product_developer_ids(command)
    grant = logical_home_server_authority_grant()
    required_grant_fields = (
        "authority_id",
        "authority_placement_id",
        "authorization_decision_id",
    )
    if (
        any(not str(grant.get(field) or "").strip() for field in required_grant_fields)
        or int(grant.get("authority_epoch") or 0) < 1
        or "task_graph.apply" not in (grant.get("capabilities") or [])
    ):
        raise ProductTextRunControlError(
            503,
            "logical_home_task_graph_authority_not_configured",
        )
    expected_graph_version = (
        int(previous_graph["graph_version"])
        if previous_graph is not None
        else 0
    )
    next_graph_version = expected_graph_version + 1
    graph_tasks = []
    if previous_graph is not None:
        graph_tasks = [
            {
                **existing_task,
                "graph_version": next_graph_version,
            }
            for existing_task in previous_graph["tasks"]
        ]
    graph_tasks.append(task)
    identity = {
        "tenant_id": payload["tenant_id"],
        "user_id": None,
        "actor": {
            "actor_id": identifiers["graph_actor_id"],
            "actor_type": "system",
        },
        "authority": {
            "authority_id": grant["authority_id"],
            "authority_role": "logical_home_control_plane",
            "authority_epoch": int(grant["authority_epoch"]),
            "authority_placement_id": grant[
                "authority_placement_id"
            ],
            "authorization_decision_id": grant[
                "authorization_decision_id"
            ],
            "capabilities": ["task_graph.apply"],
        },
        "subject_refs": {
            "goal_id": payload["goal_id"],
            "case_id": payload["case_id"],
            "task_id": None,
        },
    }
    graph_command = {
        "schema_id": "kolibri.command",
        "schema_version": "1.0",
        "message_id": identifiers["graph_command_id"],
        "command_name": "task_graph.apply",
        "payload_schema_id": "kolibri.task_graph.apply.command",
        "payload_schema_version": "1.0",
        "issued_at": command["issued_at"],
        "deadline_at": command["deadline_at"],
        "target_owner": "logical_home_control_plane",
        "identity": identity,
        "trace": {
            **command["trace"],
            "causation_id": command["message_id"],
        },
        "idempotency": {
            "key": (
                "product.developer.task_graph:"
                f"{payload['run_id']}"
            ),
            "scope": "case",
            "scope_id": payload["case_id"],
            "canonical_request_hash": "sha256:" + ("0" * 64),
        },
        "payload": {
            "schema_id": "kolibri.task_graph.apply.command",
            "schema_version": "1.0",
            "graph_id": graph_id,
            "tenant_id": payload["tenant_id"],
            "goal_id": payload["goal_id"],
            "case_id": payload["case_id"],
            "expected_graph_version": expected_graph_version,
            "next_graph_version": next_graph_version,
            "tasks": graph_tasks,
            "reason": "Home-owned developer dispatch admission.",
            "requested_at": requested_at,
        },
    }
    graph_command["idempotency"]["canonical_request_hash"] = (
        canonical_request_hash(graph_command)
    )
    return graph_command, {
        "tenant_id": identity["tenant_id"],
        "user_id": identity["user_id"],
        "actor": identity["actor"],
        "authority": grant,
    }


def _ready_product_developer_graph(
    graph: dict[str, Any],
    *,
    task_id: str,
    requested_at: str,
) -> dict[str, Any]:
    graph_service = task_graph_control_service()
    task = next(
        (
            dict(candidate)
            for candidate in graph["tasks"]
            if candidate["task_id"] == task_id
        ),
        None,
    )
    if task is None:
        raise ProductTextRunControlError(
            409,
            "product_developer_task_graph_conflict",
        )
    task.update({
        "state": "accepted",
        "version": int(task["version"]) + 1,
        "updated_at": requested_at,
    })
    task = HOME_CONTRACTS_V1.prepare_outbound(task, "kolibri.task")
    graph = graph_service.project_task_transition(
        graph,
        task,
        requested_at=requested_at,
    )
    task = next(
        dict(candidate)
        for candidate in graph["tasks"]
        if candidate["task_id"] == task_id
    )
    task.update({
        "state": "ready",
        "version": int(task["version"]) + 1,
        "updated_at": requested_at,
    })
    task = HOME_CONTRACTS_V1.prepare_outbound(task, "kolibri.task")
    return graph_service.project_task_transition(
        graph,
        task,
        requested_at=requested_at,
    )


def admit_product_developer_run(
    command: dict[str, Any],
    admit_new: bool,
) -> tuple[dict[str, Any], bool]:
    """Admit one developer command as a Home-owned canonical graph."""

    payload = command["payload"]
    requested_runtime_profile = payload["runtime_profile"]
    identifiers = _product_developer_ids(command)
    graph_service = task_graph_control_service()
    case_graph_id = redis.command(
        "GET",
        graph_service.case_graph_key(
            payload["tenant_id"],
            payload["case_id"],
        ),
    )
    selected_graph_id = (
        str(case_graph_id)
        if case_graph_id
        else _product_developer_case_graph_id(command)
    )
    source_key = product_developer_source_key(
        payload["tenant_id"],
        identifiers["task_id"],
    )
    raw_source = redis.command("GET", source_key)
    created = False
    if raw_source is None:
        if not admit_new:
            raise ProductTextRunControlError(
                408,
                "command_expired",
                [{
                    "path": "/deadline_at",
                    "code": "execution_not_admitted_before_deadline",
                }],
            )
        runtime_profile = (
            resolve_product_developer_auto_profile(command)
            if requested_runtime_profile == "auto"
            else _concrete_developer_runtime_profile(
                requested_runtime_profile,
            )
        )
        payload["runtime_profile"] = runtime_profile
        reserved = _product_developer_source_record(
            command,
            state="reserved",
            requested_runtime_profile=requested_runtime_profile,
            graph_id=selected_graph_id,
        )
        reserved_json = json.dumps(
            reserved,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        reply = redis.command("SET", source_key, reserved_json, "NX")
        if reply == "OK":
            raw_source = reserved_json
            created = True
        else:
            raw_source = redis.command("GET", source_key)
    try:
        parsed_source = json.loads(str(raw_source))
        _bind_product_developer_source_resolution(
            parsed_source,
            command,
            requested_runtime_profile=requested_runtime_profile,
            graph_id=selected_graph_id,
        )
        source = _verify_product_developer_source_record(
            parsed_source,
            command,
            requested_runtime_profile=requested_runtime_profile,
            graph_id=selected_graph_id,
        )
    except ProductTextRunControlError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProductTextRunControlError(
            503,
            "product_developer_source_command_invalid",
        ) from exc

    graph = graph_service.load_graph(
        payload["tenant_id"],
        selected_graph_id,
    )
    if source["state"] == "reserved":
        if not admit_new and graph is None:
            raise ProductTextRunControlError(
                408,
                "command_expired",
                [{
                    "path": "/deadline_at",
                    "code": "execution_not_admitted_before_deadline",
                }],
            )
        for admission_attempt in range(
            PRODUCT_DEVELOPER_ADMISSION_CAS_ATTEMPTS,
        ):
            graph = graph_service.load_graph(
                payload["tenant_id"],
                selected_graph_id,
            )
            requested_at = utc_now()
            graph_task = (
                next(
                    (
                        task
                        for task in graph["tasks"]
                        if task["task_id"] == identifiers["task_id"]
                    ),
                    None,
                )
                if graph is not None
                else None
            )
            if graph_task is None:
                next_graph_version = (
                    int(graph["graph_version"]) + 1
                    if graph is not None
                    else 1
                )
                canonical_task = _product_developer_canonical_task(
                    command,
                    requested_at=requested_at,
                    graph_version=next_graph_version,
                )
                internal_command, transport = (
                    _product_developer_graph_command(
                        command,
                        canonical_task,
                        requested_at=requested_at,
                        graph_id=selected_graph_id,
                        previous_graph=graph,
                    )
                )
                try:
                    _, result = graph_service.process(
                        internal_command,
                        transport_context=transport,
                    )
                except TaskGraphCommandError as exc:
                    if (
                        exc.code in {
                            "graph_version_conflict",
                            "task_graph_exists",
                        }
                        and admission_attempt
                        < PRODUCT_DEVELOPER_ADMISSION_CAS_ATTEMPTS - 1
                    ):
                        continue
                    raise ProductTextRunControlError(
                        exc.status,
                        exc.code,
                        exc.violations,
                    ) from exc
                graph = result["task_graph"]
                graph_task = next(
                    (
                        task
                        for task in graph["tasks"]
                        if task["task_id"] == identifiers["task_id"]
                    ),
                    None,
                )
            if (
                graph_task is None
                or graph["tenant_id"] != payload["tenant_id"]
                or graph["goal_id"] != payload["goal_id"]
                or graph["case_id"] != payload["case_id"]
                or graph_task["state"] not in {
                    "proposed",
                    "accepted",
                    "ready",
                }
            ):
                raise ProductTextRunControlError(
                    409,
                    "product_developer_task_graph_conflict",
                )
            ready_graph = (
                graph
                if graph_task["state"] == "ready"
                else _ready_product_developer_graph(
                    graph,
                    task_id=identifiers["task_id"],
                    requested_at=requested_at,
                )
            )
            ready_source = {
                **source,
                "state": "ready",
            }
            expected_graph_json = redis.command(
                "GET",
                graph_service.graph_key(
                    payload["tenant_id"],
                    selected_graph_id,
                ),
            )
            if expected_graph_json is None:
                raise ProductTextRunControlError(
                    503,
                    "product_developer_task_graph_missing",
                )
            if json.loads(str(expected_graph_json)) != graph:
                if (
                    admission_attempt
                    < PRODUCT_DEVELOPER_ADMISSION_CAS_ATTEMPTS - 1
                ):
                    continue
                raise ProductTextRunControlError(
                    409,
                    "product_developer_admission_conflict",
                )
            ready_source_json = json.dumps(
                ready_source,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            ready_graph_json = json.dumps(
                ready_graph,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            reply = redis.command(
                "EVAL",
                PRODUCT_DEVELOPER_ADMISSION_LUA,
                2,
                graph_service.graph_key(
                    payload["tenant_id"],
                    selected_graph_id,
                ),
                source_key,
                expected_graph_json,
                json.dumps(
                    source,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ),
                ready_source_json,
                ready_graph_json,
            )
            if str(reply[0]) == "committed":
                graph = json.loads(str(reply[1]))
                break
            if (
                str(reply[0]) == "stale_task_graph_revision"
                and admission_attempt
                < PRODUCT_DEVELOPER_ADMISSION_CAS_ATTEMPTS - 1
            ):
                continue
            raise ProductTextRunControlError(
                409,
                "product_developer_admission_conflict",
            )
        else:
            raise ProductTextRunControlError(
                409,
                "product_developer_admission_conflict",
            )
    elif graph is None:
        raise ProductTextRunControlError(
            503,
            "product_developer_task_graph_missing",
        )

    graph_task = next(
        (
            task
            for task in graph["tasks"]
            if task["task_id"] == identifiers["task_id"]
        ),
        None,
    )
    if (
        graph_task is None
        or graph_task["state"] not in {
            "ready",
            "leased",
            "running",
            "submitted",
            "verifying",
            "completed",
            "failed_terminal",
        }
    ):
        raise ProductTextRunControlError(
            503,
            "product_developer_task_graph_invalid",
        )
    reconcile_task_graph_execution(graph)
    task = load_task(identifiers["task_id"])
    if task is None:
        raise ProductTextRunControlError(
            503,
            "product_developer_execution_task_missing",
        )
    return task, created


def load_product_developer_source(
    canonical_task: dict[str, Any],
) -> dict[str, Any] | None:
    raw = redis.command(
        "GET",
        product_developer_source_key(
            canonical_task["tenant_id"],
            canonical_task["task_id"],
        ),
    )
    if raw is None:
        return None
    try:
        source = json.loads(str(raw))
    except (TypeError, ValueError):
        raise DeclaredContractV1Error(
            "product_developer_source_invalid",
            [{"path": "/source_command_ref", "code": "invalid"}],
        )
    if (
        not isinstance(source, dict)
        or source.get("state") != "ready"
        or source.get("tenant_id") != canonical_task["tenant_id"]
        or source.get("goal_id") != canonical_task["goal_id"]
        or source.get("case_id") != canonical_task["case_id"]
        or source.get("task_id") != canonical_task["task_id"]
    ):
        raise DeclaredContractV1Error(
            "product_developer_source_invalid",
            [{"path": "/source_command_ref", "code": "binding"}],
        )
    try:
        return _verify_product_developer_source_record(
            source,
            source["source_command"],
            requested_runtime_profile=str(
                source.get(
                    "requested_runtime_profile",
                    source["runtime_profile"],
                ),
            ),
            graph_id=str(source["graph_id"]),
        )
    except (KeyError, ProductTextRunControlError) as exc:
        raise DeclaredContractV1Error(
            "product_developer_source_invalid",
            [{"path": "/source_command_ref", "code": "hash_binding"}],
        ) from exc


def _canonical_execution_envelope(
    canonical_task: dict[str, Any],
) -> dict[str, Any]:
    """Build the deterministic legacy projection for one runnable graph task."""

    envelope = {
        "task_id": canonical_task["task_id"],
        "idempotency_key": (
            "task-graph:"
            f"{canonical_task['tenant_id']}:"
            f"{canonical_task['case_id']}:"
            f"{canonical_task['task_id']}"
        ),
        "contract_v1": canonical_task,
    }
    source = load_product_developer_source(canonical_task)
    if source is not None:
        payload = source["source_command"]["payload"]
        trusted_binding = product_developer_trusted_binding(payload)
        trusted_bound = bool(trusted_binding)
        envelope.update({
            "max_retries": 0,
            "tenant_id": payload["tenant_id"],
            "project_id": payload["project_id"],
            "thread_id": payload["thread_id"],
            "run_id": payload["run_id"],
            "input_message_id": payload["input_message_id"],
            "case_id": payload["case_id"],
            "goal_id": payload["goal_id"],
            "trace_id": source["source_command"]["trace"]["trace_id"],
            "source": {
                "kind": (
                    "product_run_execute_v1_3"
                    if trusted_bound
                    else "product_run_execute_v1_2"
                ),
                "message_id": source["source_command"]["message_id"],
                "source_command_ref": source["source_command_ref"],
                "accepted_by": "logical_home_control_plane",
            },
            "developer_dispatch": {
                "schema_id": (
                    "kolibri.product.developer_dispatch.v1_1"
                    if trusted_bound
                    else "kolibri.product.developer_dispatch"
                ),
                "schema_version": "1.1" if trusted_bound else "1.0",
                "source_command_ref": source["source_command_ref"],
                "run_id": payload["run_id"],
                "project_id": payload["project_id"],
                "thread_id": payload["thread_id"],
                "input_message_id": payload["input_message_id"],
                "runtime_profile": payload["runtime_profile"],
                "runtime_capability": source["runtime_capability"],
                "model": payload["model"],
                "reasoning_effort": payload["reasoning_effort"],
                "service_tier": payload["service_tier"],
                "workspace_ref": payload["workspace_ref"],
                "access_mode": payload["access_mode"],
                "sandbox": payload["sandbox"],
                "approval_policy": payload["approval_policy"],
                "reviewer": payload["reviewer"],
                **trusted_binding,
            },
        })
    return project_declared_task_v1(envelope, canonical_task)


def reconcile_task_graph_execution(
    graph: dict[str, Any],
) -> dict[str, Any]:
    """Repair the legacy execution cache from one canonical Task Graph.

    Task Graph remains the source of truth. The legacy task records and list
    are disposable execution projections: missing entries are recreated,
    queued stale versions are refreshed, and no-longer-runnable entries are
    removed before a worker can lease them.
    """

    runnable_ids = set(graph["runnable_task_ids"])
    materialized: list[str] = []
    removed: list[str] = []
    conflicts: list[str] = []
    tasks_by_id = {
        task["task_id"]: task
        for task in graph["tasks"]
    }
    for task_id in sorted(tasks_by_id):
        canonical_task = tasks_by_id[task_id]
        existing = load_task(task_id)
        existing_contract: dict[str, Any] | None = None
        if existing is not None:
            try:
                existing_contract = parse_declared_contract_v1(
                    existing.get("envelope", {}),
                    "kolibri.task",
                    bound_id=task_id,
                )
            except DeclaredContractV1Error:
                remove_from_queue(task_id)
                conflicts.append(task_id)
                continue
            if existing_contract is None:
                # A legacy task already owns this globally-addressed runtime
                # id. Never overwrite it with another tenant's canonical task.
                remove_from_queue(task_id)
                conflicts.append(task_id)
                continue
            existing_scope = (
                existing_contract["tenant_id"],
                existing_contract["case_id"],
            )
            canonical_scope = (
                canonical_task["tenant_id"],
                canonical_task["case_id"],
            )
            if existing_scope != canonical_scope:
                # Keep the original owner's record intact but do not allow a
                # second tenant to receive or overwrite it.
                conflicts.append(task_id)
                continue

        if task_id not in runnable_ids:
            if (
                existing is not None
                and existing_contract is not None
                and existing.get("state") in {
                    STATE_QUEUED,
                    STATE_REVIEW,
                    STATE_RETRY,
                }
            ):
                remove_from_queue(task_id)
                removed.append(task_id)
            continue

        projection = _canonical_execution_envelope(canonical_task)
        if existing is None:
            create_task(projection)
            materialized.append(task_id)
            continue
        if existing_contract != canonical_task:
            if existing.get("state") not in {
                STATE_QUEUED,
                STATE_REVIEW,
                STATE_RETRY,
            }:
                # Graph relation updates are forbidden for active tasks. If a
                # corrupt/stale active sidecar is nevertheless observed, fail
                # closed and leave it unavailable for another lease.
                remove_from_queue(task_id)
                conflicts.append(task_id)
                continue
            existing["envelope"] = projection
            existing["kind"] = canonical_task["kind"]
            existing["state"] = STATE_QUEUED
            save_task(existing)
        elif existing.get("state") not in {
            STATE_QUEUED,
            STATE_REVIEW,
            STATE_RETRY,
        }:
            # An active task is already owned by its lease; a terminal task
            # cannot be resurrected merely because a stale graph says ready.
            if existing.get("state") in TERMINAL_STATES:
                remove_from_queue(task_id)
                conflicts.append(task_id)
            continue
        enqueue(task_id)
        materialized.append(task_id)

    return {
        "graph_id": graph["graph_id"],
        "graph_version": graph["graph_version"],
        "materialized_task_ids": materialized,
        "removed_task_ids": removed,
        "conflict_task_ids": conflicts,
    }


def reconcile_all_task_graph_execution() -> list[dict[str, Any]]:
    """Rebuild every canonical runnable projection after crash or restart."""

    service = task_graph_control_service()
    results: list[dict[str, Any]] = []
    for ref in service.list_graph_refs():
        graph = service.load_graph(ref["tenant_id"], ref["graph_id"])
        if graph is None:
            raise TaskGraphCommandError(
                500,
                "stored_task_graph_ref_missing",
                [{
                    "path": "/stored_task_graph_refs",
                    "code": "referenced_graph_not_found",
                }],
            )
        results.append(reconcile_task_graph_execution(graph))
    return results


def canonical_lease_queue_ids() -> list[str]:
    """Return runnable canonical work first, in graph-stable lexical order."""

    canonical: list[tuple[tuple[str, str, str, str], str]] = []
    legacy: list[tuple[int, str]] = []
    seen: set[str] = set()
    for position, task_id in enumerate(queue_ids()):
        if task_id in seen:
            continue
        seen.add(task_id)
        task = load_task(task_id)
        if task is None:
            remove_from_queue(task_id)
            continue
        try:
            canonical_task = parse_declared_contract_v1(
                task.get("envelope", {}),
                "kolibri.task",
                bound_id=task_id,
            )
            if canonical_task is None:
                legacy.append((position, task_id))
                continue
            authoritative_graph_for_canonical_task(canonical_task)
        except DeclaredContractV1Error:
            remove_from_queue(task_id)
            continue
        canonical.append((
            (
                canonical_task["tenant_id"],
                canonical_task["goal_id"],
                canonical_task["case_id"],
                canonical_task["task_id"],
            ),
            task_id,
        ))
    return (
        [task_id for _, task_id in sorted(canonical)]
        + [task_id for _, task_id in sorted(legacy)]
    )


def create_review_task(source_task: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:
    envelope = source_task.get("envelope", {})
    if not envelope.get("create_review_on_complete"):
        return None
    pr_url = result.get("pull_request_url") or result.get("pr_url")
    if not pr_url:
        return None
    review_id = envelope.get("review_task_id") or f"{source_task['task_id']}-REVIEW"
    review_envelope = {
        "task_id": review_id,
        "idempotency_key": f"review:{source_task['task_id']}",
        "kind": "review_pr",
        "target_node": envelope.get("review_node", "new"),
        "required_capability": "review",
        "source_task_id": source_task["task_id"],
        "pull_request_url": pr_url,
        "branch": result.get("branch"),
        "base_ref": envelope.get("base_ref", "origin/main"),
        "max_retries": envelope.get("review_max_retries", MAX_RETRIES),
    }
    review = create_task(
        review_envelope,
        allow_legacy=unsigned_legacy_task_http_enabled(),
    )
    review["state"] = STATE_REVIEW if review["state"] == STATE_QUEUED else review["state"]
    save_task(review)
    return review


class AgentControlAuthError(RuntimeError):
    """A response-safe rejection at the AgentHost workload boundary."""

    def __init__(self, code: str, *, status: int = 401):
        super().__init__(code)
        self.code = code
        self.status = status


class A2AMutationControlError(ValueError):
    """Fail-closed rejection for Logical Home-owned A2A mutations."""

    def __init__(
        self,
        status: int,
        code: str,
        violations: list[dict[str, str]] | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.violations = violations or []
        super().__init__(code)

    def as_dict(self) -> dict[str, Any]:
        return {
            "error": "a2a_mutation_rejected",
            "code": self.code,
            "violations": self.violations,
        }


class RequestBodyError(RuntimeError):
    """A response-safe rejection before JSON or auth processing."""

    def __init__(self, code: str, *, status: int):
        super().__init__(code)
        self.code = code
        self.status = status


def _read_agent_control_secret() -> bytes:
    """Load the workload secret from the dedicated file-only binding."""

    raw_path = (
        os.environ.get(FACTORY_AGENT_CONTROL_TOKEN_FILE_ENV) or ""
    ).strip()
    if not raw_path:
        raise AgentControlAuthError(
            "agent_control_auth_unconfigured",
            status=503,
        )
    path = Path(raw_path)
    if not path.is_absolute() or ".." in path.parts:
        raise AgentControlAuthError(
            "agent_control_token_file_invalid",
            status=503,
        )
    try:
        info = path.lstat()
    except OSError as exc:
        raise AgentControlAuthError(
            "agent_control_token_file_unreadable",
            status=503,
        ) from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or not 32 <= info.st_size <= 514
        or not os.access(path, os.R_OK)
    ):
        raise AgentControlAuthError(
            "agent_control_token_file_invalid",
            status=503,
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AgentControlAuthError(
            "agent_control_token_file_unreadable",
            status=503,
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != info.st_dev
            or opened.st_ino != info.st_ino
            or opened.st_size != info.st_size
        ):
            raise AgentControlAuthError(
                "agent_control_token_file_invalid",
                status=503,
            )
        payload = os.read(descriptor, 515)
        if len(payload) > 514 or os.read(descriptor, 1):
            raise AgentControlAuthError(
                "agent_control_token_file_invalid",
                status=503,
            )
    except OSError as exc:
        raise AgentControlAuthError(
            "agent_control_token_file_unreadable",
            status=503,
        ) from exc
    finally:
        os.close(descriptor)
    if payload.endswith(b"\n"):
        payload = payload[:-1]
        if payload.endswith(b"\r"):
            payload = payload[:-1]
    try:
        token = payload.decode("ascii")
    except UnicodeError as exc:
        raise AgentControlAuthError(
            "agent_control_token_invalid",
            status=503,
        ) from exc
    if not AGENT_CONTROL_TOKEN_PATTERN.fullmatch(token):
        raise AgentControlAuthError(
            "agent_control_token_invalid",
            status=503,
        )
    return payload


def _read_agent_control_identity_map() -> dict[
    tuple[str, str],
    dict[str, Any],
] | None:
    """Load a fail-closed per-workload keyring for the Product agent edge.

    The legacy single-identity binding remains supported for existing
    deployments.  A keyring is deliberately mutually exclusive with it so a
    broad fallback secret cannot silently defeat per-agent isolation.
    """

    raw_path = (
        os.environ.get(
            FACTORY_AGENT_CONTROL_IDENTITY_MAP_FILE_ENV,
        )
        or ""
    ).strip()
    if not raw_path:
        return None
    legacy_names = (
        FACTORY_AGENT_CONTROL_TOKEN_FILE_ENV,
        FACTORY_AGENT_CONTROL_ALLOWED_NODE_ID_ENV,
        FACTORY_AGENT_CONTROL_ALLOWED_AGENT_ID_ENV,
        FACTORY_AGENT_CONTROL_ALLOWED_CAPABILITIES_ENV,
    )
    if any((os.environ.get(name) or "").strip() for name in legacy_names):
        raise AgentControlAuthError(
            "agent_control_auth_configuration_ambiguous",
            status=503,
        )

    path = Path(raw_path)
    if not path.is_absolute() or ".." in path.parts:
        raise AgentControlAuthError(
            "agent_control_identity_map_file_invalid",
            status=503,
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        before = path.lstat()
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AgentControlAuthError(
            "agent_control_identity_map_file_unreadable",
            status=503,
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or before.st_dev != opened.st_dev
            or before.st_ino != opened.st_ino
            or opened.st_nlink != 1
            or opened.st_uid not in {0, os.geteuid()}
            or stat.S_IMODE(opened.st_mode) & 0o077
            or not 2 <= opened.st_size <= 32 * 1024
        ):
            raise AgentControlAuthError(
                "agent_control_identity_map_file_invalid",
                status=503,
            )
        payload = os.read(descriptor, 32 * 1024 + 1)
        if len(payload) > 32 * 1024 or os.read(descriptor, 1):
            raise AgentControlAuthError(
                "agent_control_identity_map_file_invalid",
                status=503,
            )
    except OSError as exc:
        raise AgentControlAuthError(
            "agent_control_identity_map_file_unreadable",
            status=503,
        ) from exc
    finally:
        os.close(descriptor)

    try:
        document = json.loads(payload.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AgentControlAuthError(
            "agent_control_identity_map_invalid",
            status=503,
        ) from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"version", "identities"}
        or document.get("version") != 1
        or not isinstance(document.get("identities"), list)
        or not 1 <= len(document["identities"]) <= 16
    ):
        raise AgentControlAuthError(
            "agent_control_identity_map_invalid",
            status=503,
        )

    credentials: dict[tuple[str, str], dict[str, Any]] = {}
    seen_nodes: set[str] = set()
    seen_agents: set[str] = set()
    seen_secrets: set[bytes] = set()
    for entry in document["identities"]:
        if (
            not isinstance(entry, dict)
            or set(entry)
            != {"node_id", "agent_id", "secret", "capabilities"}
        ):
            raise AgentControlAuthError(
                "agent_control_identity_map_invalid",
                status=503,
            )
        node_id = entry.get("node_id")
        agent_id = entry.get("agent_id")
        secret_text = entry.get("secret")
        raw_capabilities = entry.get("capabilities")
        if (
            not isinstance(node_id, str)
            or not AGENT_CONTROL_IDENTITY_PATTERN.fullmatch(node_id)
            or not isinstance(agent_id, str)
            or not AGENT_CONTROL_IDENTITY_PATTERN.fullmatch(agent_id)
            or not isinstance(secret_text, str)
            or not AGENT_CONTROL_TOKEN_PATTERN.fullmatch(secret_text)
            or not isinstance(raw_capabilities, list)
            or not 1 <= len(raw_capabilities) <= 32
            or any(
                not isinstance(capability, str)
                or not AGENT_CONTROL_CAPABILITY_PATTERN.fullmatch(
                    capability,
                )
                for capability in raw_capabilities
            )
        ):
            raise AgentControlAuthError(
                "agent_control_identity_map_invalid",
                status=503,
            )
        capabilities = normalized_string_list(raw_capabilities)
        secret = secret_text.encode("ascii")
        identity_key = (node_id, agent_id)
        if (
            len(capabilities) != len(raw_capabilities)
            or identity_key in credentials
            or node_id in seen_nodes
            or agent_id in seen_agents
            or secret in seen_secrets
        ):
            raise AgentControlAuthError(
                "agent_control_identity_map_invalid",
                status=503,
            )
        credentials[identity_key] = {
            "secret": secret,
            "allowed_capabilities": capabilities,
        }
        seen_nodes.add(node_id)
        seen_agents.add(agent_id)
        seen_secrets.add(secret)
    return credentials


def agent_control_signature_payload(
    *,
    method: str,
    logical_path: str,
    timestamp: str,
    nonce: str,
    node_id: str,
    agent_id: str,
    body_sha256: str,
) -> bytes:
    return "\n".join((
        method.upper(),
        logical_path,
        timestamp,
        nonce,
        node_id,
        agent_id,
        body_sha256,
    )).encode("utf-8")


def _agent_control_timestamp_window() -> int:
    raw = os.environ.get(
        "FACTORY_AGENT_CONTROL_TIMESTAMP_WINDOW_SECONDS",
        "60",
    )
    try:
        value = int(raw)
    except ValueError as exc:
        raise AgentControlAuthError(
            "agent_control_timestamp_window_invalid",
            status=503,
        ) from exc
    if not 5 <= value <= 300:
        raise AgentControlAuthError(
            "agent_control_timestamp_window_invalid",
            status=503,
        )
    return value


def _configured_agent_control_identity() -> tuple[str, str]:
    """Return the one workload identity authorized to use the remote secret."""

    node_id = os.environ.get(
        FACTORY_AGENT_CONTROL_ALLOWED_NODE_ID_ENV,
        "",
    )
    agent_id = os.environ.get(
        FACTORY_AGENT_CONTROL_ALLOWED_AGENT_ID_ENV,
        "",
    )
    if not node_id or not agent_id:
        raise AgentControlAuthError(
            "agent_control_allowed_identity_unconfigured",
            status=503,
        )
    if (
        not AGENT_CONTROL_IDENTITY_PATTERN.fullmatch(node_id)
        or not AGENT_CONTROL_IDENTITY_PATTERN.fullmatch(agent_id)
    ):
        raise AgentControlAuthError(
            "agent_control_allowed_identity_invalid",
            status=503,
        )
    return node_id, agent_id


def _configured_agent_control_capabilities() -> list[str]:
    raw = os.environ.get(
        FACTORY_AGENT_CONTROL_ALLOWED_CAPABILITIES_ENV,
        "",
    )
    capabilities = normalized_string_list(raw.split(","))
    if (
        not capabilities
        or len(capabilities) > 32
        or any(
            not AGENT_CONTROL_CAPABILITY_PATTERN.fullmatch(capability)
            for capability in capabilities
        )
    ):
        raise AgentControlAuthError(
            "agent_control_allowed_capabilities_unconfigured",
            status=503,
        )
    return capabilities


def _configured_agent_control_agent_card_sha256s() -> set[str]:
    values = normalized_string_list(
        os.environ.get(
            FACTORY_AGENT_CONTROL_ALLOWED_AGENT_CARD_SHA256S_ENV,
            "",
        ).split(","),
    )
    if (
        not values
        or len(values) > 64
        or any(
            not AGENT_CONTROL_DIGEST_PATTERN.fullmatch(value)
            for value in values
        )
    ):
        raise AgentControlAuthError(
            "agent_control_agent_card_enrollment_unconfigured",
            status=503,
        )
    return set(values)


def _agent_control_nonce_key(
    *,
    node_id: str,
    agent_id: str,
    nonce: str,
) -> str:
    digest = hashlib.sha256(
        f"{node_id}\0{agent_id}\0{nonce}".encode("utf-8"),
    ).hexdigest()
    return key(f"agent_control_nonce:{digest}")


def authenticate_agent_control_request(
    handler: BaseHTTPRequestHandler,
    *,
    method: str,
    logical_path: str,
    body_bytes: bytes,
    enforce_configured_identity: bool = True,
) -> dict[str, Any]:
    """Verify bearer, signed identity, freshness, body and Redis nonce."""

    if any(
        len(handler.headers.get_all(header_name) or []) != 1
        for header_name in AGENT_CONTROL_AUTH_HEADER_NAMES
    ):
        raise AgentControlAuthError("agent_control_auth_headers_required")
    authorization = str(handler.headers.get("Authorization") or "")
    timestamp = str(handler.headers.get("X-Kolibri-Timestamp") or "")
    nonce = str(handler.headers.get("X-Kolibri-Nonce") or "")
    node_id = str(handler.headers.get("X-Kolibri-Node-Id") or "")
    agent_id = str(handler.headers.get("X-Kolibri-Agent-Id") or "")
    body_sha256 = str(
        handler.headers.get("X-Kolibri-Body-SHA256") or ""
    )
    signature = str(handler.headers.get("X-Kolibri-Signature") or "")

    if (
        not timestamp
        or not nonce
        or not node_id
        or not agent_id
        or not body_sha256
        or not signature
        or len(authorization) > 1024
    ):
        raise AgentControlAuthError("agent_control_auth_headers_required")
    if not AGENT_CONTROL_IDENTITY_PATTERN.fullmatch(node_id):
        raise AgentControlAuthError("agent_control_node_id_invalid")
    if not AGENT_CONTROL_IDENTITY_PATTERN.fullmatch(agent_id):
        raise AgentControlAuthError("agent_control_agent_id_invalid")
    if not AGENT_CONTROL_NONCE_PATTERN.fullmatch(nonce):
        raise AgentControlAuthError("agent_control_nonce_invalid")
    if (
        not timestamp.isascii()
        or not timestamp.isdigit()
        or len(timestamp) > 12
    ):
        raise AgentControlAuthError("agent_control_timestamp_invalid")
    if not AGENT_CONTROL_DIGEST_PATTERN.fullmatch(body_sha256):
        raise AgentControlAuthError("agent_control_body_hash_invalid")
    if not AGENT_CONTROL_DIGEST_PATTERN.fullmatch(signature):
        raise AgentControlAuthError("agent_control_signature_invalid")

    timestamp_value = int(timestamp)
    timestamp_window = _agent_control_timestamp_window()
    if abs(int(time.time()) - timestamp_value) > timestamp_window:
        raise AgentControlAuthError("agent_control_timestamp_expired")

    identity_map = _read_agent_control_identity_map()
    mapped_identity = (
        identity_map.get((node_id, agent_id))
        if identity_map is not None
        else None
    )
    if identity_map is not None:
        # Use a request-specific non-ASCII dummy when the identity is unknown.
        # It keeps the observable failure on the normal bearer/signature path
        # without turning the keyring into an identity enumeration endpoint.
        secret = (
            mapped_identity["secret"]
            if mapped_identity is not None
            else hmac.new(
                b"kolibri-agent-control-unknown-identity",
                f"{node_id}\0{agent_id}".encode("utf-8"),
                hashlib.sha256,
            ).digest()
        )
    else:
        secret = _read_agent_control_secret()

    bearer_prefix = "Bearer "
    provided_token = (
        authorization[len(bearer_prefix):].encode("ascii", "ignore")
        if authorization.startswith(bearer_prefix)
        else b""
    )
    actual_body_sha256 = hashlib.sha256(body_bytes).hexdigest()
    expected_signature = hmac.new(
        secret,
        agent_control_signature_payload(
            method=method,
            logical_path=logical_path,
            timestamp=timestamp,
            nonce=nonce,
            node_id=node_id,
            agent_id=agent_id,
            body_sha256=body_sha256,
        ),
        hashlib.sha256,
    ).hexdigest()
    bearer_ok = hmac.compare_digest(provided_token, secret)
    body_ok = hmac.compare_digest(body_sha256, actual_body_sha256)
    signature_ok = hmac.compare_digest(signature, expected_signature)
    if not bearer_ok:
        raise AgentControlAuthError("agent_control_bearer_invalid")
    if not body_ok:
        raise AgentControlAuthError("agent_control_body_hash_mismatch")
    if not signature_ok:
        raise AgentControlAuthError("agent_control_signature_invalid")

    if identity_map is not None:
        # A successful signature necessarily selected one exact map entry.
        # Keep the assertion explicit for type checkers and future refactors.
        if mapped_identity is None:  # pragma: no cover - bearer already fails
            raise AgentControlAuthError(
                "agent_control_identity_not_allowed",
                status=403,
            )
        allowed_capabilities = mapped_identity["allowed_capabilities"]
    elif enforce_configured_identity:
        allowed_node_id, allowed_agent_id = (
            _configured_agent_control_identity()
        )
        if not hmac.compare_digest(node_id, allowed_node_id):
            raise AgentControlAuthError(
                "agent_control_node_not_allowed",
                status=403,
            )
        if not hmac.compare_digest(agent_id, allowed_agent_id):
            raise AgentControlAuthError(
                "agent_control_agent_not_allowed",
                status=403,
            )
        allowed_capabilities = _configured_agent_control_capabilities()
    else:
        allowed_capabilities = None

    replay_key = _agent_control_nonce_key(
        node_id=node_id,
        agent_id=agent_id,
        nonce=nonce,
    )
    replay_ttl = max(60, timestamp_window * 2)
    try:
        claimed = redis.command(
            "SET",
            replay_key,
            "1",
            "NX",
            "EX",
            replay_ttl,
        )
    except Exception as exc:
        raise AgentControlAuthError(
            "agent_control_nonce_store_unavailable",
            status=503,
        ) from exc
    if claimed not in {"OK", True, 1}:
        raise AgentControlAuthError(
            "agent_control_nonce_replayed",
            status=409,
        )
    identity: dict[str, Any] = {
        "node_id": node_id,
        "agent_id": agent_id,
        "nonce": nonce,
        "timestamp": timestamp,
    }
    if allowed_capabilities is not None:
        identity["allowed_capabilities"] = allowed_capabilities
    return identity


def agent_control_get_requires_auth(path: str) -> bool:
    return path == "/v1/agent-control/auth-check"


def agent_control_signed_headers_present(
    handler: BaseHTTPRequestHandler,
) -> bool:
    """Detect the legacy signed-local transport without claiming all bearer auth."""

    return any(
        handler.headers.get(header_name) is not None
        for header_name in AGENT_CONTROL_AUTH_HEADER_NAMES
        if header_name != "Authorization"
    )


def require_local_mutation_auth() -> bool:
    return (
        os.environ.get("FACTORY_REQUIRE_LOCAL_MUTATION_AUTH", "")
        .strip()
        .lower()
        in {"1", "true", "yes", "on"}
    )


def self_authenticating_local_post(path: str) -> bool:
    """Routes that verify a separate, scoped versioned command credential."""

    if path in {
        "/v1/runtime/product-goal-initializations",
        "/v1/runtime/product-text-runs",
        "/v1/goals/commands",
        "/v1/task-graphs/commands",
    }:
        return True
    parts = path.split("/")
    return (
        len(parts) == 6
        and parts[:3] == ["", "v1", "cases"]
        and parts[5] in {"facts", "assumptions", "decisions"}
    )


def remote_agent_control_logical_path(
    request_target: str,
) -> str | None:
    """Map the dedicated public prefix to its signed internal logical path."""

    parsed = urlparse(request_target)
    if parsed.path == AGENT_CONTROL_REMOTE_PREFIX:
        logical_path = "/"
    elif parsed.path.startswith(f"{AGENT_CONTROL_REMOTE_PREFIX}/"):
        logical_path = parsed.path[len(AGENT_CONTROL_REMOTE_PREFIX):]
    else:
        return None
    if parsed.params:
        logical_path = f"{logical_path};{parsed.params}"
    if parsed.query:
        logical_path = f"{logical_path}?{parsed.query}"
    return logical_path


def remote_agent_control_post_allowed(logical_target: str) -> bool:
    """Deny by default; allow only the signed AgentHost route shapes."""

    parsed = urlparse(logical_target)
    if parsed.params or parsed.query:
        return False
    path = parsed.path
    if path in {
        "/v1/nodes/register",
        "/v1/tasks/lease",
        "/v1/agent-control/agent-cards/register",
    }:
        return True
    parts = path.split("/")
    if (
        len(parts) == 5
        and parts[:3] == ["", "v1", "nodes"]
        and parts[4] == "heartbeat"
    ):
        return bool(AGENT_CONTROL_IDENTITY_PATTERN.fullmatch(parts[3]))
    if (
        len(parts) == 5
        and parts[:3] == ["", "v1", "tasks"]
        and parts[4] in {"heartbeat", "complete", "fail"}
    ):
        return bool(AGENT_CONTROL_IDENTITY_PATTERN.fullmatch(parts[3]))
    return False


def bind_agent_control_identity(
    identity: dict[str, Any] | None,
    body: dict[str, Any],
    *,
    path_node_id: str | None = None,
) -> None:
    if identity is None:
        return
    body_node_id = str(body.get("node_id") or "")
    body_agent_id = str(body.get("agent_id") or "")
    if not body_node_id or not body_agent_id:
        raise AgentControlAuthError(
            "agent_control_body_identity_required",
            status=403,
        )
    if not hmac.compare_digest(identity["node_id"], body_node_id):
        raise AgentControlAuthError(
            "agent_control_node_identity_mismatch",
            status=403,
        )
    if not hmac.compare_digest(identity["agent_id"], body_agent_id):
        raise AgentControlAuthError(
            "agent_control_agent_identity_mismatch",
            status=403,
        )
    if path_node_id is not None and not hmac.compare_digest(
        identity["node_id"],
        str(path_node_id),
    ):
        raise AgentControlAuthError(
            "agent_control_path_node_mismatch",
            status=403,
        )


AGENT_CONTROL_AGENT_CARD_REGISTER_CAPABILITY = (
    "a2a.agent_card.register"
)


def register_agent_control_runtime_card(
    identity: dict[str, Any] | None,
    body: dict[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    """Enroll one pre-authorized provider card for the signed workload."""

    if identity is None:
        raise AgentControlAuthError(
            "agent_control_identity_required",
            status=401,
        )
    if set(body) != {
        "node_id",
        "agent_id",
        "slot_id",
        "agent_card",
    }:
        raise AgentControlAuthError(
            "agent_control_agent_card_request_invalid",
            status=422,
        )
    bind_agent_control_identity(identity, body)
    allowed_capabilities = identity.get("allowed_capabilities")
    if (
        not isinstance(allowed_capabilities, list)
        or AGENT_CONTROL_AGENT_CARD_REGISTER_CAPABILITY
        not in allowed_capabilities
    ):
        raise AgentControlAuthError(
            "agent_control_agent_card_capability_denied",
            status=403,
        )
    slot_id = str(body.get("slot_id") or "")
    if not AGENT_CONTROL_IDENTITY_PATTERN.fullmatch(slot_id):
        raise AgentControlAuthError(
            "agent_control_agent_card_slot_invalid",
            status=422,
        )
    raw_card = body.get("agent_card")
    if not isinstance(raw_card, dict):
        raise AgentControlAuthError(
            "agent_control_agent_card_contract_invalid",
            status=422,
        )
    try:
        card = parse_declared_a2a_agent_card_v1(
            raw_card,
        )
    except DeclaredContractV1Error as exc:
        raise AgentControlAuthError(
            "agent_control_agent_card_contract_invalid",
            status=422,
        ) from exc
    runtime_profile = developer_agent_card_runtime_profile(card)
    required_constraints = {
        "assignment_required",
        "lease_fence_required",
        "provider_execution_authority",
        *execution_claimant_policy_constraints(
            node_id=identity["node_id"],
            agent_id=identity["agent_id"],
            slot_id=slot_id,
        ),
        *(
            {
                developer_runtime_profile_constraint(
                    runtime_profile,
                ),
            }
            if runtime_profile is not None
            else set()
        ),
    }
    card_capabilities = set(card["capabilities"])
    credential_capabilities = set(allowed_capabilities)
    if (
        runtime_profile is None
        or card["tenant_scope"] != "platform"
        or card["agent_kind"] != "worker"
        or card["availability"] != "available"
        or card["limits"]["max_concurrent_assignments"] != 1
        or set(card["policy_constraints"]) != required_constraints
        or not card_capabilities.issubset(credential_capabilities)
    ):
        raise AgentControlAuthError(
            "agent_control_agent_card_binding_invalid",
            status=403,
        )
    card_json = _json_record(card)
    card_sha256 = hashlib.sha256(
        card_json.encode("utf-8"),
    ).hexdigest()
    if card_sha256 not in (
        _configured_agent_control_agent_card_sha256s()
    ):
        raise AgentControlAuthError(
            "agent_control_agent_card_not_enrolled",
            status=403,
        )
    reply = redis.command(
        "EVAL",
        AGENT_CONTROL_RUNTIME_CARD_REGISTER_LUA,
        4,
        a2a_agent_card_key(card["agent_card_id"]),
        a2a_agent_card_ids_key(),
        a2a_agent_cards_by_scope_key(card["tenant_scope"]),
        a2a_runtime_profile_agent_card_key(runtime_profile),
        card_json,
        card["agent_card_id"],
    )
    return str(reply[0]), (
        json.loads(reply[1])
        if len(reply) > 1 and str(reply[1]).startswith("{")
        else None
    )


def constrain_agent_control_capabilities(
    identity: dict[str, Any] | None,
    body: dict[str, Any],
) -> None:
    """Apply the server-owned capability ceiling to every remote claim."""

    if identity is None:
        return
    raw_allowed = identity.get("allowed_capabilities")
    if not isinstance(raw_allowed, list):
        return
    allowed = set(normalized_string_list(raw_allowed))
    body["capabilities"] = sorted(
        allowed.intersection(
            normalized_string_list(body.get("capabilities")),
        )
    )
    raw_slots = body.get("agent_slots")
    if isinstance(raw_slots, list):
        for slot in raw_slots:
            if isinstance(slot, dict):
                slot["capabilities"] = sorted(
                    allowed.intersection(
                        normalized_string_list(slot.get("capabilities")),
                    )
                )
    elif isinstance(raw_slots, dict):
        if "slot_id" in raw_slots:
            raw_slots["capabilities"] = sorted(
                allowed.intersection(
                    normalized_string_list(
                        raw_slots.get("capabilities"),
                    )
                )
            )
        else:
            for slot in raw_slots.values():
                if isinstance(slot, dict):
                    slot["capabilities"] = sorted(
                        allowed.intersection(
                            normalized_string_list(
                                slot.get("capabilities"),
                            )
                        )
                    )


def response(handler: BaseHTTPRequestHandler, status: int, body: Any) -> None:
    payload = json.dumps(body, indent=2, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _sse_error(event_name: str, data: dict[str, Any]) -> bytes:
    payload = json.dumps({"type": event_name, "response": data}, ensure_ascii=False).encode("utf-8")
    return b"data: " + payload + b"\n\n"


def _fake_response_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    response_id = str(payload.get("id") or f"resp_{uuid.uuid4().hex[:12]}")
    text = (
        payload.get("response")
        or payload.get("text")
        or payload.get("output_text")
        or ""
    )
    if isinstance(payload.get("output"), list):
        text_parts = []
        for item in payload["output"]:
            if not isinstance(item, dict):
                continue
            output_text = item.get("content")
            if isinstance(output_text, str):
                text_parts.append(output_text)
            if isinstance(output_text, list):
                text_parts.append("".join(
                    str(segment.get("text", "")) if isinstance(segment, dict) else str(segment)
                    for segment in output_text
                ))
        if text_parts:
            text = "".join(text_parts)
    return {
        "id": response_id,
        "object": "response",
        "status": str(payload.get("status") or "completed"),
        "output_text": str(text),
        "created_at": str(payload.get("created_at") or utc_now()),
        "model": str(payload.get("model") or "mimo-auto"),
    }


def _stream_json_as_sse(
    handler: BaseHTTPRequestHandler,
    status: int,
    payload: dict[str, Any],
    *,
    extra_headers: dict[str, str] | None = None,
) -> None:
    response_payload = _fake_response_from_payload(payload)
    created = _sse_error("response.created", response_payload)
    delta_text = str(response_payload.get("output_text", ""))
    delta = b""
    if delta_text:
        delta = b"data: " + json.dumps({
            "type": "response.output_text.delta",
            "delta": delta_text,
        }, ensure_ascii=False).encode("utf-8") + b"\n\n"
    completed = b"data: " + json.dumps({
        "type": "response.completed",
        "response": response_payload,
    }, ensure_ascii=False).encode("utf-8") + b"\n\n"
    body = created + delta + completed
    handler.send_response(status)
    for header_key, header_value in (extra_headers or {}).items():
        handler.send_header(header_key, header_value)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _parse_proxy_headers(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Content-Length": "0",
    }
    for candidate in ("Authorization", "X-Api-Key", "Cookie", "User-Agent", "Accept", "Origin", "Idempotency-Key", "Accept-Language"):
        value = handler.headers.get(candidate)
        if value is not None:
            headers[candidate] = value
    return headers


def _cookie_from_set_cookie(value: str) -> str | None:
    for segment in value.split(";"):
        cleaned = segment.strip()
        if "=" in cleaned and not cleaned.lower().startswith(("path=", "expires=", "httponly", "samesite", "max-age", "secure")):
            return cleaned
    return None


def _join_cookie_headers(existing: str | None, extra: str | None) -> str | None:
    if not existing:
        return extra
    if not extra:
        return existing
    if extra in existing:
        return existing
    return f"{existing}; {extra}"


def _normalize_headers_for_api(base_url: str, read_headers: dict[str, str], session_cookie: str | None = None) -> tuple[dict[str, str], str | None]:
    headers = dict(read_headers)
    if "Origin" not in headers:
        headers["Origin"] = base_url
    if "Referer" not in headers:
        headers["Referer"] = f"{base_url}/"
    headers["Cookie"] = _join_cookie_headers(headers.get("Cookie"), session_cookie) if session_cookie else headers.get("Cookie", "")
    return headers, headers.get("Cookie")


def _messages_from_input(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    messages = []
    for item in value:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "user")).strip()
        content = item.get("content")
        if role and isinstance(content, str):
            messages.append({"role": role, "content": content})
    return messages


def _normalize_ai_chat_payload(body: dict[str, Any]) -> dict[str, Any]:
    if isinstance(body.get("messages"), list):
        return {"messages": body["messages"]}
    messages = _messages_from_input(body.get("input"))
    if not messages:
        text = ""
        input_field = body.get("input")
        if isinstance(input_field, str):
            text = input_field
        elif isinstance(body.get("text"), str):
            text = body["text"]
        elif isinstance(body.get("prompt"), str):
            text = body["prompt"]
        if text:
            messages = [{"role": "user", "content": text}]
    return {"messages": messages}


def _normalize_responses_payload(body: dict[str, Any]) -> dict[str, Any]:
    if "input" in body and isinstance(body["input"], str) and body["input"]:
        payload = {"input": body["input"]}
        if body.get("model"):
            payload["model"] = body["model"]
        if body.get("stream") is not None:
            payload["stream"] = body["stream"]
        return payload

    if isinstance(body.get("messages"), list):
        text_parts: list[str] = []
        for message in body["messages"]:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            role = str(message.get("role", "user"))
            if role == "user" and isinstance(content, str):
                text_parts.append(content)
        input_text = "\n".join(part for part in text_parts if part)
        if input_text:
            return {"input": input_text}

    for field in ("text", "prompt"):
        text = body.get(field)
        if isinstance(text, str) and text:
            return {"input": text}
    return {"input": ""}


def _bootstrap_api_session(base_url: str, headers: dict[str, str]) -> str | None:
    payload = json.dumps({}, ensure_ascii=False).encode("utf-8")
    bootstrap_headers = dict(headers)
    bootstrap_headers["Content-Type"] = "application/json"
    bootstrap_headers["Content-Length"] = str(len(payload))
    target = base_url + "/api/v1/shell/bootstrap"
    result = MODEL_RUNTIME_ADAPTER.call(
        "POST",
        target,
        payload=payload,
        headers=bootstrap_headers,
        attempts=MODEL_RUNTIME_ACTIVITY_ATTEMPTS,
        retry_statuses={401, 403, 404, 409, 428, 429, 500, 502, 503, 504},
    )
    if result.status < 200 or result.status >= 300:
        return None
    raw_cookie = result.headers.get("set-cookie", "")
    if not raw_cookie:
        return None
    return _cookie_from_set_cookie(raw_cookie)


def _forward_to_model_runtime(handler: BaseHTTPRequestHandler, path: str, body: dict[str, Any]) -> bool:
    candidates = [path]
    if path == "/v1/responses":
        candidates.extend(["/api/v1/responses", "/api/v1/ai/chat", "/api/chat"])
    elif path == "/v1/chat/completions":
        candidates.extend(["/api/v1/responses", "/api/v1/ai/chat", "/api/chat"])

    read_headers = _parse_proxy_headers(handler)
    idempotency_key = read_headers.get("Idempotency-Key") or read_headers.get("idempotency-key")
    route_attempts = 0
    bases_allowed = min(MODEL_RUNTIME_MAX_BASES_TO_TRY, len(MODEL_RUNTIME_BASES))
    attempted_bases = 0
    swap_path_hit = False
    last_swap_candidate = None

    def _send_bounded_block(blocked_reason: str, detail: str, *, endpoint: str = path) -> bool:
        payload_json = json.dumps(
            model_runtime_blocked_envelope(
                body,
                endpoint=endpoint,
                blocked_reason=blocked_reason,
                detail=detail,
            ),
            ensure_ascii=False,
        ).encode("utf-8")
        handler.send_response(503)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(payload_json)))
        handler.end_headers()
        handler.wfile.write(payload_json)
        return True

    for base in MODEL_RUNTIME_BASES[:bases_allowed]:
        attempted_bases += 1
        for candidate in candidates:
            if candidate in {"/api/v1/ai/chat", "/api/chat"}:
                candidate_payload = _normalize_ai_chat_payload(body)
            elif candidate == "/api/v1/responses":
                candidate_payload = _normalize_responses_payload(body)
            else:
                candidate_payload = body
            send_payload = json.dumps(candidate_payload, ensure_ascii=False).encode("utf-8")
            base_session_headers = dict(read_headers)
            session_cookie: str | None = None
            if candidate.startswith("/api/"):
                session_cookie = _bootstrap_api_session(base, base_session_headers)
                base_session_headers, session_cookie = _normalize_headers_for_api(base, base_session_headers, session_cookie=session_cookie)
            refresh_cookie_used = False

            heartbeat_state = {"last_signal_ts": 0.0}

            def _heartbeat(attempt_activity_id: str, attempt: int) -> None:
                if MODEL_RUNTIME_ACTIVITY_HEARTBEAT_SECONDS <= 0:
                    return
                now = time.time()
                last_signal = heartbeat_state["last_signal_ts"]
                if now - last_signal < MODEL_RUNTIME_ACTIVITY_HEARTBEAT_SECONDS:
                    return
                heartbeat_state["last_signal_ts"] = now
                _ = attempt_activity_id
                _ = attempt

            route_headers = {
                "X-Kolibri-Model-Runtime-Base": base,
                "X-Kolibri-Model-Runtime-Route": candidate,
                "X-Kolibri-Model-Runtime-Attempts": "",
            }

            while True:
                if route_attempts >= MODEL_RUNTIME_MAX_ROUTE_ATTEMPTS:
                    return _send_bounded_block(
                        "model_runtime_budget_exhausted",
                        f"model runtime route attempts exhausted ({route_attempts}/{MODEL_RUNTIME_MAX_ROUTE_ATTEMPTS})",
                    )
                route_attempts += 1
                route_headers["X-Kolibri-Model-Runtime-Attempts"] = str(route_attempts)
                send_headers, _ = _normalize_headers_for_api(base, base_session_headers, session_cookie=session_cookie)
                send_headers["Content-Length"] = str(len(send_payload))
                target = base + candidate
                adapter_activity = MODEL_RUNTIME_ADAPTER.call(
                    "POST",
                    target,
                    payload=send_payload,
                    headers=send_headers,
                    attempts=MODEL_RUNTIME_ACTIVITY_ATTEMPTS,
                    heartbeat_fn=_heartbeat,
                    idempotency_key=(
                        f"{idempotency_key}:{target}"
                        if idempotency_key
                        else None
                    ),
                    retry_statuses=MODEL_RUNTIME_RETRY_STATUS | {405},
                )
                status = adapter_activity.status
                upstream_data = adapter_activity.body
                upstream_headers = dict(adapter_activity.headers)
                content_type = str(
                    upstream_headers.get("content-type", upstream_headers.get("Content-Type", "")),
                ).split(";", 1)[0].strip().lower()
                route_headers["X-Kolibri-Model-Runtime-Attempts"] = str(route_attempts)

                if status >= 200 and status < 300:
                    if content_type == "text/event-stream":
                        handler.send_response(status)
                        for header_key, header_value in route_headers.items():
                            handler.send_header(header_key, header_value)
                        for header_key, header_value in upstream_headers.items():
                            if str(header_key).lower() in {"connection", "transfer-encoding"}:
                                continue
                            if str(header_key).lower() == "content-type":
                                continue
                            handler.send_header(header_key, header_value)
                        handler.send_header("Content-Type", "text/event-stream")
                        handler.send_header("Cache-Control", "no-cache")
                        handler.send_header("Content-Length", str(len(upstream_data)))
                        handler.end_headers()
                        handler.wfile.write(upstream_data)
                        return True

                    if path == "/v1/responses" and "application/json" in content_type:
                        try:
                            json_payload = json.loads(upstream_data.decode("utf-8"))
                            if isinstance(json_payload, dict):
                                _stream_json_as_sse(
                                    handler,
                                    status,
                                    json_payload,
                                    extra_headers=route_headers,
                                )
                                return True
                        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                            pass

                    handler.send_response(status)
                    handler.send_header("X-Kolibri-Model-Runtime-Base", base)
                    handler.send_header("X-Kolibri-Model-Runtime-Route", candidate)
                    handler.send_header("X-Kolibri-Model-Runtime-Attempts", str(route_attempts))
                    handler.send_header("Content-Type", content_type or "application/json")
                    handler.send_header("Content-Length", str(len(upstream_data)))
                    handler.end_headers()
                    handler.wfile.write(upstream_data)
                    return True

                if status in {401, 403, 428, 429} and candidate.startswith("/api/") and not refresh_cookie_used:
                    refreshed_cookie = _bootstrap_api_session(base, send_headers)
                    if refreshed_cookie:
                        session_cookie = refreshed_cookie
                        refresh_cookie_used = True
                        continue
                    error_payload = _read_http_error_payload(
                        adapter_activity.last_error_code if adapter_activity.last_error is not None else HTTPError("bootstrap-refresh", status),
                    )
                    handler.send_response(status)
                    for header_key, header_value in route_headers.items():
                        handler.send_header(header_key, header_value)
                    handler.send_header("Content-Type", "application/json")
                    handler.send_header("Content-Length", str(len(error_payload)))
                    handler.end_headers()
                    handler.wfile.write(error_payload)
                    return True

                if candidate in {"/api/v1/ai/chat", "/api/chat", "/api/v1/responses"} and status == 405:
                    break

                if status in MODEL_RUNTIME_PROVIDER_SWAP_STATUS:
                    swap_path_hit = True
                    last_swap_candidate = candidate
                    break

                error_payload = _read_http_error_payload(
                    HTTPError(
                        target,
                        status,
                        adapter_activity.last_error or "upstream_error",
                        {},
                        upstream_data,
                    ),
                )
                handler.send_response(status)
                for header_key, header_value in route_headers.items():
                    handler.send_header(header_key, header_value)
                handler.send_header("Content-Type", "application/json")
                handler.send_header("Content-Length", str(len(error_payload)))
                handler.end_headers()
                handler.wfile.write(error_payload)
                return True
    if swap_path_hit and attempted_bases > 0:
        return _send_bounded_block(
            "provider_swap_limit_reached",
            f"no viable model runtime route after {route_attempts} attempts across {attempted_bases} base(s)",
            endpoint=last_swap_candidate or path,
        )
    return False


def _read_http_error_payload(exc: HTTPError) -> bytes:
    try:
        raw = exc.read()
        if raw:
            return raw
    except Exception:
        pass
    return json.dumps({
        "status": getattr(exc, "code", 502),
        "error": "model_backend_unavailable",
        "detail": str(exc),
    }, ensure_ascii=False).encode("utf-8")


def read_raw_body(
    handler: BaseHTTPRequestHandler,
    *,
    max_bytes: int = MAX_REQUEST_BODY_BYTES,
) -> bytes:
    cached = getattr(handler, "_kolibri_raw_request_body", None)
    if isinstance(cached, bytes):
        return cached
    transfer_encoding = str(
        handler.headers.get("Transfer-Encoding") or "",
    ).strip()
    if transfer_encoding and transfer_encoding.lower() != "identity":
        raise RequestBodyError(
            "request_transfer_encoding_unsupported",
            status=400,
        )
    content_length = handler.headers.get("Content-Length")
    if content_length is None or content_length == "":
        length = 0
    else:
        try:
            length = int(content_length, 10)
        except (TypeError, ValueError) as exc:
            raise RequestBodyError(
                "request_content_length_invalid",
                status=400,
            ) from exc
    if length < 0:
        raise RequestBodyError(
            "request_content_length_invalid",
            status=400,
        )
    if length > max_bytes:
        raise RequestBodyError(
            "request_body_too_large",
            status=413,
        )
    if not length:
        raw = b""
    else:
        connection = getattr(handler, "connection", None)
        previous_timeout = (
            connection.gettimeout()
            if connection is not None
            else None
        )
        try:
            if connection is not None:
                connection.settimeout(REQUEST_BODY_TIMEOUT_SECONDS)
            raw = handler.rfile.read(length)
        except (TimeoutError, socket.timeout) as exc:
            raise RequestBodyError(
                "request_body_timeout",
                status=408,
            ) from exc
        finally:
            if connection is not None:
                connection.settimeout(previous_timeout)
        if len(raw) != length:
            raise RequestBodyError(
                "request_body_incomplete",
                status=400,
            )
    setattr(handler, "_kolibri_raw_request_body", raw)
    return raw


def read_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    raw = read_raw_body(handler)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def goal_identity_signature(
    secret: str,
    *,
    message_id: str,
    tenant_id: str,
    user_id: str | None,
    actor_id: str,
    actor_type: str,
) -> str:
    claims = {
        "message_id": message_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "actor": {
            "actor_id": actor_id,
            "actor_type": actor_type,
        },
    }
    digest = hmac.new(
        secret.encode("utf-8"),
        json.dumps(
            claims,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256:{digest}"


def _factory_env_or_credential(name: str) -> str:
    """Read one server-owned setting without following unsafe credential paths."""

    direct = os.environ.get(name, "").strip()
    credential_path = os.environ.get(f"{name}_FILE", "").strip()
    if direct and credential_path:
        return ""
    if direct:
        return direct
    if not credential_path or not os.path.isabs(credential_path):
        return ""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(credential_path, flags)
    except OSError:
        return ""
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in {0, os.geteuid()}
            or metadata.st_mode & 0o077
            or metadata.st_size < 1
            or metadata.st_size > 8192
        ):
            return ""
        raw = os.read(descriptor, 8193)
        if len(raw) > 8192:
            return ""
        try:
            return raw.decode("utf-8", "strict").strip()
        except UnicodeDecodeError:
            return ""
    finally:
        os.close(descriptor)


def _factory_configured_value(
    name: str,
    *,
    config_prefix: str | None = None,
) -> str:
    if config_prefix is not None:
        candidates = [f"{config_prefix}_{name}"]
        aliases = {
            "AUTHORITY_EPOCH": "EPOCH",
            "AUTHORITY_PLACEMENT_ID": "PLACEMENT_ID",
            "AUTHORITY_CAPABILITIES": "CAPABILITIES",
        }
        if name in aliases:
            candidates.append(f"{config_prefix}_{aliases[name]}")
        for candidate in candidates:
            value = _factory_env_or_credential(candidate)
            if value:
                return value
        return ""
    return _factory_env_or_credential(
        f"FACTORY_CONTROL_{name}",
    ) or _factory_env_or_credential(f"FACTORY_GOAL_{name}")


def logical_home_server_authority_grant() -> dict[str, Any]:
    """Return only Home authority metadata; never tokens or HMAC material."""

    epoch_text = _factory_configured_value("AUTHORITY_EPOCH")
    try:
        authority_epoch = int(epoch_text)
    except (TypeError, ValueError):
        authority_epoch = 0
    return {
        "authority_id": _factory_configured_value("AUTHORITY_ID"),
        "authority_role": "logical_home_control_plane",
        "authority_epoch": authority_epoch,
        "authority_placement_id": _factory_configured_value(
            "AUTHORITY_PLACEMENT_ID",
        ),
        "authorization_decision_id": _factory_configured_value(
            "AUTHORIZATION_DECISION_ID",
        ),
        "capabilities": normalized_string_list(
            _factory_configured_value(
                "AUTHORITY_CAPABILITIES",
            ).split(","),
        ),
    }


def logical_home_command_transport_context(
    handler: BaseHTTPRequestHandler,
    command: dict[str, Any],
    *,
    error_type: (
        type[GoalCommandError]
        | type[TaskGraphCommandError]
        | type[ProductTextRunControlError]
        | type[ProductGoalInitializeControlError]
        | type[A2AMutationControlError]
    ),
    error_prefix: str,
    config_prefix: str | None = None,
    authority_role: str = "logical_home_control_plane",
) -> dict[str, Any]:
    """Authenticate the trusted gateway and reconstruct its authority grant.

    Tenant/user/actor are assertions made by the authenticated internal
    gateway. Authority identity, epoch, placement, decision and capabilities
    come only from server configuration and can never be advanced by a request.
    """

    def configured(name: str) -> str:
        return _factory_configured_value(
            name,
            config_prefix=config_prefix,
        )

    token = configured("COMMAND_TOKEN")
    identity_hmac_key = configured("IDENTITY_HMAC_KEY")
    authority_id = configured("AUTHORITY_ID")
    placement_id = configured("AUTHORITY_PLACEMENT_ID")
    decision_id = configured(
        "AUTHORIZATION_DECISION_ID",
    )
    epoch_text = configured("AUTHORITY_EPOCH")
    capabilities = normalized_string_list(
        configured("AUTHORITY_CAPABILITIES").split(","),
    )
    if not all((
        token,
        identity_hmac_key,
        authority_id,
        placement_id,
        decision_id,
        epoch_text,
        capabilities,
    )):
        raise error_type(503, f"{error_prefix}_auth_not_configured")
    try:
        authority_epoch = int(epoch_text)
    except ValueError as exc:
        raise error_type(
            503,
            f"{error_prefix}_auth_not_configured",
        ) from exc
    if authority_epoch < 1:
        raise error_type(503, f"{error_prefix}_auth_not_configured")

    authorization = handler.headers.get("Authorization", "")
    scheme, _, supplied_token = authorization.partition(" ")
    if (
        scheme.lower() != "bearer"
        or not supplied_token
        or not hmac.compare_digest(supplied_token, token)
    ):
        raise error_type(401, f"{error_prefix}_unauthorized")

    tenant_id = handler.headers.get("X-Kolibri-Tenant-Id", "").strip()
    actor_id = handler.headers.get("X-Kolibri-Actor-Id", "").strip()
    actor_type = handler.headers.get("X-Kolibri-Actor-Type", "").strip()
    user_header = handler.headers.get("X-Kolibri-User-Id")
    user_id = user_header.strip() if user_header and user_header.strip() else None
    if not tenant_id or not actor_id or actor_type not in {
        "user",
        "service",
        "agent",
        "system",
    }:
        raise error_type(401, f"{error_prefix}_identity_required")
    expected_signature = goal_identity_signature(
        identity_hmac_key,
        message_id=str(command.get("message_id") or ""),
        tenant_id=tenant_id,
        user_id=user_id,
        actor_id=actor_id,
        actor_type=actor_type,
    )
    supplied_signature = handler.headers.get(
        "X-Kolibri-Identity-Signature",
        "",
    )
    if (
        not supplied_signature
        or not hmac.compare_digest(supplied_signature, expected_signature)
    ):
        raise error_type(
            401,
            f"{error_prefix}_identity_signature_invalid",
        )
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "actor": {
            "actor_id": actor_id,
            "actor_type": actor_type,
        },
        "authority": {
            "authority_id": authority_id,
            "authority_role": authority_role,
            "authority_epoch": authority_epoch,
            "authority_placement_id": placement_id,
            "authorization_decision_id": decision_id,
            "capabilities": capabilities,
        },
    }


def logical_home_a2a_mutation_message_id(
    action: str,
    payload: dict[str, Any],
) -> str:
    canonical = json.dumps(
        {
            "action": action,
            "payload": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"evt_{hashlib.sha256(canonical).hexdigest()}"


def logical_home_a2a_mutation_transport_context(
    handler: BaseHTTPRequestHandler,
    payload: dict[str, Any],
    *,
    action: str,
    required_capability: str,
) -> dict[str, Any]:
    transport_message_id = logical_home_a2a_mutation_message_id(
        action,
        payload,
    )
    context = logical_home_command_transport_context(
        handler,
        {"message_id": transport_message_id},
        error_type=A2AMutationControlError,
        error_prefix="a2a_mutation",
    )
    capabilities = set(
        normalized_string_list(
            (context.get("authority") or {}).get("capabilities"),
        ),
    )
    if required_capability not in capabilities:
        raise A2AMutationControlError(
            403,
            "a2a_mutation_capability_denied",
            [{
                "path": "/identity/authority/capabilities",
                "code": f"{required_capability}_required",
            }],
        )
    context["transport_message_id"] = transport_message_id
    return context


def _a2a_mutation_binding_error(
    path: str,
    code: str,
) -> A2AMutationControlError:
    return A2AMutationControlError(
        403,
        "a2a_mutation_identity_binding_failed",
        [{"path": path, "code": code}],
    )


def _require_logical_home_system_actor(
    context: dict[str, Any],
) -> None:
    actor = context.get("actor") or {}
    if (
        context.get("user_id") is not None
        or actor.get("actor_type") != "system"
    ):
        raise _a2a_mutation_binding_error(
            "/transport/actor",
            "logical_home_system_actor_required",
        )


def bind_a2a_event_transport(
    event: dict[str, Any],
    message: dict[str, Any],
    context: dict[str, Any],
) -> None:
    identity = event.get("identity") or {}
    actor = identity.get("actor") or {}
    authority = identity.get("authority") or {}
    transport_actor = context.get("actor") or {}
    transport_authority = context.get("authority") or {}
    exact_bindings = (
        (
            "/identity/tenant_id",
            identity.get("tenant_id"),
            context.get("tenant_id"),
        ),
        (
            "/identity/user_id",
            identity.get("user_id"),
            context.get("user_id"),
        ),
        (
            "/identity/actor/actor_id",
            actor.get("actor_id"),
            transport_actor.get("actor_id"),
        ),
        (
            "/identity/actor/actor_type",
            actor.get("actor_type"),
            transport_actor.get("actor_type"),
        ),
        (
            "/payload/tenant_id",
            message.get("tenant_id"),
            context.get("tenant_id"),
        ),
        (
            "/payload/sender_actor_id",
            message.get("sender_actor_id"),
            transport_actor.get("actor_id"),
        ),
    )
    for path, declared, authenticated in exact_bindings:
        if declared != authenticated:
            raise _a2a_mutation_binding_error(
                path,
                "authenticated_claimant_mismatch",
            )
    authority_bindings = (
        "authority_id",
        "authority_role",
        "authority_epoch",
        "authority_placement_id",
        "authorization_decision_id",
    )
    for field in authority_bindings:
        if authority.get(field) != transport_authority.get(field):
            raise _a2a_mutation_binding_error(
                f"/identity/authority/{field}",
                "logical_home_authority_mismatch",
            )
    declared_capabilities = set(
        normalized_string_list(authority.get("capabilities")),
    )
    transport_capabilities = set(
        normalized_string_list(
            transport_authority.get("capabilities"),
        ),
    )
    if not declared_capabilities.issubset(transport_capabilities):
        raise _a2a_mutation_binding_error(
            "/identity/authority/capabilities",
            "authority_capability_escalation",
        )


def bind_a2a_agent_card_transport(
    card: dict[str, Any],
    context: dict[str, Any],
) -> None:
    _require_logical_home_system_actor(context)
    tenant_scope = str(card.get("tenant_scope") or "")
    if (
        tenant_scope != "platform"
        and tenant_scope != str(context.get("tenant_id") or "")
    ):
        raise _a2a_mutation_binding_error(
            "/tenant_scope",
            "authenticated_tenant_mismatch",
        )


def bind_assignment_transport(
    assignment: dict[str, Any],
    context: dict[str, Any],
    *,
    require_available_card: bool,
) -> None:
    _require_logical_home_system_actor(context)
    if (
        require_available_card
        and assignment.get("status") != "pending"
    ):
        raise _a2a_mutation_binding_error(
            "/status",
            "assignment_must_start_pending",
        )
    if assignment.get("tenant_id") != context.get("tenant_id"):
        raise _a2a_mutation_binding_error(
            "/tenant_id",
            "authenticated_tenant_mismatch",
        )
    profile = assignment.get("authority_profile") or {}
    transport_authority = context.get("authority") or {}
    if require_available_card:
        for field in (
            "authority_id",
            "authority_role",
            "authority_epoch",
            "authorization_decision_id",
        ):
            if profile.get(field) == transport_authority.get(field):
                continue
            raise _a2a_mutation_binding_error(
                f"/authority_profile/{field}",
                "logical_home_authority_mismatch",
            )
    if require_available_card and not set(
        normalized_string_list(profile.get("capabilities")),
    ).issubset(
        set(
            normalized_string_list(
                transport_authority.get("capabilities"),
            ),
        ),
    ):
        raise _a2a_mutation_binding_error(
            "/authority_profile/capabilities",
            "authority_capability_escalation",
        )
    if require_available_card:
        card = load_a2a_agent_card(
            str(assignment.get("agent_card_id") or ""),
        )
        if card is None:
            raise _a2a_mutation_binding_error(
                "/agent_card_id",
                "agent_card_not_registered",
            )
        if int(card.get("version") or 0) != int(
            assignment.get("agent_card_version") or 0,
        ):
            raise _a2a_mutation_binding_error(
                "/agent_card_version",
                "agent_card_version_mismatch",
            )
        if card.get("tenant_scope") not in {
            "platform",
            assignment.get("tenant_id"),
        }:
            raise _a2a_mutation_binding_error(
                "/agent_card_id",
                "agent_card_tenant_scope_mismatch",
            )
        if card.get("availability") != "available":
            raise _a2a_mutation_binding_error(
                "/agent_card_id",
                "agent_card_unavailable",
            )


def goal_command_transport_context(
    handler: BaseHTTPRequestHandler,
    command: dict[str, Any],
) -> dict[str, Any]:
    return logical_home_command_transport_context(
        handler,
        command,
        error_type=GoalCommandError,
        error_prefix="goal_command",
    )


def product_text_run_command_transport_context(
    handler: BaseHTTPRequestHandler,
    command: dict[str, Any],
) -> dict[str, Any]:
    return logical_home_command_transport_context(
        handler,
        command,
        error_type=ProductTextRunControlError,
        error_prefix="product_text_run_command",
        config_prefix="FACTORY_PRODUCT",
        authority_role="product_data_authority",
    )


def product_goal_initialize_command_transport_context(
    handler: BaseHTTPRequestHandler,
    command: dict[str, Any],
) -> dict[str, Any]:
    return logical_home_command_transport_context(
        handler,
        command,
        error_type=ProductGoalInitializeControlError,
        error_prefix="product_goal_initialize_command",
        config_prefix="FACTORY_PRODUCT",
        authority_role="product_data_authority",
    )


def task_graph_command_transport_context(
    handler: BaseHTTPRequestHandler,
    command: dict[str, Any],
) -> dict[str, Any]:
    return logical_home_command_transport_context(
        handler,
        command,
        error_type=TaskGraphCommandError,
        error_prefix="task_graph_command",
    )


def project_case_command_transport_context(
    handler: BaseHTTPRequestHandler,
    command: dict[str, Any],
) -> dict[str, Any]:
    return logical_home_command_transport_context(
        handler,
        command,
        error_type=ProjectCaseControlError,
        error_prefix="project_case_command",
    )


def parse_owner_ids(value: str) -> set[int]:
    ids = set()
    for item in value.replace(";", ",").split(","):
        item = item.strip()
        if item:
            ids.add(int(item))
    return ids


def validate_miniapp(handler: BaseHTTPRequestHandler, body: dict[str, Any] | None = None) -> dict[str, Any]:
    init_data = handler.headers.get("X-Telegram-Init-Data") or (body or {}).get("init_data") or ""
    return validate_telegram_init_data(
        init_data,
        os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        parse_owner_ids(os.environ.get("TELEGRAM_OWNER_IDS", "")),
        parse_owner_ids(os.environ.get("TELEGRAM_ADMIN_IDS", "")),
        int(os.environ.get("TELEGRAM_INIT_DATA_MAX_AGE", "86400")),
    )


def superfactory_status() -> dict[str, Any]:
    nodes = []
    for node_id in sorted(redis.command("SMEMBERS", key("node_ids")) or []):
        node = get_json(node_key(node_id), {})
        node["draining"] = bool(redis.command("GET", drain_key(node_id)))
        nodes.append(node)
    tasks = [task for task in (load_task(task_id) for task_id in all_task_ids()) if task]
    counts: dict[str, int] = {}
    for task in tasks:
        state = str(task.get("state") or "unknown")
        counts[state] = counts.get(state, 0) + 1
    receiver = plan_update_receiver(webhook_info={"url": os.environ.get("TELEGRAM_WEBHOOK_URL", "")})
    return {
        "status": "ok",
        "receiver": {
            "mode": receiver.mode,
            "should_poll": receiver.should_poll,
            "webhook_configured": bool(receiver.webhook_url),
            "conflict": receiver.conflict,
        },
        "runner_policy": runner_policy(),
        "nodes": nodes,
        "task_counts": counts,
        "queue": queue_ids(),
    }


def miniapp_task_envelope(body: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
    text = str(body.get("objective") or body.get("message") or "").strip()
    if not text:
        raise ValueError("objective is required")
    runner = select_runner(str(body.get("kind") or "owner_remote_task"), body.get("runner"))
    task_id = body.get("task_id") or f"TGAPP-{uuid.uuid4().hex[:12]}"
    return {
        "task_id": task_id,
        "idempotency_key": body.get("idempotency_key") or f"telegram-miniapp:{auth['user']['id']}:{task_id}",
        "kind": body.get("kind") or "owner_remote_task",
        "required_capability": body.get("required_capability") or "generic_implementation",
        "objective": text,
        "runner": runner["runner"],
        "runner_policy": runner,
        "source": {
            "kind": "telegram_miniapp",
            "user_id": auth["user"]["id"],
            "role": auth["role"],
            "accepted_at": utc_now(),
        },
        "max_retries": int(body.get("max_retries", 1)),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "KolibriFactoryControl/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s %s\n" % (utc_now(), fmt % args))

    def do_GET(self) -> None:  # noqa: N802
        try:
            if remote_agent_control_logical_path(self.path) is not None:
                raise AgentControlAuthError(
                    "agent_control_remote_route_forbidden",
                    status=403,
                )
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            self._agent_control_identity = None
            if path in {"/health", "/v1/health"}:
                pong = redis.command("PING")
                response(self, 200, canonical_response_envelope(
                    status="completed",
                    node="home",
                    route_used="/v1/health",
                    data={"redis": pong, "queue_backend": "redis", "time": utc_now(), "fabric_api_version": FABRIC_API_VERSION, "truth_factory": "enabled"},
                    next_action="use /v1/fleet/route before dispatching work to a node",
                ))
                return
            if agent_control_get_requires_auth(path):
                self._agent_control_identity = (
                    authenticate_agent_control_request(
                        self,
                        method="GET",
                        logical_path=self.path,
                        body_bytes=b"",
                    )
                )
            elif require_local_mutation_auth():
                if not agent_control_signed_headers_present(self):
                    raise AgentControlAuthError(
                        "agent_control_auth_headers_required",
                    )
                self._agent_control_identity = (
                    authenticate_agent_control_request(
                        self,
                        method="GET",
                        logical_path=self.path,
                        body_bytes=b"",
                        enforce_configured_identity=False,
                    )
                )
            if path == "/v1/agent-control/auth-check":
                identity = self._agent_control_identity
                response(self, 200, {
                    "status": "ok",
                    "authenticated": True,
                    "node_id": identity["node_id"],
                    "agent_id": identity["agent_id"],
                    "authenticated_at": utc_now(),
                })
                return
            if path == "/v1/truth/summary":
                response(self, 200, get_truth_summary())
                return
            if path == "/v1/truth/claims":
                query = parse_qs(parsed.query)
                task_id = query.get("task_id", [None])[0]
                if task_id:
                    response(self, 200, {"claims": get_claims_for_task(task_id)})
                else:
                    response(self, 200, {"claims": [asdict(c) for c in _truth_claims.values()]})
                return
            if path == "/v1/truth/contradictions":
                contradictions = [asdict(c) for c in _truth_claims.values() if c.status == "challenged"]
                response(self, 200, {"contradictions": contradictions, "count": len(contradictions)})
                return
            if path == "/v1/disputes":
                query = parse_qs(parsed.query)
                tenant_id = (query.get("tenant_id", [""])[0] or "").strip()
                scope = (query.get("scope", [""])[0] or "").strip()
                disputes = list_disputes(
                    tenant_id if tenant_id else None,
                    scope if scope else None,
                )
                response(self, 200, {
                    "disputes": disputes,
                    "count": len(disputes),
                    "scope_filter": scope or None,
                })
                return
            if path.startswith("/v1/disputes/"):
                parts = path.split("/")
                if len(parts) != 4:
                    response(self, 404, {"error": "dispute_route_not_supported"})
                    return
                dispute_id = parts[3]
                dispute = load_dispute(dispute_id)
                if not dispute:
                    response(self, 404, {"error": "dispute_not_found", "dispute_id": dispute_id})
                    return
                response(self, 200, asdict(dispute))
                return
            if path == "/v1/superfactory/status":
                auth = validate_miniapp(self)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                response(self, 200, superfactory_status())
                return
            if path == "/v1/nodes":
                query = parse_qs(parsed.query)
                limit = min(max(int(query.get("limit", ["50"])[0]), 1), 250)
                offset = max(int(query.get("offset", ["0"])[0]), 0)
                nodes = []
                current = now_ts()
                node_ids = sorted(redis.command("SMEMBERS", key("node_ids")) or [])
                total_indexed = len(node_ids)
                page_ids = node_ids[offset:offset + limit]
                page_nodes = get_json_many([node_key(node_id) for node_id in page_ids])
                drains = redis.command("MGET", *[drain_key(node_id) for node_id in page_ids]) if page_ids else []
                for node_id, raw_node, draining in zip(page_ids, page_nodes, drains):
                    node = raw_node or {"node_id": node_id}
                    node["draining"] = bool(draining)
                    node = refresh_node_effective_state(node, current)
                    nodes.append(classify_node_freshness(node, current))
                counts = node_health_counts(nodes)
                response(self, 200, {
                    "nodes": nodes,
                    "counts": counts,
                    "freshness": counts,
                    "pagination": {"limit": limit, "offset": offset, "returned": len(nodes), "total_indexed": total_indexed},
                })
                return
            if path.startswith("/v1/nodes/"):
                node_id = path.split("/", 3)[3]
                node = get_json(node_key(node_id), {})
                if not node:
                    response(self, 404, {"error": "node_not_found", "node_id": node_id})
                    return
                node["draining"] = bool(redis.command("GET", drain_key(node_id)))
                response(self, 200, classify_node_freshness(refresh_node_effective_state(node)))
                return
            if path == "/v1/fleet/nodes":
                nodes = fabric_nodes(registered_nodes())
                response(self, 200, canonical_response_envelope(
                    status="completed",
                    route_used="/v1/fleet/nodes",
                    data={"nodes": nodes},
                    next_action="select a target node or ask /v1/fleet/route for a safe route",
                ))
                return
            if path == "/v1/fleet/topology":
                nodes = fabric_nodes(registered_nodes())
                response(self, 200, canonical_response_envelope(
                    status="completed",
                    route_used="/v1/fleet/topology",
                    data=fleet_topology(nodes),
                    next_action="use the protected_fabric_api edge or relay endpoint for execution",
                ))
                return
            if path == "/v1/fleet/route":
                query = parse_qs(parsed.query)
                route = fabric_route(
                    target_node=query.get("target_node", [None])[0],
                    required_capability=query.get("required_capability", [None])[0],
                    registered_nodes=registered_nodes(),
                )
                status = "completed" if route.get("status") == "ok" else "blocked"
                response(self, 200 if status == "completed" else 503, canonical_response_envelope(
                    status=status,
                    node=route.get("route", {}).get("target_node") or route.get("target_node") or "home",
                    route_used="/v1/fleet/route",
                    fallback_nodes=route.get("fallback_nodes", []),
                    blocked_reason=route.get("reason", ""),
                    repair_task=route.get("repair_task", ""),
                    data=route,
                    next_action="dispatch via /v1/agents/tasks" if status == "completed" else "choose a fallback node or run the repair task",
                ))
                return
            if path == "/v1/fleet/capabilities":
                nodes = fabric_nodes(registered_nodes())
                response(self, 200, canonical_response_envelope(
                    status="completed",
                    route_used="/v1/fleet/capabilities",
                    data=fleet_capabilities(nodes),
                    next_action="include required_capability in /v1/agents/tasks when dispatching work",
                ))
                return
            if path == "/v1/fabric/manifest":
                response(self, 200, fabric_manifest_payload(fabric_nodes(registered_nodes())))
                return
            if path == "/v1/os/capabilities":
                response(self, 200, os_capabilities_envelope())
                return
            if path == "/v1/models":
                response(self, 200, canonical_response_envelope(
                    status="completed",
                    route_used="/v1/models",
                    data={"object": "list", "data": MODEL_CATALOG},
                    next_action="model generation endpoints remain safe stubs until authenticated model routes are online",
                ))
                return
            if path == "/v1/admin/agent-host-binary":
                binary_path = Path(os.environ.get(
                    "KOLIBRI_AGENT_HOST_BINARY",
                    "/usr/local/bin/kolibri-agent-host",
                ))
                if not binary_path.exists():
                    response(self, 404, {"error": "binary_not_found"})
                    return
                data = binary_path.read_bytes()
                import hashlib as _hl
                sha256 = _hl.sha256(data).hexdigest()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("X-Binary-SHA256", sha256)
                self.send_header("X-Binary-Size", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            if path == "/v1/fabric/health":
                pong = redis.command("PING")
                response(self, 200, {
                    "status": "ok",
                    "fabric_api_version": FABRIC_API_VERSION,
                    "primary_management_path": "protected_fabric_api",
                    "ssh_policy": "emergency_bootstrap_diagnostic_only",
                    "redis": pong,
                    "time": utc_now(),
                })
                return
            if path == "/v1/fabric/policy":
                response(self, 200, {
                    "primary_management_path": "protected_fabric_api",
                    "ssh_policy": "emergency_bootstrap_diagnostic_only",
                    "owner_rights": OWNER_RIGHTS_POLICY,
                    "node_identity": NODE_IDENTITY_ROTATION_POLICY,
                    "bootstrap": BOOTSTRAP_CONTRACT,
                })
                return
            if path.startswith("/v1/policy/audit/"):
                parts = path.split("/")
                if len(parts) != 5 or not parts[4]:
                    response(self, 400, {"error": "policy_audit_tenant_required"})
                    return
                tenant_id = parts[4]
                response(self, 200, {
                    "tenant_id": tenant_id,
                    "decisions": policy_decision_service().load_audit_log(tenant_id),
                })
                return
            if path == "/v1/fabric/routes":
                response(self, 200, {
                    "status": "ok",
                    "primary_management_path": "protected_fabric_api",
                    "nodes": fabric_nodes(registered_nodes()),
                    "relay_endpoint": "/v1/fabric/relay",
                })
                return
            if path == "/v1/fabric/keys/rotation":
                response(self, 200, NODE_IDENTITY_ROTATION_POLICY)
                return
            if path == "/v1/goals":
                response(self, 404, {
                    "error": "goal_query_requires_tenant_and_goal_id",
                })
                return
            if path == "/v1/a2a/agent-cards":
                query = parse_qs(parsed.query)
                scope = (query.get("scope", [""])[0] or "").strip()
                card_ids = (
                    a2a_agent_cards_by_scope(scope)
                    if scope
                    else a2a_agent_card_ids()
                )
                agent_cards = [
                    card
                    for card in (load_a2a_agent_card(card_id) for card_id in card_ids)
                    if card is not None
                ]
                response(self, 200, {
                    "agent_cards": agent_cards,
                    "scope": scope or "all",
                })
                return
            if path.startswith("/v1/a2a/agent-cards/"):
                parts = path.split("/")
                if len(parts) != 5:
                    response(self, 404, {"error": "a2a_route_not_supported"})
                    return
                card_id = parts[4]
                card = load_a2a_agent_card(card_id)
                if not card:
                    response(self, 404, {"error": "a2a_agent_card_not_found", "agent_card_id": card_id})
                    return
                response(self, 200, card)
                return
            if path.startswith("/v1/a2a/messages/"):
                parts = path.split("/")
                if len(parts) != 6:
                    response(self, 404, {"error": "a2a_route_not_supported"})
                    return
                tenant_id = parts[4]
                channel_id = parts[5]
                cursor = load_a2a_cursor(tenant_id, channel_id)
                message_payloads = []
                for message_id in load_a2a_messages(tenant_id, channel_id):
                    envelope = get_json(a2a_message_id_key(message_id))
                    if envelope is not None:
                        message_payloads.append(envelope)
                response(self, 200, {
                    "tenant_id": tenant_id,
                    "channel_id": channel_id,
                    "cursor": cursor,
                    "messages": message_payloads,
                })
                return
            if path.startswith("/v1/a2a/channels/") and path.endswith("/cursor"):
                parts = path.split("/")
                if len(parts) != 7:
                    response(self, 404, {"error": "a2a_route_not_supported"})
                    return
                tenant_id = parts[4]
                channel_id = parts[5]
                cursor = load_a2a_cursor(tenant_id, channel_id)
                response(self, 200, cursor)
                return
            if path == "/v1/cases":
                query = parse_qs(parsed.query)
                tenant_id = (query.get("tenant", [""])[0] or "").strip()
                if not tenant_id:
                    response(self, 400, {
                        "error": "case_query_requires_tenant",
                    })
                    return
                response(self, 200, {
                    "cases": project_case_control_service().list_case_refs(tenant_id),
                })
                return
            if path.startswith("/v1/workflows/"):
                parts = path.split("/")
                if len(parts) not in {5, 6}:
                    response(self, 404, {"error": "workflow_route_not_supported"})
                    return
                service = workflow_control_service()
                tenant_id = parts[3]
                goal_id = parts[4]
                workflow = service.load_workflow_by_goal(tenant_id, goal_id)
                if workflow is None:
                    response(self, 404, {
                        "error": "project_workflow_not_found",
                        "tenant_id": tenant_id,
                        "goal_id": goal_id,
                    })
                    return
                if len(parts) == 6 and parts[5] == "status":
                    response(self, 200, {
                        "tenant_id": tenant_id,
                        "goal_id": goal_id,
                        "workflow_id": workflow["workflow_id"],
                        "status": workflow["status"],
                        "version": workflow["version"],
                        "query_count": workflow.get("query_count", 0),
                        "signal_count": workflow.get("signal_count", 0),
                    })
                    return
                if len(parts) == 5:
                    response(self, 200, workflow)
                    return
                response(self, 404, {"error": "workflow_route_not_supported"})
                return
            if path.startswith("/v1/goals/"):
                parts = path.split("/")
                if len(parts) == 6 and parts[5] == "audit":
                    service = goal_control_service()
                    tenant_id = parts[3]
                    goal_id = parts[4]
                    response(self, 200, {
                        "tenant_id": tenant_id,
                        "goal_id": goal_id,
                        "audit_events": service.load_audit_events(
                            tenant_id,
                            goal_id,
                        ),
                    })
                    return
                if len(parts) == 5:
                    service = goal_control_service()
                    tenant_id = parts[3]
                    goal_id = parts[4]
                    goal = service.load_goal(tenant_id, goal_id)
                    if goal is None:
                        response(self, 404, {
                            "error": "goal_not_found",
                            "tenant_id": tenant_id,
                            "goal_id": goal_id,
                        })
                        return
                    response(self, 200, goal)
                    return
                response(self, 404, {"error": "goal_route_not_supported"})
                return
            if path.startswith("/v1/cases/"):
                parts = path.split("/")
                if len(parts) == 6 and parts[5] == "audit":
                    service = project_case_control_service()
                    tenant_id = parts[3]
                    case_id = parts[4]
                    case = service.load_case(tenant_id, case_id)
                    if case is None:
                        response(self, 404, {
                            "error": "project_case_not_found",
                            "tenant_id": tenant_id,
                            "case_id": case_id,
                        })
                        return
                    response(self, 200, {
                        "tenant_id": tenant_id,
                        "case_id": case_id,
                        "audit_events": service.load_audit_events(
                            tenant_id,
                            case_id,
                        ),
                        })
                    return
                if len(parts) == 6 and parts[5] == "lineage":
                    service = project_case_control_service()
                    tenant_id = parts[3]
                    case_id = parts[4]
                    lineage = service.load_case_lineage(tenant_id, case_id)
                    if lineage is None:
                        response(self, 404, {
                            "error": "project_case_not_found",
                            "tenant_id": tenant_id,
                            "case_id": case_id,
                        })
                        return
                    response(self, 200, lineage)
                    return
                if len(parts) == 6 and parts[5] == "stale":
                    service = project_case_control_service()
                    tenant_id = parts[3]
                    case_id = parts[4]
                    staleness = service.load_case_staleness(tenant_id, case_id)
                    if staleness is None:
                        response(self, 404, {
                            "error": "project_case_not_found",
                            "tenant_id": tenant_id,
                            "case_id": case_id,
                        })
                        return
                    response(self, 200, staleness)
                    return
                if len(parts) == 6 and parts[5] == "diff":
                    service = project_case_control_service()
                    tenant_id = parts[3]
                    case_id = parts[4]
                    query = parse_qs(parsed.query)
                    from_version = (query.get("from_version") or [""])[0].strip()
                    to_version = (query.get("to_version") or [""])[0].strip()
                    if not from_version or not to_version:
                        service._reject(
                            "project_case_diff_versions_required",
                            "/diff",
                            status=400,
                        )
                    try:
                        from_version_value = int(from_version)
                    except ValueError:
                        service._reject(
                            "project_case_diff_version_invalid",
                            "/from_version",
                            status=400,
                        )
                    try:
                        to_version_value = int(to_version)
                    except ValueError:
                        service._reject(
                            "project_case_diff_version_invalid",
                            "/to_version",
                            status=400,
                        )
                    response(self, 200, service.diff_case(
                        tenant_id,
                        case_id,
                        from_version_value,
                        to_version_value,
                    ))
                    return
                if len(parts) == 6 and parts[5] == "export":
                    service = project_case_control_service()
                    tenant_id = parts[3]
                    case_id = parts[4]
                    export = service.export_case(tenant_id, case_id)
                    if export is None:
                        response(self, 404, {
                            "error": "project_case_not_found",
                            "tenant_id": tenant_id,
                            "case_id": case_id,
                        })
                        return
                    response(self, 200, export)
                    return
                if len(parts) == 5:
                    service = project_case_control_service()
                    tenant_id = parts[3]
                    case_id = parts[4]
                    case = service.load_case(tenant_id, case_id)
                    if case is None:
                        response(self, 404, {
                            "error": "project_case_not_found",
                            "tenant_id": tenant_id,
                            "case_id": case_id,
                        })
                        return
                    response(self, 200, case)
                    return
                response(self, 404, {"error": "case_route_not_supported"})
                return
            if path == "/v1/task-graphs":
                service = task_graph_control_service()
                response(self, 200, {"task_graphs": service.list_graph_refs()})
                return
            if path.startswith("/v1/task-graphs/"):
                parts = path.split("/")
                if len(parts) == 6 and parts[5] == "audit":
                    service = task_graph_control_service()
                    tenant_id = parts[3]
                    graph_id = parts[4]
                    response(self, 200, {
                        "tenant_id": tenant_id,
                        "graph_id": graph_id,
                        "audit_events": service.load_audit_events(
                            tenant_id,
                            graph_id,
                        ),
                    })
                    return
                if len(parts) == 5:
                    service = task_graph_control_service()
                    tenant_id = parts[3]
                    graph_id = parts[4]
                    graph = service.load_graph(tenant_id, graph_id)
                    if graph is None:
                        response(self, 404, {
                            "error": "task_graph_not_found",
                            "tenant_id": tenant_id,
                            "graph_id": graph_id,
                        })
                        return
                    response(self, 200, graph)
                    return
                response(self, 404, {"error": "task_graph_route_not_supported"})
                return
            if path == "/v1/tasks":
                query = parse_qs(parsed.query)
                wanted = query.get("state", [None])[0]
                limit = min(max(int(query.get("limit", ["100"])[0]), 1), 250)
                offset = max(int(query.get("offset", ["0"])[0]), 0)
                task_ids = list(reversed(all_task_ids()))
                total_indexed = len(task_ids)
                if wanted is None:
                    task_ids = task_ids[offset:offset + limit]
                tasks = [load_task(task_id) for task_id in task_ids]
                tasks = [task for task in tasks if task and (wanted is None or task.get("state") == wanted)]
                if wanted is not None:
                    tasks = tasks[offset:offset + limit]
                queue = queue_ids()
                response(self, 200, {
                    "tasks": tasks,
                    "queue": queue[:250],
                    "pagination": {"limit": limit, "offset": offset, "returned": len(tasks), "total_indexed": total_indexed},
                    "queue_total": len(queue),
                })
                return
            if path.startswith("/v1/tasks/"):
                task_id = path.split("/", 3)[3]
                task = load_task(task_id)
                if not task:
                    response(self, 404, {"error": "task_not_found", "task_id": task_id})
                    return
                response(self, 200, task)
                return
            if path.startswith("/v1/superfactory/tasks/") and path.endswith("/artifacts"):
                auth = validate_miniapp(self)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                task_id = path.split("/")[4]
                task = load_task(task_id)
                if not task:
                    response(self, 404, {"error": "task_not_found", "task_id": task_id})
                    return
                result = task.get("result") or {}
                response(self, 200, {
                    "task_id": task_id,
                    "state": task.get("state"),
                    "artifacts": {
                        "pull_request_url": result.get("pull_request_url") or result.get("pr_url"),
                        "preview_url": result.get("preview_url"),
                        "ci_url": result.get("ci_url"),
                        "result_reference": task.get("result_reference"),
                    },
                })
                return
            if path.startswith("/v1/agents/status/"):
                task_id = path.split("/", 4)[4]
                task = load_task(task_id)
                if not task:
                    response(self, 404, canonical_response_envelope(
                        status="blocked",
                        task_id=task_id,
                        route_used="/v1/agents/status",
                        blocked_reason="unknown",
                        repair_task={"kind": "verify_agent_task_id", "task_id": task_id},
                        next_action="submit a task through /v1/agents/tasks or verify the task id",
                    ))
                    return
                response(self, 200, canonical_response_envelope(
                    status="completed" if task.get("state") in TERMINAL_STATES else "running",
                    task_id=task_id,
                    node=(task.get("lease_owner") or "home").split(":", 1)[0],
                    route_used="/v1/agents/status",
                    data={"task": task},
                    next_action="poll /v1/agents/artifacts/{task_id}" if task.get("state") in TERMINAL_STATES else "continue polling status",
                ))
                return
            if path == "/v1/agents/assignments":
                query = parse_qs(parsed.query)
                task_id = query.get("task_id", [None])[0]
                assignment_ids = list_assignment_ids(task_id)
                assignments = []
                for assignment_id in assignment_ids:
                    assignment = load_assignment(assignment_id)
                    if assignment is not None:
                        assignments.append(assignment)
                response(self, 200, {
                    "assignments": assignments,
                })
                return
            if (
                path.startswith("/v1/agents/assignments/")
                and path.endswith("/events")
            ):
                assignment_id = (
                    path.split("/", 4)[4].rsplit("/events", 1)[0]
                )
                assignment = load_assignment(assignment_id)
                if not assignment:
                    response(self, 404, {
                        "error": "assignment_not_found",
                        "assignment_id": assignment_id,
                    })
                    return
                response(self, 200, {
                    "assignment_id": assignment_id,
                    "events": load_assignment_status_events(
                        assignment_id,
                    ),
                })
                return
            if path.startswith("/v1/agents/assignments/"):
                assignment_id = path.split("/", 4)[4]
                assignment = load_assignment(assignment_id)
                if not assignment:
                    response(self, 404, {"error": "assignment_not_found", "assignment_id": assignment_id})
                    return
                response(self, 200, assignment)
                return
            if path.startswith("/v1/agents/artifacts/"):
                task_id = path.split("/", 4)[4]
                task = load_task(task_id)
                envelope = task_artifact_envelope(task, task_id)
                response(self, 200 if task else 404, envelope)
                return
            response(self, 404, {"error": "not_found", "path": path})
        except AgentControlAuthError as exc:
            response(self, exc.status, {
                "error": "agent_control_unauthorized",
                "code": exc.code,
            })
        except Exception as exc:  # pragma: no cover - surfaced in runtime logs
            response(self, 500, {"error": "control_plane_error", "detail": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            remote_logical_path = remote_agent_control_logical_path(
                self.path,
            )
            self._agent_control_identity = None
            if remote_logical_path is not None:
                if not remote_agent_control_post_allowed(
                    remote_logical_path,
                ):
                    raise AgentControlAuthError(
                        "agent_control_remote_route_forbidden",
                        status=403,
                    )
                raw_body = read_raw_body(self)
                self._agent_control_identity = (
                    authenticate_agent_control_request(
                        self,
                        method="POST",
                        logical_path=remote_logical_path,
                        body_bytes=raw_body,
                    )
                )
                parsed = urlparse(remote_logical_path)
                path = parsed.path
            else:
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/") or "/"
                raw_body = read_raw_body(self)
                self_authenticating_request = (
                    self_authenticating_local_post(path)
                )
                signed_agent_request = (
                    not self_authenticating_request
                    and agent_control_signed_headers_present(self)
                )
                if (
                    require_local_mutation_auth()
                    and not self_authenticating_request
                    and not signed_agent_request
                ):
                    raise AgentControlAuthError(
                        "agent_control_auth_headers_required",
                    )
                if signed_agent_request:
                    self._agent_control_identity = (
                        authenticate_agent_control_request(
                            self,
                            method="POST",
                            logical_path=self.path,
                            body_bytes=raw_body,
                            enforce_configured_identity=(
                                path
                                == (
                                    "/v1/agent-control/"
                                    "agent-cards/register"
                                )
                            ),
                        )
                    )
            body = read_body(self)
            if path != "/v1/agent-control/agent-cards/register":
                constrain_agent_control_capabilities(
                    self._agent_control_identity,
                    body,
                )
            if path == "/v1/runtime/product-goal-initializations":
                status_code, result = (
                    product_goal_initialize_control_service().process(
                        body,
                        transport_context=(
                            product_goal_initialize_command_transport_context(
                                self,
                                body,
                            )
                        ),
                    )
                )
                response(self, status_code, result)
                return
            if path == "/v1/runtime/product-text-runs":
                status_code, result = product_text_run_control_service().process(
                    body,
                    transport_context=product_text_run_command_transport_context(
                        self,
                        body,
                    ),
                )
                response(self, status_code, result)
                return
            if path == "/v1/goals/commands":
                status_code, result = goal_control_service().process(
                    body,
                    transport_context=goal_command_transport_context(self, body),
                )
                response(self, status_code, result)
                return
            if path.startswith("/v1/workflows/"):
                parts = path.split("/")
                if len(parts) == 6 and parts[5] == "query":
                    tenant_id = parts[3]
                    goal_id = parts[4]
                    if not isinstance(body, dict):
                        response(
                            self,
                            400,
                            {
                                "error": "invalid_request",
                                "code": "workflow_query_payload_object_required",
                            },
                        )
                        return
                    query_type = str(body.get("query_type") or "").strip()
                    if not query_type:
                        response(
                            self,
                            400,
                            {
                                "error": "workflow_query_type_required",
                            },
                        )
                        return
                    try:
                        workflow, query = workflow_control_service().query(
                            tenant_id,
                            goal_id,
                            query_type=query_type,
                            query_scope=str(body.get("query_scope") or "") or None,
                        )
                    except ProjectWorkflowError as exc:
                        response(self, exc.status, exc.as_dict())
                        return
                    response(self, 200, {
                        "tenant_id": tenant_id,
                        "goal_id": goal_id,
                        "workflow_id": workflow["workflow_id"],
                        "workflow": workflow,
                        "query": query,
                    })
                    return
                if len(parts) == 6 and parts[5] == "cancel":
                    tenant_id = parts[3]
                    goal_id = parts[4]
                    try:
                        workflow = workflow_control_service().cancel(tenant_id, goal_id)
                    except ProjectWorkflowError as exc:
                        response(self, exc.status, exc.as_dict())
                        return
                    response(self, 200, {
                        "tenant_id": tenant_id,
                        "goal_id": goal_id,
                        "workflow": workflow,
                    })
                    return
                if len(parts) == 6 and parts[5] == "signal":
                    tenant_id = parts[3]
                    goal_id = parts[4]
                    if not isinstance(body, dict):
                        response(
                            self,
                            400,
                            {
                                "error": "invalid_request",
                                "code": "workflow_signal_payload_object_required",
                            },
                        )
                        return
                    signal_type = str(body.get("signal_type") or "").strip()
                    if not signal_type:
                        response(
                            self,
                            400,
                            {
                                "error": "workflow_signal_type_required",
                            },
                        )
                        return
                    signal_id = body.get("signal_id")
                    payload = body.get("payload")
                    actor_id = body.get("actor_id")
                    expected_version = body.get("expected_version")
                    try:
                        expected_version_int = int(expected_version) if expected_version is not None and str(expected_version).strip() != "" else None
                    except (TypeError, ValueError):
                        expected_version_int = None
                    try:
                        workflow, signal = workflow_control_service().signal(
                            tenant_id,
                            goal_id,
                            signal_type=signal_type,
                            signal_id=signal_id,
                            payload=payload if isinstance(payload, dict) else None,
                            actor_id=actor_id,
                            expected_version=expected_version_int,
                        )
                    except ProjectWorkflowError as exc:
                        response(self, exc.status, exc.as_dict())
                        return
                    response(self, 200, {
                        "tenant_id": tenant_id,
                        "goal_id": goal_id,
                        "workflow": workflow,
                        "signal": signal,
                    })
                    return
                if len(parts) == 8 and parts[5] == "signal" and parts[7] == "ack":
                    tenant_id = parts[3]
                    goal_id = parts[4]
                    signal_id = parts[6]
                    if not signal_id:
                        response(
                            self,
                            400,
                            {"error": "workflow_signal_id_required"},
                        )
                        return
                    if not isinstance(body, dict):
                        response(
                            self,
                            400,
                            {"error": "invalid_request", "code": "workflow_signal_ack_payload_object_required"},
                        )
                        return
                    outcome = str(body.get("outcome") or "resolved")
                    try:
                        workflow = workflow_control_service().acknowledge_signal(
                            tenant_id,
                            goal_id,
                            signal_id=signal_id,
                            outcome=outcome,
                        )
                    except ProjectWorkflowError as exc:
                        response(self, exc.status, exc.as_dict())
                        return
                    response(self, 200, {
                        "tenant_id": tenant_id,
                        "goal_id": goal_id,
                        "workflow": workflow,
                        "signal_id": signal_id,
                        "outcome": outcome,
                    })
                    return
                response(self, 404, {"error": "workflow_route_not_supported"})
                return
            if path == "/v1/task-graphs/commands":
                with NODE_UPDATE_LOCK:
                    status_code, result = task_graph_control_service().process(
                        body,
                        transport_context=task_graph_command_transport_context(
                            self,
                            body,
                        ),
                )
                    # The graph commit is authoritative and atomic. Queue
                    # records are a recoverable compatibility projection;
                    # reconcile on every successful command and again at
                    # lease time. The shared mutation lock prevents a local
                    # lease from racing between graph commit and projection.
                    reconcile_task_graph_execution(result["task_graph"])
                response(self, status_code, result)
                return
            if path.startswith("/v1/cases/"):
                parts = path.split("/")
                if len(parts) == 6 and parts[5] in {"facts", "assumptions", "decisions"}:
                    tenant_id = str(parts[3])
                    case_id = str(parts[4])
                    register = str(parts[5])
                    if not isinstance(body, dict):
                        response(
                            self,
                            400,
                            {"error": "invalid_request", "code": "case_register_payload_object_required"},
                        )
                        return
                    command = dict(body)
                    command.setdefault(
                        "message_id",
                        f"case-register:{tenant_id}:{case_id}:{register}",
                    )
                    transport_context = project_case_command_transport_context(self, command)
                    idempotency_key = (
                        self.headers.get("Idempotency-Key")
                        or self.headers.get("X-Kolibri-Idempotency-Key")
                        or str(body.get("idempotency_key") or "")
                    )
                    request_hash = _request_signature(
                        {
                            "tenant_id": tenant_id,
                            "case_id": case_id,
                            "register": register,
                            "item": body,
                            "actor": transport_context["actor"],
                        },
                    )
                    service = project_case_control_service()
                    if register == "facts":
                        status_code, result = service.append_fact(
                            tenant_id,
                            case_id,
                            body,
                            transport_context=transport_context,
                            idempotency_key=idempotency_key,
                            request_hash=request_hash,
                        )
                    elif register == "assumptions":
                        status_code, result = service.append_assumption(
                            tenant_id,
                            case_id,
                            body,
                            transport_context=transport_context,
                            idempotency_key=idempotency_key,
                            request_hash=request_hash,
                        )
                    else:
                        status_code, result = service.append_decision(
                            tenant_id,
                            case_id,
                            body,
                            transport_context=transport_context,
                            idempotency_key=idempotency_key,
                            request_hash=request_hash,
                        )
                    response(self, status_code, result)
                    return
            if path == "/v1/agent-control/agent-cards/register":
                outcome, stored = register_agent_control_runtime_card(
                    self._agent_control_identity,
                    body,
                )
                if outcome == "existing":
                    response(self, 200, stored)
                    return
                if outcome in {
                    "conflict",
                    "runtime_profile_conflict",
                }:
                    response(self, 409, {
                        "error": (
                            "a2a_runtime_profile_agent_card_conflict"
                            if outcome == "runtime_profile_conflict"
                            else "a2a_agent_card_conflict"
                        ),
                        "agent_card_id": (
                            body.get("agent_card") or {}
                        ).get("agent_card_id"),
                    })
                    return
                if outcome != "committed":
                    raise RuntimeError(
                        "a2a_agent_card_registry_write_failed:"
                        f"{outcome}",
                    )
                response(self, 201, stored)
                return
            if path == "/v1/nodes/register":
                bind_agent_control_identity(
                    self._agent_control_identity,
                    body,
                )
                requested_node_id = str(body["node_id"])
                try:
                    node = persist_node_heartbeat(requested_node_id, body)
                except LookupError as exc:
                    response(self, 404, {"error": str(exc), "node_id": resolve_logical_node_id(requested_node_id, body)})
                    return
                except ValueError as exc:
                    response(self, 400, {"error": str(exc), "node_id": requested_node_id})
                    return
                response(self, 200, node)
                return
            if path.startswith("/v1/nodes/") and path.endswith("/heartbeat"):
                requested_node_id = path.split("/")[3]
                bind_agent_control_identity(
                    self._agent_control_identity,
                    body,
                    path_node_id=requested_node_id,
                )
                try:
                    node = persist_node_heartbeat(requested_node_id, body)
                except LookupError as exc:
                    response(self, 404, {"error": str(exc), "node_id": resolve_logical_node_id(requested_node_id, body)})
                    return
                except ValueError as exc:
                    response(self, 400, {"error": str(exc), "node_id": requested_node_id})
                    return
                response(self, 200, node)
                return
            if path.startswith("/v1/nodes/") and path.endswith("/drain"):
                node_id = path.split("/")[3]
                drain = bool(body.get("drain", True))
                if drain:
                    redis.command("SET", drain_key(node_id), "1")
                else:
                    redis.command("DEL", drain_key(node_id))
                response(self, 200, {"node_id": node_id, "draining": drain})
                return
            if path == "/v1/tasks":
                task = create_task(
                    body,
                    allow_legacy=unsigned_legacy_task_http_enabled(),
                )
                response(self, 201, task)
                return
            if path == "/v1/truth/claim":
                claim = create_claim(
                    body.get("task_id", "manual"),
                    body.get("made_by", "owner"),
                    body.get("claim", ""),
                    body.get("scope", "manual"),
                )
                response(self, 201, asdict(claim))
                return
            if path == "/v1/truth/evidence":
                ev = add_evidence(
                    body.get("claim_id", ""),
                    body.get("type", "manual"),
                    body.get("source", ""),
                    body.get("summary", ""),
                    body.get("path", ""),
                )
                response(self, 201, asdict(ev))
                return
            if path == "/v1/truth/verdict":
                v = set_verdict(
                    body.get("claim_id", ""),
                    body.get("verdict", "not_proven"),
                    body.get("confidence", "low"),
                    body.get("reasoning", ""),
                    body.get("next_action", ""),
                    body.get("owner_summary", ""),
                )
                response(self, 201, asdict(v))
                return
            if path.startswith("/v1/disputes/"):
                parts = path.split("/")
                if len(parts) != 4:
                    response(self, 404, {"error": "dispute_route_not_supported"})
                    return
                scope = _normalize_dispute_scope(parts[3])
                if scope != (parts[3] or "").strip().lower():
                    response(self, 400, {
                        "error": "invalid_dispute_scope",
                        "scope": parts[3],
                    })
                    return
                if not isinstance(body, dict):
                    response(
                        self,
                        400,
                        {"error": "invalid_request", "code": "dispute_payload_object_required"},
                    )
                    return
                claim_id = str(body.get("claim_id") or "").strip()
                actor_id = str(body.get("actor_id") or "").strip()
                if not claim_id or not actor_id:
                    response(
                        self,
                        400,
                        {"error": "dispute_payload_required", "code": "claim_id_and_actor_id_required"},
                    )
                    return
                tenant_id = str(body.get("tenant_id") or "").strip()
                if not tenant_id:
                    response(
                        self,
                        400,
                        {"error": "dispute_payload_required", "code": "tenant_id_required"},
                    )
                    return
                claim = _truth_claims.get(claim_id)
                requested_decision = body.get("requested_decision")
                decision, status, reason = resolve_dispute(
                    scope,
                    claim,
                    str(requested_decision).strip() if requested_decision else None,
                )
                if requested_decision and str(requested_decision).strip() not in {
                    "approved",
                    "rejected",
                    "needs_more_evidence",
                    "escalated",
                    "deadlock",
                }:
                    response(
                        self,
                        422,
                        {
                            "error": "invalid_dispute_decision",
                            "requested_decision": requested_decision,
                        },
                    )
                    return
                verdict = _normalize_dispute_decision(str(requested_decision or ""))
                dispute = Dispute(
                    dispute_id=_id("D"),
                    tenant_id=tenant_id,
                    scope=scope,
                    claim_id=claim_id,
                    actor_id=actor_id,
                    claim_verdict=str(claim.verdict if claim and claim.verdict else "not_proven"),
                    claim_evidence_count=claim_evidence_count(claim),
                    risk=evaluate_dispute_risk(scope, claim),
                    decision=decision,
                    status=status,
                    reason=reason,
                    next_action="independent_reviewer" if status in {"escalated", "pending"} else "director_notify",
                    events=[{
                        "event": "created",
                        "actor_id": actor_id,
                        "scope": scope,
                        "requested_decision": verdict,
                        "reason": reason,
                        "created_at": utc_now(),
                    }],
                )
                save_dispute(dispute)
                response(self, 201, asdict(dispute))
                return
            if path == "/v1/superfactory/tasks":
                auth = validate_miniapp(self, body)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                try:
                    envelope = miniapp_task_envelope(body, auth)
                except ValueError as exc:
                    response(self, 400, {"error": "invalid_task", "detail": str(exc)})
                    return
                task = create_task(
                    envelope,
                    allow_legacy=unsigned_legacy_task_http_enabled(),
                )
                response(self, 201, task)
                return
            if path == "/v1/agents/tasks":
                envelope = task_envelope_from_request(body)
                task = create_task(
                    envelope,
                    allow_legacy=unsigned_legacy_task_http_enabled(),
                )
                response(self, 201, canonical_response_envelope(
                    status="running",
                    task_id=task["task_id"],
                    trace_id=envelope.get("trace_id") or task["task_id"],
                    node=envelope.get("target_node") or "home",
                    route_used="/v1/agents/tasks",
                    data={"task": task},
                    next_action="poll /v1/agents/status/{task_id}",
                ))
                return
            if path == "/v1/os/capabilities/invoke":
                envelope = os_capability_invoke_envelope(body)
                response(self, 200 if envelope["status"] == "completed" else 403, envelope)
                return
            if path in {"/v1/responses", "/v1/chat/completions"}:
                if _forward_to_model_runtime(self, path, body):
                    return
                response(self, 503, model_stub_envelope(body, endpoint=path))
                return
            # ── Admin endpoints ────────────────────────────────────────
            if path == "/v1/admin/exec":
                auth = validate_miniapp(self, body)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                target = body.get("target_node")
                if not target:
                    response(self, 400, {"error": "target_node required"})
                    return
                command = body.get("command")
                if not command:
                    response(self, 400, {"error": "command required"})
                    return
                envelope = {
                    "kind": "admin_exec",
                    "target_node": target,
                    "required_capability": "admin_exec",
                    "objective": json.dumps({
                        "command": command,
                        "cwd": body.get("cwd", "/"),
                        "timeout": body.get("timeout", 30),
                        "env": body.get("env", {}),
                    }),
                    "source": {"kind": "admin_api", "user_id": auth["user"]["id"], "endpoint": "/v1/admin/exec"},
                    "max_retries": 0,
                }
                task = create_task(
                    envelope,
                    allow_legacy=unsigned_legacy_task_http_enabled(),
                )
                response(self, 202, canonical_response_envelope(
                    status="running", task_id=task["task_id"],
                    node=target, route_used="/v1/admin/exec",
                    data={"task": task},
                    next_action=f"poll /v1/agents/status/{task['task_id']}",
                ))
                return
            if path == "/v1/admin/service":
                auth = validate_miniapp(self, body)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                target = body.get("target_node")
                if not target:
                    response(self, 400, {"error": "target_node required"})
                    return
                action = body.get("action", "status")
                service = body.get("service")
                if not service:
                    response(self, 400, {"error": "service name required"})
                    return
                if action not in ("start", "stop", "restart", "status", "enable", "disable"):
                    response(self, 400, {"error": f"invalid action: {action}"})
                    return
                envelope = {
                    "kind": "admin_service",
                    "target_node": target,
                    "required_capability": "admin_service",
                    "objective": json.dumps({
                        "action": action,
                        "service": service,
                    }),
                    "source": {"kind": "admin_api", "user_id": auth["user"]["id"], "endpoint": "/v1/admin/service"},
                    "max_retries": 0,
                }
                task = create_task(
                    envelope,
                    allow_legacy=unsigned_legacy_task_http_enabled(),
                )
                response(self, 202, canonical_response_envelope(
                    status="running", task_id=task["task_id"],
                    node=target, route_used="/v1/admin/service",
                    data={"task": task},
                    next_action=f"poll /v1/agents/status/{task['task_id']}",
                ))
                return
            if path == "/v1/admin/git":
                auth = validate_miniapp(self, body)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                target = body.get("target_node")
                if not target:
                    response(self, 400, {"error": "target_node required"})
                    return
                action = body.get("action", "status")
                if action not in ("status", "pull", "diff", "log", "stash"):
                    response(self, 400, {"error": f"invalid action: {action}"})
                    return
                envelope = {
                    "kind": "admin_git",
                    "target_node": target,
                    "required_capability": "admin_git",
                    "objective": json.dumps({
                        "action": action,
                        "branch": body.get("branch"),
                        "remote": body.get("remote", "origin"),
                        "path": body.get("path", "/opt/kolibri-ai-platform"),
                    }),
                    "source": {"kind": "admin_api", "user_id": auth["user"]["id"], "endpoint": "/v1/admin/git"},
                    "max_retries": 0,
                }
                task = create_task(
                    envelope,
                    allow_legacy=unsigned_legacy_task_http_enabled(),
                )
                response(self, 202, canonical_response_envelope(
                    status="running", task_id=task["task_id"],
                    node=target, route_used="/v1/admin/git",
                    data={"task": task},
                    next_action=f"poll /v1/agents/status/{task['task_id']}",
                ))
                return
            if path == "/v1/admin/bootstrap-node":
                auth = validate_miniapp(self, body)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                status_code, payload = bootstrap_node_contract(body)
                response(self, status_code, payload)
                return
            if path == "/v1/admin/rotate-keys":
                auth = validate_miniapp(self, body)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                target = body.get("target_node")
                if not target:
                    response(self, 400, {"error": "target_node required"})
                    return
                envelope = {
                    "kind": "admin_rotate_keys",
                    "target_node": target,
                    "required_capability": "admin_rotate_keys",
                    "objective": json.dumps({"reason": body.get("reason", "operator_rotation")}),
                    "source": {"kind": "admin_api", "user_id": auth["user"]["id"], "endpoint": "/v1/admin/rotate-keys"},
                    "max_retries": 0,
                }
                task = create_task(
                    envelope,
                    allow_legacy=unsigned_legacy_task_http_enabled(),
                )
                response(self, 202, canonical_response_envelope(
                    status="running", task_id=task["task_id"],
                    node=target, route_used="/v1/admin/rotate-keys",
                    data={"task": task},
                    next_action=f"poll /v1/agents/status/{task['task_id']}",
                ))
                return
            if path == "/v1/admin/self-update":
                auth = validate_miniapp(self, body)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                target = body.get("target_node")
                if not target:
                    response(self, 400, {"error": "target_node required"})
                    return
                # Build binary URL — agents download from control plane
                cp_host = os.environ.get("KOLIBRI_SELF_UPDATE_HOST", "10.99.0.1")
                cp_port = os.environ.get("KOLIBRI_SELF_UPDATE_PORT", "9101")
                binary_url = body.get("binary_url") or f"http://{cp_host}:{cp_port}/v1/admin/agent-host-binary"
                import hashlib as _hl
                binary_path = Path(os.environ.get(
                    "KOLIBRI_AGENT_HOST_BINARY", "/usr/local/bin/kolibri-agent-host"))
                expected_sha256 = ""
                if binary_path.exists():
                    expected_sha256 = _hl.sha256(binary_path.read_bytes()).hexdigest()
                new_caps = body.get("capabilities") or (
                    "generic_implementation,read_only_probe,"
                    "admin_exec,admin_service,admin_git,admin_rotate_keys,admin_self_update"
                )
                envelope = {
                    "kind": "admin_self_update",
                    "target_node": target,
                    "required_capability": "admin_exec",
                    "objective": json.dumps({
                        "binary_url": binary_url,
                        "sha256": expected_sha256,
                        "capabilities": new_caps,
                    }),
                    "source": {"kind": "admin_api", "user_id": auth["user"]["id"], "endpoint": "/v1/admin/self-update"},
                    "max_retries": 0,
                }
                task = create_task(
                    envelope,
                    allow_legacy=unsigned_legacy_task_http_enabled(),
                )
                response(self, 202, canonical_response_envelope(
                    status="running", task_id=task["task_id"],
                    node=target, route_used="/v1/admin/self-update",
                    data={"task": task, "binary_url": binary_url, "sha256": expected_sha256},
                    next_action=f"poll /v1/agents/status/{task['task_id']}",
                ))
                return
            if path == "/v1/a2a/agent-cards":
                transport_context = (
                    logical_home_a2a_mutation_transport_context(
                        self,
                        body,
                        action="a2a.agent_card.register",
                        required_capability="a2a.agent_card.register",
                    )
                )
                try:
                    card = parse_declared_a2a_agent_card_v1(body)
                except DeclaredContractV1Error as exc:
                    response(self, 422, {
                        "error": "contract_v1_rejected",
                        "code": exc.code,
                        "violations": exc.violations,
                    })
                    return
                bind_a2a_agent_card_transport(
                    card,
                    transport_context,
                )
                outcome, stored = create_a2a_agent_card_atomically(card)
                if outcome == "existing":
                    response(self, 200, stored)
                    return
                if outcome == "conflict":
                    response(self, 409, {
                        "error": "a2a_agent_card_conflict",
                        "agent_card_id": card["agent_card_id"],
                    })
                    return
                if outcome != "committed":
                    raise RuntimeError(
                        f"a2a_agent_card_registry_write_failed:{outcome}",
                    )
                response(self, 201, card)
                return
            if path == "/v1/a2a/messages":
                now = utc_now()
                transport_context = (
                    logical_home_a2a_mutation_transport_context(
                        self,
                        body,
                        action="a2a.message.append",
                        required_capability="a2a.message.append",
                    )
                )
                try:
                    event, message = parse_declared_a2a_event_v1(body)
                except DeclaredContractV1Error as exc:
                    response(self, 422, {
                        "error": "contract_v1_rejected",
                        "code": exc.code,
                        "violations": exc.violations,
                    })
                    return
                bind_a2a_event_transport(
                    event,
                    message,
                    transport_context,
                )
                result = append_a2a_message_atomically(
                    message,
                    event,
                    now,
                )
                decision = result["decision"]
                if decision == "duplicate_noop":
                    response(self, 200, {
                        "decision": decision,
                        "message_id": message["a2a_message_id"],
                    })
                    return
                if decision == "assignment_auth_rejected":
                    response(self, 409, {
                        "error": "a2a_assignment_rejected",
                        "decision": decision,
                        "violations": result["violations"],
                        "message_id": message["a2a_message_id"],
                    })
                    return
                if decision != "accepted":
                    response(self, 409, {
                        "error": "a2a_message_rejected",
                        "decision": decision,
                        "code": result["code"],
                        "tenant_id": message["tenant_id"],
                        "channel_id": message["channel_id"],
                        "message_id": message["a2a_message_id"],
                    })
                    return
                response(self, 201, {
                    "decision": "accepted",
                    "message_id": message["a2a_message_id"],
                    "cursor": result["cursor"],
                })
                return
            if path == "/v1/fabric/route":
                route = fabric_route(
                    target_node=body.get("target_node"),
                    required_capability=body.get("required_capability"),
                    registered_nodes=registered_nodes(),
                )
                response(self, 200 if route.get("status") == "ok" else 503, route)
                return
            if path == "/v1/fabric/relay":
                route = fabric_route(
                    target_node=body.get("target_node"),
                    required_capability=body.get("required_capability"),
                    registered_nodes=registered_nodes(),
                )
                if route.get("status") != "ok" and not route.get("can_continue_elsewhere"):
                    response(self, 503, route)
                    return
                response(self, 202, {
                    "status": "accepted",
                    "relay": "safe_stub",
                    "route": route,
                    "message": "relay contract accepted; privileged execution must be performed by an authenticated agent host",
                })
                return
            if path == "/v1/policy/decide":
                response(self, 200, policy_decision_service().evaluate(body))
                return
            if path == "/v1/fabric/bootstrap":
                status_code, payload = bootstrap_node_contract(body)
                response(self, status_code, payload)
                return
            if path == "/v1/agents/assignments":
                transport_context = (
                    logical_home_a2a_mutation_transport_context(
                        self,
                        body,
                        action="a2a.agent_assignment.create",
                        required_capability=(
                            "a2a.agent_assignment.create"
                        ),
                    )
                )
                try:
                    assignment = parse_declared_assignment_v1(body)
                except DeclaredContractV1Error as exc:
                    response(self, 422, {
                        "error": "contract_v1_rejected",
                        "code": exc.code,
                        "violations": exc.violations,
                    })
                    return
                bind_assignment_transport(
                    assignment,
                    transport_context,
                    require_available_card=True,
                )
                assignment_id = str(assignment.get("assignment_id") or "").strip()
                outcome, stored = create_assignment_atomically(assignment)
                if outcome == "existing":
                    response(self, 200, stored)
                    return
                if outcome == "conflict":
                    response(self, 409, {
                        "error": "assignment_id_conflict",
                        "assignment_id": assignment_id,
                    })
                    return
                if outcome != "committed":
                    raise RuntimeError(
                        f"assignment_registry_write_failed:{outcome}",
                    )
                response(self, 201, assignment)
                return
            if path == "/v1/tasks/lease":
                bind_agent_control_identity(
                    self._agent_control_identity,
                    body,
                )
                requeue_expired_leases()
                reconcile_all_task_graph_execution()
                node_id = body["node_id"]
                if redis.command("GET", drain_key(node_id)):
                    response(self, 204, {})
                    return
                agent_id = body.get("agent_id", node_id)
                raw_node = get_json(node_key(node_id))
                if raw_node is None:
                    response(self, 403, {
                        "error": "agent_control_node_not_registered",
                        "node_id": node_id,
                    })
                    return
                try:
                    capabilities, claim_node, slot_id = lease_claim_view(raw_node, body)
                except ValueError as exc:
                    response(self, 409, {"error": str(exc), "node_id": node_id})
                    return
                lease_slot_id = slot_id or str(agent_id)
                with NODE_UPDATE_LOCK:
                    resumed = (
                        resume_active_product_developer_lease_for_claim(
                            node_id=node_id,
                            agent_id=agent_id,
                            slot_id=lease_slot_id,
                            capabilities=capabilities,
                            node=claim_node,
                        )
                    )
                    if resumed is not None:
                        parse_declared_contract_v1(
                            resumed.get("envelope", {}),
                            "kolibri.task",
                            bound_id=str(resumed["task_id"]),
                        )
                        response(self, 200, resumed)
                        return
                    for task_id in canonical_lease_queue_ids():
                        task = load_task(task_id)
                        if not task or task.get("state") not in {STATE_QUEUED, STATE_REVIEW}:
                            remove_from_queue(task_id)
                            continue
                        if not compatible(task, node_id, capabilities, claim_node):
                            continue
                        canonical_task = parse_declared_contract_v1(
                            task.get("envelope", {}),
                            "kolibri.task",
                            bound_id=str(task["task_id"]),
                        )
                        canonical_graph = None
                        if canonical_task is not None:
                            # Re-read immediately before the mutation so a
                            # stale graph-version sidecar cannot be leased.
                            try:
                                canonical_graph = authoritative_graph_for_canonical_task(
                                    canonical_task,
                                )
                            except DeclaredContractV1Error:
                                remove_from_queue(task_id)
                                continue
                        try:
                            task = claim_task_lease_atomically(
                                task,
                                node_id=node_id,
                                agent_id=agent_id,
                                slot_id=lease_slot_id,
                                canonical_task=canonical_task,
                                canonical_graph=canonical_graph,
                            )
                        except DeclaredContractV1Error as exc:
                            if exc.code in {
                                "canonical_execution_agent_card_unavailable",
                                "product_developer_agent_card_unavailable",
                                "logical_home_requester_card_unavailable",
                            }:
                                continue
                            raise
                        if task is None:
                            continue
                        parse_declared_contract_v1(
                            task.get("envelope", {}),
                            "kolibri.task",
                            bound_id=str(task["task_id"]),
                        )
                        response(self, 200, task)
                        return
                response(self, 204, {})
                return
            if path.startswith("/v1/tasks/") and path.endswith("/heartbeat"):
                task_id = path.split("/")[3]
                bind_agent_control_identity(
                    self._agent_control_identity,
                    body,
                )
                task = load_task(task_id)
                if not task:
                    response(self, 404, {"error": "task_not_found", "task_id": task_id})
                    return
                if is_product_developer_task(task):
                    try:
                        task = heartbeat_product_developer_task_atomically(
                            task,
                            body,
                        )
                    except DeclaredContractV1Error as exc:
                        violation_code = (
                            exc.violations[0].get("code")
                            if exc.violations
                            else exc.code
                        )
                        status_code = (
                            422
                            if exc.code == "invalid_heartbeat_state"
                            else 409
                        )
                        response(self, status_code, {
                            "error": exc.code,
                            "reason": violation_code,
                            "task_id": task_id,
                            "attempt_id": task.get("attempt_id"),
                            "assignment_id": task.get(
                                "current_assignment_id",
                            ),
                        })
                        return
                    response(self, 200, task)
                    return
                canonical_task = parse_declared_contract_v1(
                    task.get("envelope", {}),
                    "kolibri.task",
                    bound_id=task_id,
                )
                if canonical_task is not None:
                    try:
                        task = (
                            heartbeat_canonical_execution_task_atomically(
                                task,
                                body,
                            )
                        )
                    except DeclaredContractV1Error as exc:
                        reason = (
                            exc.violations[0].get("code")
                            if exc.violations
                            else exc.code
                        )
                        response(
                            self,
                            (
                                422
                                if exc.code == "invalid_heartbeat_state"
                                else 409
                            ),
                            {
                                "error": exc.code,
                                "reason": reason,
                                "task_id": task_id,
                                "attempt_id": task.get("attempt_id"),
                                "assignment_id": task.get(
                                    "current_assignment_id",
                                ),
                            },
                        )
                        return
                    response(self, 200, task)
                    return
                fence_error = validate_task_mutation_fence(task, body)
                if fence_error:
                    response(self, 409, {
                        "error": "stale_or_invalid_lease",
                        "reason": fence_error,
                        "task_id": task_id,
                        "attempt_id": task.get("attempt_id"),
                    })
                    return
                assignment_error = validate_task_assignment_state(task)
                if assignment_error:
                    response(self, 409, {
                        "error": "stale_or_invalid_assignment",
                        "reason": assignment_error,
                        "task_id": task_id,
                        "attempt_id": task.get("attempt_id"),
                        "assignment_id": task.get("current_assignment_id"),
                    })
                    return
                if task.get("state") in TERMINAL_STATES:
                    response(self, 200, task)
                    return
                if task.get("state") not in TERMINAL_STATES:
                    requested_state = body.get("state")
                    if requested_state not in {None, "", STATE_RUNNING}:
                        response(self, 422, {
                            "error": "invalid_heartbeat_state",
                            "reason": "heartbeat_state_must_be_running",
                            "task_id": task_id,
                        })
                        return
                    previous = dict(task)
                    task["state"] = STATE_RUNNING
                    task["heartbeat_at"] = utc_now()
                    task["lease_until"] = now_ts() + LEASE_DURATION
                    task["pid"] = body.get("pid", task.get("pid"))
                    task["worktree"] = body.get("worktree", task.get("worktree"))
                    task["branch"] = body.get("branch", task.get("branch"))
                    task["log_paths"] = body.get("log_paths", task.get("log_paths"))
                    committed = commit_fenced_task_mutation(
                        previous,
                        task,
                        active=True,
                    )
                    if committed is None:
                        response(self, 409, {
                            "error": "stale_or_invalid_lease",
                            "reason": "stale_task_revision",
                            "task_id": task_id,
                            "attempt_id": previous.get("attempt_id"),
                        })
                        return
                    task = committed
                response(self, 200, task)
                return
            if path.startswith("/v1/tasks/") and path.endswith("/complete"):
                task_id = path.split("/")[3]
                bind_agent_control_identity(
                    self._agent_control_identity,
                    body,
                )
                task = load_task(task_id)
                if not task:
                    response(self, 404, {"error": "task_not_found", "task_id": task_id})
                    return
                if is_product_developer_task(task):
                    fence_error = validate_task_mutation_fence(task, body)
                    if fence_error:
                        response(self, 409, {
                            "error": "stale_or_invalid_lease",
                            "reason": fence_error,
                            "task_id": task_id,
                            "attempt_id": task.get("attempt_id"),
                        })
                        return
                    if task.get("state") in TERMINAL_STATES:
                        response(
                            self,
                            200,
                            {"task": task, "review_task": None},
                        )
                        return
                    assignment_error = validate_task_assignment_state(task)
                    if assignment_error:
                        response(self, 409, {
                            "error": "stale_or_invalid_assignment",
                            "reason": assignment_error,
                            "task_id": task_id,
                            "attempt_id": task.get("attempt_id"),
                            "assignment_id": task.get("assignment_id"),
                        })
                        return
                    result = body.get("result", body)
                    reject_unmaterialized_artifact_contract(
                        result,
                        task_id=task_id,
                    )
                    committed = commit_product_developer_terminal(
                        task,
                        body,
                        success=True,
                    )
                    if committed is None:
                        response(self, 409, {
                            "error": "stale_or_invalid_lease",
                            "reason": "stale_task_revision",
                            "task_id": task_id,
                            "attempt_id": task.get("attempt_id"),
                        })
                        return
                    response(
                        self,
                        200,
                        {"task": committed, "review_task": None},
                    )
                    return
                canonical_task = parse_declared_contract_v1(
                    task.get("envelope", {}),
                    "kolibri.task",
                    bound_id=task_id,
                )
                if canonical_task is not None:
                    result = body.get("result", body)
                    reject_unmaterialized_artifact_contract(
                        result,
                        task_id=task_id,
                    )
                    try:
                        committed = (
                            commit_canonical_execution_terminal_atomically(
                                task,
                                body,
                                success=True,
                            )
                        )
                    except DeclaredContractV1Error as exc:
                        reason = (
                            exc.violations[0].get("code")
                            if exc.violations
                            else exc.code
                        )
                        response(self, 409, {
                            "error": exc.code,
                            "reason": reason,
                            "task_id": task_id,
                            "attempt_id": task.get("attempt_id"),
                            "assignment_id": task.get(
                                "current_assignment_id",
                            ),
                        })
                        return
                    if committed is None:
                        response(self, 409, {
                            "error": "stale_or_invalid_lease",
                            "reason": "stale_task_revision",
                            "task_id": task_id,
                            "attempt_id": task.get("attempt_id"),
                        })
                        return
                    response(
                        self,
                        200,
                        {"task": committed, "review_task": None},
                    )
                    return
                fence_error = validate_task_mutation_fence(task, body)
                if fence_error:
                    response(self, 409, {
                        "error": "stale_or_invalid_lease",
                        "reason": fence_error,
                        "task_id": task_id,
                        "attempt_id": task.get("attempt_id"),
                    })
                    return
                assignment_error = validate_task_assignment_state(task)
                if assignment_error:
                    response(self, 409, {
                        "error": "stale_or_invalid_assignment",
                        "reason": assignment_error,
                        "task_id": task_id,
                        "attempt_id": task.get("attempt_id"),
                        "assignment_id": task.get("current_assignment_id"),
                    })
                    return
                if task.get("state") in TERMINAL_STATES:
                    response(self, 200, {"task": task, "review_task": None})
                    return
                result = body.get("result", body)
                reject_unmaterialized_artifact_contract(
                    result,
                    task_id=task_id,
                )
                previous = dict(task)
                needs_review = task.get("envelope", {}).get("create_review_on_complete")
                has_pr = bool(result.get("pull_request_url") or result.get("pr_url"))
                task["state"] = STATE_COMPLETED if (not needs_review or has_pr) else STATE_WAITING_REVIEW
                task["result"] = result
                task["result_reference"] = body.get("result_reference") or result.get("result_path")
                task["heartbeat_at"] = utc_now()
                task["lease_until"] = None
                preserve_terminal_lease_evidence(task)
                committed = commit_fenced_task_mutation(
                    previous,
                    task,
                    active=False,
                )
                if committed is None:
                    response(self, 409, {
                        "error": "stale_or_invalid_lease",
                        "reason": "stale_task_revision",
                        "task_id": task_id,
                        "attempt_id": previous.get("attempt_id"),
                    })
                    return
                task = committed
                if task.get("state") == STATE_COMPLETED:
                    mark_assignment_for_task_status(
                        task,
                        status="completed",
                        reason="task completed",
                    )
                # Truth gate: verify completion has evidence
                task = truth_gate_on_complete(task, result)
                save_task(task)
                review_task = create_review_task(task, result) if has_pr else None
                response(self, 200, {"task": task, "review_task": review_task})
                return
            if path.startswith("/v1/tasks/") and path.endswith("/annotate"):
                task_id = path.split("/")[3]
                task = load_task(task_id)
                if not task:
                    response(self, 404, {"error": "task_not_found", "task_id": task_id})
                    return
                reject_direct_canonical_task_mutation(
                    task,
                    route="/v1/tasks/{task_id}/annotate",
                )
                assignment_error = validate_task_assignment_state(task)
                if assignment_error:
                    response(self, 409, {
                        "error": "stale_or_invalid_assignment",
                        "reason": assignment_error,
                        "task_id": task_id,
                        "attempt_id": task.get("attempt_id"),
                        "assignment_id": task.get("current_assignment_id"),
                    })
                    return
                result = dict(task.get("result") or {})
                result_patch = body.get("result", body)
                if not isinstance(result_patch, dict):
                    raise DeclaredContractV1Error(
                        "invalid_contract",
                        [{"path": "/result", "code": "type"}],
                    )
                result.update(result_patch)
                reject_unmaterialized_artifact_contract(
                    result,
                    task_id=task_id,
                )
                task["result"] = result
                task["result_reference"] = body.get("result_reference") or result.get("result_path") or task.get("result_reference")
                task["heartbeat_at"] = utc_now()
                review_task = None
                if task.get("state") == STATE_WAITING_REVIEW and (result.get("pull_request_url") or result.get("pr_url")):
                    task["state"] = STATE_COMPLETED
                    preserve_terminal_lease_evidence(task)
                    save_task(task)
                    review_task = create_review_task(task, result)
                else:
                    save_task(task)
                if task.get("state") == STATE_COMPLETED:
                    mark_assignment_for_task_status(
                        task,
                        status="completed",
                        reason="task annotated to completion",
                    )
                response(self, 200, {"task": task, "review_task": review_task})
                return
            if path.startswith("/v1/tasks/") and path.endswith("/fail"):
                task_id = path.split("/")[3]
                bind_agent_control_identity(
                    self._agent_control_identity,
                    body,
                )
                task = load_task(task_id)
                if not task:
                    response(self, 404, {"error": "task_not_found", "task_id": task_id})
                    return
                if is_product_developer_task(task):
                    fence_error = validate_task_mutation_fence(task, body)
                    if fence_error:
                        response(self, 409, {
                            "error": "stale_or_invalid_lease",
                            "reason": fence_error,
                            "task_id": task_id,
                            "attempt_id": task.get("attempt_id"),
                        })
                        return
                    if task.get("state") in TERMINAL_STATES:
                        response(self, 200, task)
                        return
                    assignment_error = validate_task_assignment_state(task)
                    if assignment_error:
                        response(self, 409, {
                            "error": "stale_or_invalid_assignment",
                            "reason": assignment_error,
                            "task_id": task_id,
                            "attempt_id": task.get("attempt_id"),
                            "assignment_id": task.get("assignment_id"),
                        })
                        return
                    failed_result = body.get("result")
                    reject_unmaterialized_artifact_contract(
                        failed_result,
                        task_id=task_id,
                    )
                    committed = commit_product_developer_terminal(
                        task,
                        body,
                        success=False,
                    )
                    if committed is None:
                        response(self, 409, {
                            "error": "stale_or_invalid_lease",
                            "reason": "stale_task_revision",
                            "task_id": task_id,
                            "attempt_id": task.get("attempt_id"),
                        })
                        return
                    response(self, 200, committed)
                    return
                canonical_task = parse_declared_contract_v1(
                    task.get("envelope", {}),
                    "kolibri.task",
                    bound_id=task_id,
                )
                if canonical_task is not None:
                    failed_result = body.get("result")
                    reject_unmaterialized_artifact_contract(
                        failed_result,
                        task_id=task_id,
                    )
                    try:
                        committed = (
                            commit_canonical_execution_terminal_atomically(
                                task,
                                body,
                                success=False,
                            )
                        )
                    except DeclaredContractV1Error as exc:
                        reason = (
                            exc.violations[0].get("code")
                            if exc.violations
                            else exc.code
                        )
                        response(self, 409, {
                            "error": exc.code,
                            "reason": reason,
                            "task_id": task_id,
                            "attempt_id": task.get("attempt_id"),
                            "assignment_id": task.get(
                                "current_assignment_id",
                            ),
                        })
                        return
                    if committed is None:
                        response(self, 409, {
                            "error": "stale_or_invalid_lease",
                            "reason": "stale_task_revision",
                            "task_id": task_id,
                            "attempt_id": task.get("attempt_id"),
                        })
                        return
                    response(self, 200, committed)
                    return
                fence_error = validate_task_mutation_fence(task, body)
                if fence_error:
                    response(self, 409, {
                        "error": "stale_or_invalid_lease",
                        "reason": fence_error,
                        "task_id": task_id,
                        "attempt_id": task.get("attempt_id"),
                    })
                    return
                assignment_error = validate_task_assignment_state(task)
                if assignment_error:
                    response(self, 409, {
                        "error": "stale_or_invalid_assignment",
                        "reason": assignment_error,
                        "task_id": task_id,
                        "attempt_id": task.get("attempt_id"),
                        "assignment_id": task.get("current_assignment_id"),
                    })
                    return
                if task.get("state") in TERMINAL_STATES:
                    response(self, 200, task)
                    return
                error_type = body.get("error_type", "runtime_error")
                error = body.get("error", "")
                failed_result = body.get("result")
                reject_unmaterialized_artifact_contract(
                    failed_result,
                    task_id=task_id,
                )
                previous = dict(task)
                task["error_type"] = error_type
                task["error"] = error
                task["result"] = failed_result
                task["result_reference"] = body.get("result_reference")
                task["lease_until"] = None
                retry = (
                    int(task.get("attempt", 0))
                    < int(task.get("max_retries", MAX_RETRIES))
                    and body.get("retry", True)
                )
                if retry:
                    task["state"] = STATE_QUEUED
                else:
                    task["state"] = STATE_FAILED
                    preserve_terminal_lease_evidence(task)
                committed = commit_fenced_task_mutation(
                    previous,
                    task,
                    active=False,
                    enqueue_after=retry,
                )
                if committed is None:
                    response(self, 409, {
                        "error": "stale_or_invalid_lease",
                        "reason": "stale_task_revision",
                        "task_id": task_id,
                        "attempt_id": previous.get("attempt_id"),
                    })
                    return
                task = committed
                if task.get("state") == STATE_QUEUED:
                    mark_assignment_for_task_status(
                        task,
                        status="expired",
                        reason="task retry requested",
                    )
                elif task.get("state") == STATE_FAILED:
                    mark_assignment_for_task_status(
                        task,
                        status="superseded",
                        reason="task failed without retry",
                    )
                # Only the CAS winner may create truth/runner side effects.
                task = truth_gate_on_fail(task, error_type, error)
                mark_node_runner_failure(task, body)
                save_task(task)
                response(self, 200, task)
                return
            if path.startswith("/v1/tasks/") and path.endswith("/cancel"):
                task_id = path.split("/")[3]
                task = load_task(task_id)
                if not task:
                    response(self, 404, {"error": "task_not_found", "task_id": task_id})
                    return
                reject_direct_canonical_task_mutation(
                    task,
                    route="/v1/tasks/{task_id}/cancel",
                )
                if task.get("state") not in TERMINAL_STATES:
                    assignment_error = validate_task_assignment_state(task)
                    if assignment_error:
                        response(self, 409, {
                            "error": "stale_or_invalid_assignment",
                            "reason": assignment_error,
                            "task_id": task_id,
                            "attempt_id": task.get("attempt_id"),
                            "assignment_id": task.get("current_assignment_id"),
                        })
                        return
                remove_from_queue(task_id)
                task["state"] = STATE_CANCELLED
                task["cancel_requested_at"] = utc_now()
                task["lease_until"] = None
                preserve_terminal_lease_evidence(task)
                mark_assignment_for_task_status(
                    task,
                    status="superseded",
                    reason="task cancelled",
                )
                save_task(task)
                response(self, 200, task)
                return
            if path.startswith("/v1/agents/cancel/"):
                task_id = path.split("/", 4)[4]
                task = load_task(task_id)
                if not task:
                    response(self, 404, canonical_response_envelope(
                        status="blocked",
                        task_id=task_id,
                        route_used="/v1/agents/cancel",
                        blocked_reason="unknown",
                        repair_task={"kind": "verify_agent_task_id", "task_id": task_id},
                        next_action="verify task id before retrying cancellation",
                    ))
                    return
                reject_direct_canonical_task_mutation(
                    task,
                    route="/v1/agents/cancel/{task_id}",
                )
                if task.get("state") not in TERMINAL_STATES:
                    assignment_error = validate_task_assignment_state(task)
                    if assignment_error:
                        response(self, 409, {
                            "error": "stale_or_invalid_assignment",
                            "reason": assignment_error,
                            "task_id": task_id,
                            "attempt_id": task.get("attempt_id"),
                            "assignment_id": task.get("current_assignment_id"),
                        })
                        return
                remove_from_queue(task_id)
                task["state"] = STATE_CANCELLED
                task["cancel_requested_at"] = utc_now()
                task["lease_until"] = None
                mark_assignment_for_task_status(
                    task,
                    status="superseded",
                    reason="task cancelled",
                )
                save_task(task)
                response(self, 200, canonical_response_envelope(
                    status="completed",
                    task_id=task_id,
                    node=(task.get("lease_owner") or "home").split(":", 1)[0],
                    route_used="/v1/agents/cancel",
                    data={"task": task},
                    next_action="poll /v1/agents/status/{task_id} to confirm terminal state",
                ))
                return
            if path.endswith("/revoke") and path.startswith("/v1/agents/assignments/"):
                assignment_id = path.split("/", 4)[4].rsplit("/revoke", 1)[0]
                transport_context = (
                    logical_home_a2a_mutation_transport_context(
                        self,
                        body,
                        action=(
                            "a2a.agent_assignment.revoke:"
                            f"{assignment_id}"
                        ),
                        required_capability=(
                            "a2a.agent_assignment.revoke"
                        ),
                    )
                )
                assignment = load_assignment(assignment_id)
                if assignment is None:
                    response(self, 404, {"error": "assignment_not_found", "assignment_id": assignment_id})
                    return
                bind_assignment_transport(
                    assignment,
                    transport_context,
                    require_available_card=False,
                )
                revoke_reason = (
                    body.get("reason")
                    if isinstance(body, dict)
                    else None
                )
                if (
                    not isinstance(revoke_reason, str)
                    or not revoke_reason.strip()
                    or len(revoke_reason.strip()) > 2000
                ):
                    response(self, 422, {
                        "error": "invalid_assignment_revoke_reason",
                    })
                    return
                mark_assignment_by_id(
                    assignment_id,
                    status="revoked",
                    reason=revoke_reason.strip(),
                    audit_context=transport_context,
                )
                response(
                    self,
                    200,
                    load_assignment(assignment_id) or assignment,
                )
                return
            response(self, 404, {"error": "not_found", "path": path})
        except RequestBodyError as exc:
            response(self, exc.status, {
                "error": "invalid_request_body",
                "code": exc.code,
            })
        except AgentControlAuthError as exc:
            response(self, exc.status, {
                "error": "agent_control_unauthorized",
                "code": exc.code,
            })
        except A2AMutationControlError as exc:
            response(self, exc.status, exc.as_dict())
        except ProductGoalInitializeControlError as exc:
            response(self, exc.status, exc.as_dict())
        except ProductTextRunControlError as exc:
            response(self, exc.status, exc.as_dict())
        except GoalCommandError as exc:
            response(self, exc.status, exc.as_dict())
        except TaskGraphCommandError as exc:
            response(self, exc.status, exc.as_dict())
        except ProjectCaseControlError as exc:
            response(self, exc.status, exc.as_dict())
        except DeclaredContractV1Error as exc:
            response(self, 422, {
                "error": "contract_v1_rejected",
                "code": exc.code,
                "violations": exc.violations,
            })
        except Exception as exc:  # pragma: no cover - surfaced in runtime logs
            response(self, 500, {"error": "control_plane_error", "detail": str(exc)})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default=os.environ.get("FACTORY_BIND", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("FACTORY_PORT", "9101")))
    args = parser.parse_args()
    authority_card, _authority_card_raw = (
        ensure_logical_home_authority_agent_card_projection()
    )
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(json.dumps({
        "event": "factory_control_started",
        "bind": args.bind,
        "port": args.port,
        "namespace": NAMESPACE,
        "logical_home_authority_agent_card_id": (
            authority_card["agent_card_id"]
        ),
    }))
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
