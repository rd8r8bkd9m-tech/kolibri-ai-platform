"""
Kolibri Organism — Distributed Compute Layer

Components:
1. Redis State Store — shared state across all nodes
2. Job Queue — async task distribution with failover
3. Resource Manager — tracks RAM/CPU, auto-assigns tasks
4. Unified API — single endpoint for all operations
"""

from fastapi import FastAPI, HTTPException
import httpx
import asyncio
import json
import os
import subprocess
import socket
import time
import uuid
import psutil
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
MIMO_MODEL = os.environ.get("KOLIBRI_MIMO_MODEL", "mimo/mimo-auto")
MIMO_TIMEOUT = int(os.environ.get("KOLIBRI_MIMO_TIMEOUT", "300"))

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
            except Exception:
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
        except Exception:
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
        self.redis.hset(f"{self.results_prefix}{job_id}", "id", job_id)
        self.redis.hset(f"{self.results_prefix}{job_id}", "type", task_type)
        self.redis.hset(f"{self.results_prefix}{job_id}", "payload", job["payload"])
        self.redis.hset(f"{self.results_prefix}{job_id}", "target", target)
        self.redis.hset(f"{self.results_prefix}{job_id}", "timeout", str(timeout))
        self.redis.hset(f"{self.results_prefix}{job_id}", "retries", str(retries))
        self.redis.hset(f"{self.results_prefix}{job_id}", "attempts", "0")
        self.redis.lpush(self.queue_key, json.dumps(job))
        return job_id

    def get_result(self, job_id: str) -> dict:
        result = self.redis.hgetall(f"{self.results_prefix}{job_id}")
        if not result:
            return {"status": "not_found"}
        return result

    def process_next(self, assigned_to: Optional[str] = None) -> Optional[dict]:
        job_data = self.redis.rpop(self.queue_key)
        if not job_data:
            return None
        worker = assigned_to or NODE_NAME
        job = json.loads(job_data)
        job["status"] = JobStatus.RUNNING
        job["attempts"] += 1
        job["started_at"] = datetime.now().isoformat()
        job["assigned_to"] = worker
        self.redis.hset(f"{self.results_prefix}{job['id']}", "status", JobStatus.RUNNING)
        self.redis.hset(f"{self.results_prefix}{job['id']}", "assigned_to", worker)
        self.redis.hset(f"{self.results_prefix}{job['id']}", "attempts", str(job["attempts"]))
        self.redis.hset(f"{self.results_prefix}{job['id']}", "started_at", job["started_at"])
        return job

    def complete(self, job_id: str, result: dict):
        self.redis.hset(f"{self.results_prefix}{job_id}", "status", JobStatus.COMPLETED)
        self.redis.hset(f"{self.results_prefix}{job_id}", "result", json.dumps(result))
        self.redis.hset(f"{self.results_prefix}{job_id}", "completed_at", datetime.now().isoformat())
        self.redis.hdel(f"{self.results_prefix}{job_id}", "error")

    def fail(self, job_id: str, error: str, retry: bool = True):
        result_key = f"{self.results_prefix}{job_id}"
        existing = self.redis.hgetall(result_key)
        attempts = int(existing.get("attempts", 0) or 0)
        retries = int(existing.get("retries", 0) or 0)

        if retry and attempts < retries:
            self.redis.hset(f"{self.results_prefix}{job_id}", "status", JobStatus.RETRYING)
            job = {
                "id": job_id,
                "type": existing.get("type", "general"),
                "payload": existing.get("payload", "{}"),
                "target": existing.get("target", "auto"),
                "timeout": int(existing.get("timeout", 300) or 300),
                "retries": retries,
                "attempts": attempts,
                "status": JobStatus.PENDING,
                "created_at": existing.get("created_at", datetime.now().isoformat()),
                "created_by": existing.get("created_by", NODE_NAME),
            }
            self.redis.lpush(self.queue_key, json.dumps(job))
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


def get_mimo_path() -> str:
    return "/usr/local/bin/mimo" if NODE_NAME == "home" else "/root/.mimocode/bin/mimo"


def normalize_payload(payload: Any) -> dict:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {"prompt": payload}
    return {"payload": str(payload)}


def extract_prompt(payload: Any) -> str:
    normalized = normalize_payload(payload)
    prompt = normalized.get("prompt", normalized.get("payload", ""))
    if isinstance(prompt, (dict, list)):
        return json.dumps(prompt, ensure_ascii=False)
    return str(prompt)


def summarize_output(stdout: str, stderr: str) -> str:
    text = (stdout or stderr or "").strip()
    if not text:
        return "No output"
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:240]
    return "No output"


def structured_task_result(
    status: str,
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: Optional[int] = None,
    error: Optional[str] = None,
) -> dict:
    result = {
        "status": status,
        "node": NODE_NAME,
        "summary": error or summarize_output(stdout, stderr),
        "output": stdout,
        "error": error or stderr,
        "changed_files": [],
        "checks": [],
        "risks": [] if status == "completed" else [error or stderr or "task_failed"],
        "artifacts": [],
        "completed_at": datetime.now().isoformat(),
    }
    if returncode is not None:
        result["returncode"] = returncode
    return result


