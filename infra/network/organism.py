"""
Kolibri Organism — Distributed Compute Layer

Components:
1. Redis State Store — shared state across all nodes
2. Job Queue — async task distribution with failover
3. Resource Manager — tracks RAM/CPU, auto-assigns tasks
4. Unified API — single endpoint for all operations
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import httpx
import asyncio
import json
import os
import socket
import time
import uuid
import pickle
import hashlib
import psutil
import urllib.parse
from datetime import datetime
from typing import Optional, Any
from contextlib import asynccontextmanager
from enum import Enum

# ── Config ──────────────────────────────────────────────────────────

NODE_NAME = os.environ.get("KOLIBRI_NODE", "unknown")
NODE_ROLE = os.environ.get("KOLIBRI_ROLE", "worker")
NODE_PORT = int(os.environ.get("KOLIBRI_PORT", "9001"))
GATEWAY_IP = os.environ.get("KOLIBRI_GATEWAY", "10.99.0.2")
REDIS_HOST = os.environ.get("KOLIBRI_REDIS", "10.99.0.1")
REDIS_PORT = int(os.environ.get("KOLIBRI_REDIS_PORT", "6379"))
VPN_SUBNET = "10.99.0.0/24"
CONTROL_PLANE_URL = os.environ.get(
    "KOLIBRI_CONTROL_PLANE_URL",
    os.environ.get("KOLIBRI_FACTORY_CONTROL_URL", "http://10.99.0.2:9101"),
).rstrip("/")
CONTROL_PLANE_HTTP_TIMEOUT = float(os.environ.get("KOLIBRI_CONTROL_PLANE_HTTP_TIMEOUT", "20"))
CONTROL_PLANE_POLL_INTERVAL = float(os.environ.get("KOLIBRI_CONTROL_PLANE_POLL_INTERVAL", "0.5"))


class ComputeRequest(BaseModel):
    type: str = Field(default="general", min_length=1, max_length=64)
    prompt: Any = None
    payload: Any = None
    target: str = Field(default="auto", min_length=1, max_length=128)
    wait: bool = True
    timeout: int = Field(default=300, ge=1, le=1800)
    idempotency_key: Optional[str] = Field(default=None, max_length=256)


class JobSubmitRequest(BaseModel):
    type: str = Field(default="general", min_length=1, max_length=64)
    payload: dict = Field(default_factory=dict)
    target: str = Field(default="auto", min_length=1, max_length=128)
    timeout: int = Field(default=300, ge=1, le=1800)
    retries: int = Field(default=3, ge=0, le=10)


class BroadcastRequest(BaseModel):
    message: str = Field(default="", max_length=4096)

# ── Redis Client (simple, no deps) ─────────────────────────────────

class RedisClient:
    """Minimal Redis client using raw sockets."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._sock = None

    def _connect(self):
        if self._sock:
            try:
                self._sock.ping()
                return
            except:
                self._sock.close()
                self._sock = None
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(5)
        self._sock.connect((self.host, self.port))

    def _command(self, *args) -> Any:
        self._connect()
        cmd = "*{}\r\n".format(len(args))
        for arg in args:
            arg = str(arg)
            cmd += "${}\r\n{}\r\n".format(len(arg), arg)
        self._sock.sendall(cmd.encode())
        return self._read_response()

    def _read_line(self) -> str:
        buf = b""
        while True:
            ch = self._sock.recv(1)
            if not ch:
                raise Exception("Connection closed")
            buf += ch
            if buf.endswith(b"\r\n"):
                return buf[:-2].decode()

    def _read_bytes(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise Exception("Connection closed")
            buf += chunk
        return buf

    def _read_response(self) -> Any:
        line = self._read_line()
        prefix = line[0]
        if prefix == "+":
            return line[1:]
        elif prefix == "-":
            raise Exception(line[1:])
        elif prefix == ":":
            return int(line[1:])
        elif prefix == "$":
            length = int(line[1:])
            if length == -1:
                return None
            data = self._read_bytes(length)
            self._read_line()  # consume trailing \r\n
            return data.decode()
        elif prefix == "*":
            count = int(line[1:])
            if count == -1:
                return None
            items = []
            for _ in range(count):
                items.append(self._read_response())
            return items
        return line

    def ping(self) -> bool:
        try:
            return self._command("PING") == "PONG"
        except:
            return False

    def set(self, key: str, value: str, ex: int = None) -> bool:
        if ex:
            return self._command("SET", key, value, "EX", ex) == "OK"
        return self._command("SET", key, value) == "OK"

    def get(self, key: str) -> Optional[str]:
        return self._command("GET", key)

    def delete(self, *keys: str) -> int:
        return self._command("DEL", *keys)

    def hset(self, name: str, key: str, value: str) -> int:
        return self._command("HSET", name, key, value)

    def hget(self, name: str, key: str) -> Optional[str]:
        return self._command("HGET", name, key)

    def hgetall(self, name: str) -> dict:
        result = self._command("HGETALL", name)
        if not result:
            return {}
        return {result[i]: result[i+1] for i in range(0, len(result), 2)}

    def hdel(self, name: str, *keys: str) -> int:
        return self._command("HDEL", name, *keys)

    def lpush(self, key: str, *values: str) -> int:
        return self._command("LPUSH", key, *values)

    def rpush(self, key: str, *values: str) -> int:
        return self._command("RPUSH", key, *values)

    def rpop(self, key: str) -> Optional[str]:
        return self._command("RPOP", key)

    def lrange(self, key: str, start: int, stop: int) -> list:
        result = self._command("LRANGE", key, start, stop)
        return result if isinstance(result, list) else [result] if result else []

    def llen(self, key: str) -> int:
        return self._command("LLEN", key)

    def incr(self, key: str) -> int:
        return self._command("INCR", key)

    def expire(self, key: str, seconds: int) -> bool:
        return self._command("EXPIRE", key, seconds) == "1"

    def keys(self, pattern: str = "*") -> list:
        result = self._command("KEYS", pattern)
        return result if isinstance(result, list) else [result] if result else []

# ── Job Queue ───────────────────────────────────────────────────────

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

class JobQueue:
    """Distributed job queue with failover."""

    def __init__(self, redis: RedisClient):
        self.redis = redis
        self.queue_key = "kolibri:jobs:pending"
        self.running_key = "kolibri:jobs:running"
        self.results_prefix = "kolibri:jobs:result:"
        self.nodes_prefix = "kolibri:nodes:"
        self.state_prefix = "kolibri:state:"

    def submit(self, task_type: str, payload: dict, target: str = "auto",
               timeout: int = 300, retries: int = 3) -> str:
        job_id = str(uuid.uuid4())[:8]
        job = {
            "id": job_id,
            "type": task_type,
            "payload": json.dumps(payload),
            "target": target,
            "timeout": timeout,
            "retries": retries,
            "attempts": 0,
            "status": JobStatus.PENDING,
            "created_at": datetime.now().isoformat(),
            "created_by": NODE_NAME,
        }
        self.redis.hset(f"{self.results_prefix}{job_id}", "status", JobStatus.PENDING)
        self.redis.hset(f"{self.results_prefix}{job_id}", "created_at", job["created_at"])
        self.redis.lpush(self.queue_key, json.dumps(job))
        return job_id

    def get_result(self, job_id: str) -> dict:
        result = self.redis.hgetall(f"{self.results_prefix}{job_id}")
        if not result:
            return {"status": "not_found"}
        return result

    def process_next(self) -> Optional[dict]:
        job_data = self.redis.rpop(self.queue_key)
        if not job_data:
            return None
        job = json.loads(job_data)
        job["status"] = JobStatus.RUNNING
        job["attempts"] += 1
        job["started_at"] = datetime.now().isoformat()
        job["assigned_to"] = NODE_NAME
        self.redis.hset(f"{self.results_prefix}{job['id']}", "status", JobStatus.RUNNING)
        self.redis.hset(f"{self.results_prefix}{job['id']}", "assigned_to", NODE_NAME)
        return job

    def complete(self, job_id: str, result: dict):
        self.redis.hset(f"{self.results_prefix}{job_id}", "status", JobStatus.COMPLETED)
        self.redis.hset(f"{self.results_prefix}{job_id}", "result", json.dumps(result))
        self.redis.hset(f"{self.results_prefix}{job_id}", "completed_at", datetime.now().isoformat())

    def fail(self, job_id: str, error: str, retry: bool = True):
        if retry:
            self.redis.hset(f"{self.results_prefix}{job_id}", "status", JobStatus.RETRYING)
        else:
            self.redis.hset(f"{self.results_prefix}{job_id}", "status", JobStatus.FAILED)
        self.redis.hset(f"{self.results_prefix}{job_id}", "error", error)

# ── Resource Manager ────────────────────────────────────────────────

class ResourceManager:
    """Tracks cluster resources and assigns tasks."""

    nodes_prefix = "kolibri:nodes:"
    state_prefix = "kolibri:state:"

    def __init__(self, redis: RedisClient):
        self.redis = redis

    def register_node(self, name: str, info: dict):
        self.redis.hset(f"{self.nodes_prefix}{name}", "info", json.dumps(info))
        self.redis.hset(f"{self.nodes_prefix}{name}", "last_seen", str(time.time()))
        self.redis.hset(f"{self.nodes_prefix}{name}", "status", "online")

    def heartbeat(self, name: str, load: dict):
        self.redis.hset(f"{self.nodes_prefix}{name}", "last_seen", str(time.time()))
        self.redis.hset(f"{self.nodes_prefix}{name}", "status", "online")
        self.redis.hset(f"{self.nodes_prefix}{name}", "load", json.dumps(load))

    def get_nodes(self) -> dict:
        nodes = {}
        for key in self.redis.keys(f"{self.nodes_prefix}*"):
            name = key.replace(self.nodes_prefix, "")
            info = self.redis.hgetall(key)
            if info:
                nodes[name] = {
                    "status": info.get("status", "unknown"),
                    "info": json.loads(info.get("info", "{}")),
                    "load": json.loads(info.get("load", "{}")),
                    "last_seen": float(info.get("last_seen", 0)),
                }
        return nodes

    def get_online_nodes(self) -> dict:
        now = time.time()
        return {
            name: n for name, n in self.get_nodes().items()
            if n["status"] == "online" and (now - n["last_seen"]) < 90
        }

    def select_best(self, task_type: str = "general") -> Optional[str]:
        role_map = {
            "training": "training",
            "inference": "inference",
            "rag": "rag",
            "agent": "agent",
            "frontend": "gateway",
        }
        target_role = role_map.get(task_type)
        online = self.get_online_nodes()

        candidates = {}
        if target_role:
            candidates = {name: n for name, n in online.items()
                         if n["info"].get("role") == target_role}
        if not candidates:
            candidates = online

        if not candidates:
            return None

        best = None
        best_score = -1
        for name, n in candidates.items():
            load = n.get("load", {})
            cpu = load.get("cpu_percent", 50)
            ram_free = load.get("ram_total_gb", 1) - load.get("ram_used_gb", 0)
            score = ram_free * 10 - cpu
            if score > best_score:
                best_score = score
                best = name
        return best

    def set_state(self, key: str, value: str):
        self.redis.set(f"{self.state_prefix}{key}", value)

    def get_state(self, key: str) -> Optional[str]:
        return self.redis.get(f"{self.state_prefix}{key}")

    def delete_state(self, key: str):
        self.redis.delete(f"{self.state_prefix}{key}")

# ── Globals ─────────────────────────────────────────────────────────

redis = None
queue = None
resources = None

# ── App ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis, queue, resources

    redis = RedisClient(REDIS_HOST, REDIS_PORT)
    queue = JobQueue(redis)
    resources = ResourceManager(redis)

    # Register self
    load = get_system_load()
    info = {
        "ip": get_vpn_ip(),
        "port": NODE_PORT,
        "role": NODE_ROLE,
        "hostname": socket.gethostname(),
        "started_at": datetime.now().isoformat(),
    }
    resources.register_node(NODE_NAME, info)
    resources.heartbeat(NODE_NAME, load)

    # Start background tasks
    asyncio.create_task(heartbeat_loop())
    asyncio.create_task(job_processor_loop())

    yield


async def heartbeat_loop():
    while True:
        try:
            load = get_system_load()
            resources.heartbeat(NODE_NAME, load)
        except Exception:
            pass
        await asyncio.sleep(15)


async def job_processor_loop():
    """Process jobs from the queue."""
    while True:
        try:
            job = queue.process_next()
            if job:
                result = await delegate_job_to_control_plane(job)
                if result.get("status") in {"completed", "submitted"}:
                    queue.complete(job["id"], result)
                else:
                    queue.fail(job["id"], result.get("error", "unknown"), retry=job["attempts"] < job["retries"])
        except Exception as e:
            pass
        await asyncio.sleep(0.5)


async def delegate_job_to_control_plane(job: dict) -> dict:
    task_type = job.get("type", "general")
    payload = json.loads(job.get("payload", "{}"))
    target = job.get("target", "auto")
    timeout = int(job.get("timeout", 300))
    return await submit_control_plane_task(task_type, payload, target, timeout, wait=False, idempotency_key=job.get("id"))


def request_token(explicit: str | None = None) -> str:
    raw = explicit or uuid.uuid4().hex
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_control_plane_envelope(
    task_type: str,
    payload: dict,
    target: str,
    timeout: int,
    idempotency_key: str | None = None,
) -> dict:
    prompt = payload.get("prompt", payload.get("payload", ""))
    if not isinstance(prompt, str):
        prompt = json.dumps(prompt, ensure_ascii=False)
    token = request_token(idempotency_key)
    task_id = f"MESH-{NODE_NAME}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{token}"
    envelope = {
        "task_id": task_id,
        "idempotency_key": f"mesh:{NODE_NAME}:{token}",
        "kind": "owner_remote_task",
        "required_capability": "generic_implementation",
        "max_retries": 1,
        "objective": prompt,
        "mesh": {
            "task_type": task_type,
            "source_node": NODE_NAME,
            "requested_target": target,
            "timeout": timeout,
        },
        "source": {
            "kind": "mesh-api",
            "node": NODE_NAME,
            "accepted_at": datetime.now().isoformat(),
        },
    }
    if target not in {"", "auto"}:
        envelope["target_node"] = NODE_NAME if target == "local" else target
    return envelope


async def submit_control_plane_task(
    task_type: str,
    payload: dict,
    target: str,
    timeout: int,
    wait: bool,
    idempotency_key: str | None = None,
) -> dict:
    envelope = build_control_plane_envelope(task_type, payload, target, timeout, idempotency_key)
    try:
        async with httpx.AsyncClient(timeout=CONTROL_PLANE_HTTP_TIMEOUT) as client:
            created = await client.post(f"{CONTROL_PLANE_URL}/v1/tasks", json=envelope)
            created.raise_for_status()
            task = created.json()
            task_id = task.get("task_id") or envelope["task_id"]
            if not wait:
                return {
                    "status": "submitted",
                    "transport": "control-plane",
                    "node": NODE_NAME,
                    "control_plane_task_id": task_id,
                }

            deadline = time.time() + timeout
            quoted_task_id = urllib.parse.quote(task_id, safe="")
            while time.time() < deadline:
                current = await client.get(f"{CONTROL_PLANE_URL}/v1/tasks/{quoted_task_id}")
                current.raise_for_status()
                state = current.json()
                if state.get("state") == "completed":
                    return {
                        "status": "completed",
                        "transport": "control-plane",
                        "node": NODE_NAME,
                        "control_plane_task_id": task_id,
                        "result": state.get("result"),
                    }
                if state.get("state") in {"failed", "dead_letter", "cancelled"}:
                    return {
                        "status": "failed",
                        "transport": "control-plane",
                        "node": NODE_NAME,
                        "control_plane_task_id": task_id,
                        "error": state.get("error") or state.get("error_type") or state.get("state"),
                    }
                await asyncio.sleep(CONTROL_PLANE_POLL_INTERVAL)
            return {
                "status": "timeout",
                "transport": "control-plane",
                "node": NODE_NAME,
                "control_plane_task_id": task_id,
            }
    except Exception as e:
        return {"status": "error", "transport": "control-plane", "node": NODE_NAME, "error": str(e)}


async def get_control_plane_filesystem() -> Any:
    try:
        async with httpx.AsyncClient(timeout=CONTROL_PLANE_HTTP_TIMEOUT) as client:
            response = await client.get(f"{CONTROL_PLANE_URL}/v1/filesystem")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail="control plane filesystem request failed",
        ) from e
    except ValueError as e:
        raise HTTPException(status_code=502, detail="control plane filesystem response is not JSON") from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"control plane filesystem unavailable: {e}") from e


