"""
Kolibri Worker Service — Kolibri Node (10.99.0.6)

Worker node that registers with the Kolibri Organism cluster,
processes jobs from the distributed queue, and reports metrics.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import httpx
import asyncio
import json
import os
import subprocess
import socket
import time
import psutil
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

NODE_NAME = os.environ.get("KOLIBRI_NODE", "kolibri")
NODE_ROLE = os.environ.get("KOLIBRI_ROLE", "worker")
NODE_PORT = int(os.environ.get("KOLIBRI_PORT", "9001"))
GATEWAY_IP = os.environ.get("KOLIBRI_GATEWAY", "10.99.0.2")
GATEWAY_PORT = int(os.environ.get("KOLIBRI_GATEWAY_PORT", "9001"))
REDIS_HOST = os.environ.get("KOLIBRI_REDIS", "10.99.0.1")
REDIS_PORT = int(os.environ.get("KOLIBRI_REDIS_PORT", "6379"))

gateway_client: Optional[httpx.AsyncClient] = None


def get_vpn_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((GATEWAY_IP, 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"


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


async def register_with_gateway():
    info = {
        "ip": get_vpn_ip(),
        "port": NODE_PORT,
        "role": NODE_ROLE,
        "hostname": socket.gethostname(),
        "started_at": datetime.now().isoformat(),
    }
    try:
        resp = await gateway_client.post(
            f"http://{GATEWAY_IP}:{GATEWAY_PORT}/node/register",
            json={"node": NODE_NAME, "info": info},
            timeout=10.0,
        )
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


async def send_heartbeat():
    load = get_system_load()
    try:
        resp = await gateway_client.post(
            f"http://{GATEWAY_IP}:{GATEWAY_PORT}/node/heartbeat",
            json={"node": NODE_NAME, "load": load},
            timeout=10.0,
        )
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


async def heartbeat_loop():
    while True:
        try:
            await send_heartbeat()
        except Exception:
            pass
        await asyncio.sleep(15)


async def job_processor_loop():
    """Pull jobs from gateway queue and execute them."""
    while True:
        try:
            resp = await gateway_client.get(
                f"http://{GATEWAY_IP}:{GATEWAY_PORT}/jobs?status=pending&limit=1",
                timeout=10.0,
            )
            data = resp.json()
            jobs = data.get("jobs", [])
            if jobs:
                job = jobs[0]
                job_id = job.get("id")
                if job_id:
                    result = await execute_job(job)
                    await report_job_result(job_id, result)
        except Exception:
            pass
        await asyncio.sleep(2)


async def execute_job(job: dict) -> dict:
    payload = json.loads(job.get("payload", "{}")) if isinstance(job.get("payload"), str) else job.get("payload", {})
    task_type = job.get("type", "general")
    prompt = payload.get("prompt", payload.get("payload", ""))

    mimo_path = "/root/.mimocode/bin/mimo"
    cmd = f"{mimo_path} run --dangerously-skip-permissions --model mimo/mimo-auto '{prompt}'"

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        return {
            "status": "completed",
            "node": NODE_NAME,
            "output": result.stdout,
            "error": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "node": NODE_NAME, "error": "timeout"}
    except Exception as e:
        return {"status": "error", "node": NODE_NAME, "error": str(e)}


async def report_job_result(job_id: str, result: dict):
    try:
        await gateway_client.post(
            f"http://{GATEWAY_IP}:{GATEWAY_PORT}/job/{job_id}/complete",
            json=result,
            timeout=10.0,
        )
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global gateway_client
    gateway_client = httpx.AsyncClient()

    await register_with_gateway()
    asyncio.create_task(heartbeat_loop())
    asyncio.create_task(job_processor_loop())

    yield

    await gateway_client.aclose()


app = FastAPI(title="Kolibri Worker", version="1.0", lifespan=lifespan)


@app.get("/worker/health")
async def health():
    load = get_system_load()
    try:
        gateway_resp = await gateway_client.get(
            f"http://{GATEWAY_IP}:{GATEWAY_PORT}/health", timeout=5.0
        )
        gateway_ok = gateway_resp.status_code == 200
    except Exception:
        gateway_ok = False

    return {
        "status": "ok" if gateway_ok else "degraded",
        "node": NODE_NAME,
        "role": NODE_ROLE,
        "ip": get_vpn_ip(),
        "gateway": "connected" if gateway_ok else "disconnected",
        "load": load,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/worker/metrics")
async def metrics():
    load = get_system_load()
    return {
        "node": NODE_NAME,
        "role": NODE_ROLE,
        "metrics": load,
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/worker/task")
async def direct_task(task: dict):
    """Execute a task directly on this worker."""
    payload = task.get("payload", "")
    task_type = task.get("type", "general")
    prompt = payload if isinstance(payload, str) else payload.get("prompt", "")

    mimo_path = "/root/.mimocode/bin/mimo"
    cmd = f"{mimo_path} run --dangerously-skip-permissions --model mimo/mimo-auto '{prompt}'"

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        return {
            "status": "completed",
            "node": NODE_NAME,
            "output": result.stdout,
            "error": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "node": NODE_NAME, "error": "timeout"}
    except Exception as e:
        return {"status": "error", "node": NODE_NAME, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    print(f"🐝 Kolibri Worker: {NODE_NAME} ({NODE_ROLE}) on :{NODE_PORT}")
    print(f"   Gateway: {GATEWAY_IP}:{GATEWAY_PORT}")
    print(f"   Redis: {REDIS_HOST}:{REDIS_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=NODE_PORT)