async def run_mimo_prompt(prompt: str, timeout: int = MIMO_TIMEOUT) -> dict:
    if not prompt.strip():
        return structured_task_result("error", error="empty prompt")

    args = [
        get_mimo_path(),
        "run",
        "--format",
        "json",
        "--model",
        MIMO_MODEL,
        prompt,
    ]

    try:
        result = subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        status = "completed" if result.returncode == 0 else "error"
        return structured_task_result(
            status,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )
    except subprocess.TimeoutExpired as exc:
        return structured_task_result(
            "timeout",
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            error="timeout",
        )
    except FileNotFoundError:
        return structured_task_result("error", error=f"Mimo binary not found: {get_mimo_path()}")
    except Exception as e:
        return structured_task_result("error", error=str(e))

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
                result = await execute_job(job)
                if result.get("status") == "completed":
                    queue.complete(job["id"], result)
                else:
                    queue.fail(job["id"], result.get("error", "unknown"), retry=job["attempts"] < job["retries"])
        except Exception:
            pass
        await asyncio.sleep(0.5)


async def execute_job(job: dict) -> dict:
    task_type = job.get("type", "general")
    payload = json.loads(job.get("payload", "{}"))
    target = job.get("target", "auto")

    if target == "local" or target == NODE_NAME:
        return await run_locally(task_type, payload)

    if target == "auto":
        best = resources.select_best(task_type)
        if best and best != NODE_NAME:
            return await dispatch_to(best, task_type, payload)
        return await run_locally(task_type, payload)

    return await dispatch_to(target, task_type, payload)


async def dispatch_to(node: str, task_type: str, payload: dict) -> dict:
    nodes = resources.get_online_nodes()
    if node not in nodes:
        return {"status": "error", "error": f"Node {node} offline"}

    info = nodes[node]["info"]
    ip = info.get("ip")
    port = info.get("port", 9001)

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(
                f"http://{ip}:{port}/task/execute",
                json={"payload": json.dumps(payload), "type": task_type}
            )
            return r.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def run_locally(task_type: str, payload: dict) -> dict:
    timeout = int(payload.get("timeout", MIMO_TIMEOUT)) if isinstance(payload, dict) else MIMO_TIMEOUT
    return await run_mimo_prompt(extract_prompt(payload), timeout=timeout)


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
    except Exception:
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
async def submit_job(job: dict):
    task_type = job.get("type", "general")
    payload = job.get("payload", {})
    target = job.get("target", "auto")
    timeout = job.get("timeout", 300)
    retries = job.get("retries", 3)

    job_id = queue.submit(task_type, payload, target, timeout, retries)
    return {"job_id": job_id, "status": "submitted"}


@app.get("/job/{job_id}")
async def get_job(job_id: str):
    result = queue.get_result(job_id)
    return result


@app.post("/job/claim")
async def claim_job(data: dict = None):
    """Atomically claim one pending job for a worker node."""
    data = data or {}
    assigned_to = data.get("node") or NODE_NAME
    job = queue.process_next(assigned_to=assigned_to)
    if not job:
        return {"status": "empty", "job": None}
    return {"status": "claimed", "job": job}


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


@app.post("/job/{job_id}/complete")
async def complete_job(job_id: str, result: dict):
    """Accept structured task results from worker nodes."""
    status = result.get("status", "error")
    if status == "completed":
        queue.complete(job_id, result)
    else:
        queue.fail(job_id, result.get("error") or result.get("summary") or "worker_failed", retry=True)
        queue.redis.hset(f"{queue.results_prefix}{job_id}", "result", json.dumps(result))
        queue.redis.hset(f"{queue.results_prefix}{job_id}", "completed_at", datetime.now().isoformat())
    return {"status": "recorded", "job_id": job_id, "result_status": status}


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


# ── Unified Compute ────────────────────────────────────────────────

@app.post("/compute")
async def compute(task: dict):
    """Unified compute endpoint — submit any task, auto-routed to best node."""
    task_type = task.get("type", "general")
    prompt = task.get("prompt", task.get("payload", ""))
    target = task.get("target", "auto")
    wait = task.get("wait", True)
    timeout = task.get("timeout", 300)

    job_id = queue.submit(task_type, {"prompt": prompt}, target, timeout)

    if wait:
        result = await wait_job(job_id, timeout)
        return {"job_id": job_id, **result}
    else:
        return {"job_id": job_id, "status": "submitted"}


@app.post("/task/execute")
async def execute_task(task: dict):
    """Execute task directly on this node."""
    payload = task.get("payload", "")
    timeout = int(task.get("timeout", MIMO_TIMEOUT))
    return await run_mimo_prompt(extract_prompt(payload), timeout=timeout)


# ── Broadcast ───────────────────────────────────────────────────────

@app.post("/broadcast")
async def broadcast(data: dict):
    """Send message to all nodes."""
    message = data.get("message", "")
    results = {}
    online = resources.get_online_nodes()

    for name, node in online.items():
        if name == NODE_NAME:
            results[name] = "self"
            continue
        info = node["info"]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"http://{info['ip']}:{info['port']}/task/execute",
                    json={"payload": f"echo: {message}", "type": "broadcast"}
                )
                results[name] = "sent"
        except Exception:
            results[name] = "failed"

    return {"results": results}


# ── Entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"🐝 Kolibri Organism: {NODE_NAME} ({NODE_ROLE}) on :{NODE_PORT}")
    print(f"   Redis: {REDIS_HOST}:{REDIS_PORT}")
    print(f"   Gateway: {GATEWAY_IP}")
    uvicorn.run(app, host="0.0.0.0", port=NODE_PORT)