def get_system_load() -> dict:
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu_percent": round(cpu, 1),
        "ram_percent": round(mem.percent, 1),
        "ram_used_gb": round(mem.used / (1024**3), 2),
        "ram_total_gb": round(mem.total / (1024**3), 2),
        "disk_percent": round(disk.percent, 1),
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "load_avg": list(os.getloadavg()),
    }


def get_vpn_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.99.0.2", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "0.0.0.0"


# ── FastAPI ─────────────────────────────────────────────────────────

app = FastAPI(title="Kolibri Organism", version="3.0", lifespan=lifespan)


# ── Health ──────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    redis_ok = redis.ping() if redis else False
    return {
        "status": "ok" if redis_ok else "degraded",
        "node": NODE_NAME,
        "role": NODE_ROLE,
        "ip": get_vpn_ip(),
        "redis": "connected" if redis_ok else "disconnected",
        "load": get_system_load(),
        "timestamp": datetime.now().isoformat(),
    }


# ── Cluster Status ─────────────────────────────────────────────────

@app.get("/cluster/status")
async def cluster_status():
    nodes = resources.get_online_nodes()
    total_ram = sum(n["load"].get("ram_total_gb", 0) for n in nodes.values())
    used_ram = sum(n["load"].get("ram_used_gb", 0) for n in nodes.values())
    avg_cpu = sum(n["load"].get("cpu_percent", 0) for n in nodes.values()) / max(len(nodes), 1)

    return {
        "cluster": "Kolibri Organism",
        "subnet": VPN_SUBNET,
        "total_nodes": len(resources.get_nodes()),
        "online_nodes": len(nodes),
        "total_ram_gb": round(total_ram, 2),
        "used_ram_gb": round(used_ram, 2),
        "free_ram_gb": round(total_ram - used_ram, 2),
        "avg_cpu_percent": round(avg_cpu, 1),
        "nodes": {
            name: {
                "role": n["info"].get("role"),
                "ip": n["info"].get("ip"),
                "cpu": n["load"].get("cpu_percent", "?"),
                "ram": f"{n['load'].get('ram_used_gb', '?')}/{n['load'].get('ram_total_gb', '?')} GB",
            }
            for name, n in nodes.items()
        }
    }


# ── Job Queue ───────────────────────────────────────────────────────

@app.post("/job/submit")
async def submit_job(job: JobSubmitRequest):
    job_id = queue.submit(job.type, job.payload, job.target, job.timeout, job.retries)
    return {"job_id": job_id, "status": "submitted"}


@app.get("/job/{job_id}")
async def get_job(job_id: str):
    result = queue.get_result(job_id)
    return result


@app.get("/job/{job_id}/wait")
async def wait_job(job_id: str, timeout: int = 60):
    start = time.time()
    while time.time() - start < timeout:
        result = queue.get_result(job_id)
        if result.get("status") in ("completed", "failed"):
            return result
        await asyncio.sleep(0.5)
    return {"status": "timeout", "job_id": job_id}


@app.post("/job/{job_id}/cancel")
async def cancel_job(job_id: str):
    queue.redis.hset(f"{queue.results_prefix}{job_id}", "status", "cancelled")
    return {"status": "cancelled", "job_id": job_id}


@app.get("/jobs")
async def list_jobs(status: str = "all", limit: int = 50):
    keys = queue.redis.keys(f"{queue.results_prefix}*")
    jobs = []
    for key in keys[:limit]:
        job_id = key.replace(queue.results_prefix, "")
        result = queue.get_result(job_id)
        if status == "all" or result.get("status") == status:
            result["id"] = job_id
            jobs.append(result)
    return {"jobs": jobs, "count": len(jobs)}


# ── State Store ─────────────────────────────────────────────────────

@app.post("/state/set")
async def set_state(data: dict):
    key = data.get("key")
    value = data.get("value")
    ttl = data.get("ttl")
    if not key or value is None:
        raise HTTPException(400, "key and value required")
    resources.set_state(key, value)
    if ttl:
        redis.expire(f"kolibri:state:{key}", ttl)
    return {"status": "ok", "key": key}


@app.get("/state/{key}")
async def get_state(key: str):
    value = resources.get_state(key)
    if value is None:
        raise HTTPException(404, "key not found")
    return {"key": key, "value": value}


@app.delete("/state/{key}")
async def delete_state(key: str):
    resources.delete_state(key)
    return {"status": "deleted", "key": key}


@app.get("/state")
async def list_state(pattern: str = "*"):
    keys = redis.keys(f"kolibri:state:{pattern}")
    result = {}
    for key in keys:
        short_key = key.replace("kolibri:state:", "")
        result[short_key] = redis.get(key)
    return {"state": result, "count": len(result)}


# ── Node Management ────────────────────────────────────────────────

@app.post("/node/register")
async def register_node(data: dict):
    name = data.get("node")
    info = data.get("info", {})
    if not name:
        raise HTTPException(400, "node name required")
    resources.register_node(name, info)
    return {"status": "registered", "node": name}


@app.post("/node/heartbeat")
async def node_heartbeat(data: dict):
    name = data.get("node")
    load = data.get("load", {})
    if name:
        resources.heartbeat(name, load)
    return {"status": "ok"}


@app.get("/nodes")
async def list_nodes():
    return {"nodes": resources.get_nodes()}


@app.get("/nodes/online")
async def list_online():
    return {"nodes": resources.get_online_nodes()}


# ── Unified Filesystem Namespace ───────────────────────────────────

@app.get("/filesystem")
async def filesystem_namespace():
    """Return the factory filesystem namespace through mesh API."""
    return await get_control_plane_filesystem()


@app.get("/mesh/filesystem")
async def mesh_filesystem_namespace():
    """Alias for clients that call mesh-scoped endpoints explicitly."""
    return await get_control_plane_filesystem()


# ── Unified Compute ────────────────────────────────────────────────

@app.post("/compute")
async def compute(task: ComputeRequest):
    """Submit compute work to the Factory Control Plane."""
    prompt = task.prompt if task.prompt is not None else task.payload

    return await submit_control_plane_task(
        task.type,
        {"prompt": prompt},
        task.target,
        task.timeout,
        wait=task.wait,
        idempotency_key=task.idempotency_key,
    )


# ── Broadcast ───────────────────────────────────────────────────────

@app.post("/broadcast")
async def broadcast(data: BroadcastRequest):
    """Publish a cluster message without remote command execution."""
    online = resources.get_online_nodes()
    event_id = f"broadcast:{datetime.now().strftime('%Y%m%d%H%M%S')}:{uuid.uuid4().hex[:8]}"
    resources.set_state(event_id, json.dumps({
        "message": data.message,
        "source_node": NODE_NAME,
        "recipients": sorted(online.keys()),
        "created_at": datetime.now().isoformat(),
    }, ensure_ascii=False))
    return {"status": "published", "event_id": event_id, "recipients": sorted(online.keys())}


# ── Entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"🐝 Kolibri Organism: {NODE_NAME} ({NODE_ROLE}) on :{NODE_PORT}")
    print(f"   Redis: {REDIS_HOST}:{REDIS_PORT}")
    print(f"   Gateway: {GATEWAY_IP}")
    uvicorn.run(app, host="0.0.0.0", port=NODE_PORT)
