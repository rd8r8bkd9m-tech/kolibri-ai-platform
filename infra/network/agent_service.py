"""
Kolibri Agent Service — Sandboxed code execution, planning, and tool calling.

Endpoints:
- POST /agent/execute — execute code in a sandboxed subprocess
- POST /agent/plan   — break down complex tasks into steps
- POST /agent/tools  — register and call custom tools
- POST /agent/run    — full agent loop (plan → execute → observe → repeat)
- POST /agent/chat   — conversational agent interface (called by pipeline)
- GET  /agent/status — current agent state and running tasks
- GET  /agent/health — health check
"""

import asyncio
import hashlib
import json
import os
import resource
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ── Config ──────────────────────────────────────────────────────────

SERVICE_PORT = int(os.environ.get("KOLIBRI_AGENT_PORT", "8003"))
INFERENCE_URL = os.environ.get("KOLIBRI_INFERENCE_URL", "http://10.99.0.5:8001")
MAX_TIMEOUT = 30
MAX_MEMORY_MB = 256
MAX_HISTORY = 200
MAX_CONCURRENT = 5


# ── Models ──────────────────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    code: str
    language: str = "python"
    timeout: int = MAX_TIMEOUT
    env: Optional[Dict[str, str]] = None
    workdir: Optional[str] = None


class PlanRequest(BaseModel):
    task: str
    context: Optional[str] = None
    max_steps: int = 10


class ToolRegistration(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: str  # "builtin" or "http"
    endpoint: Optional[str] = None


class ToolCall(BaseModel):
    name: str
    arguments: Dict[str, Any]


class RunRequest(BaseModel):
    task: str
    max_iterations: int = 5
    conversation: Optional[List[Dict[str, str]]] = None
    tools: Optional[List[str]] = None


class ChatRequest(BaseModel):
    message: str
    conversation: Optional[List[Dict[str, str]]] = None
    stream: bool = False


# ── Execution Status ────────────────────────────────────────────────

class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


# ── Sandboxed Executor ──────────────────────────────────────────────

class SandboxExecutor:
    """Execute code in sandboxed subprocess with resource limits."""

    def __init__(self):
        self._running: Dict[str, asyncio.subprocess.Process] = {}
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def execute(self, code: str, language: str = "python",
                      timeout: int = MAX_TIMEOUT, env: Optional[Dict[str, str]] = None,
                      workdir: Optional[str] = None) -> Dict[str, Any]:
        task_id = str(uuid.uuid4())[:8]
        start = time.time()

        async with self._semaphore:
            try:
                if language == "python":
                    result = await self._exec_python(task_id, code, timeout, env, workdir)
                elif language in ("sh", "shell", "bash"):
                    result = await self._exec_shell(task_id, code, timeout, env, workdir)
                else:
                    return {
                        "task_id": task_id,
                        "status": TaskStatus.FAILED,
                        "error": f"Unsupported language: {language}",
                        "latency_ms": int((time.time() - start) * 1000),
                    }
                result["latency_ms"] = int((time.time() - start) * 1000)
                return result
            except Exception as e:
                return {
                    "task_id": task_id,
                    "status": TaskStatus.FAILED,
                    "error": str(e),
                    "latency_ms": int((time.time() - start) * 1000),
                }

    def _build_limits(self):
        mem_bytes = MAX_MEMORY_MB * 1024 * 1024
        return {
            resource.RLIMIT_AS: (mem_bytes, mem_bytes),
            resource.RLIMIT_CPU: (MAX_TIMEOUT, MAX_TIMEOUT),
            resource.RLIMIT_FSIZE: (50 * 1024 * 1024, 50 * 1024 * 1024),
            resource.RLIMIT_NPROC: (64, 64),
        }

    async def _exec_python(self, task_id: str, code: str, timeout: int,
                           env: Optional[Dict[str, str]], workdir: Optional[str]) -> Dict[str, Any]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            script_path = f.name

        try:
            proc_env = {**os.environ, **(env or {})}
            proc_env["PYTHONUNBUFFERED"] = "1"

            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-u", script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=proc_env,
                cwd=workdir or tempfile.gettempdir(),
                preexec_fn=self._apply_limits,
            )
            self._running[task_id] = proc

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                exit_code = proc.returncode
                status = TaskStatus.COMPLETED if exit_code == 0 else TaskStatus.FAILED
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return {
                    "task_id": task_id,
                    "status": TaskStatus.TIMEOUT,
                    "error": f"Execution timed out after {timeout}s",
                    "stdout": "",
                    "stderr": "",
                    "exit_code": -1,
                }
            finally:
                self._running.pop(task_id, None)

            return {
                "task_id": task_id,
                "status": status,
                "stdout": stdout.decode(errors="replace")[:65536],
                "stderr": stderr.decode(errors="replace")[:16384],
                "exit_code": exit_code,
            }
        finally:
            os.unlink(script_path)

    async def _exec_shell(self, task_id: str, code: str, timeout: int,
                          env: Optional[Dict[str, str]], workdir: Optional[str]) -> Dict[str, Any]:
        proc_env = {**os.environ, **(env or {})}

        proc = await asyncio.create_subprocess_shell(
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=proc_env,
            cwd=workdir or tempfile.gettempdir(),
            preexec_fn=self._apply_limits,
        )
        self._running[task_id] = proc

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            exit_code = proc.returncode
            status = TaskStatus.COMPLETED if exit_code == 0 else TaskStatus.FAILED
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "task_id": task_id,
                "status": TaskStatus.TIMEOUT,
                "error": f"Execution timed out after {timeout}s",
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
            }
        finally:
            self._running.pop(task_id, None)

        return {
            "task_id": task_id,
            "status": status,
            "stdout": stdout.decode(errors="replace")[:65536],
            "stderr": stderr.decode(errors="replace")[:16384],
            "exit_code": exit_code,
        }

    def _apply_limits(self):
        try:
            for res, (soft, hard) in self._build_limits().items():
                resource.setrlimit(res, (soft, hard))
        except (ValueError, OSError):
            pass

    async def cancel(self, task_id: str) -> bool:
        proc = self._running.get(task_id)
        if proc and proc.returncode is None:
            proc.kill()
            return True
        return False

    @property
    def active_count(self) -> int:
        return len(self._running)

    @property
    def active_tasks(self) -> List[str]:
        return list(self._running.keys())


# ── Tool Registry ───────────────────────────────────────────────────

class ToolRegistry:
    """Register and manage callable tools."""

    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._http_client = httpx.AsyncClient(timeout=30.0)
        self._register_builtins()

    def _register_builtins(self):
        self.register("shell", "Execute a shell command", {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 15},
            },
            "required": ["command"],
        }, handler="builtin")

        self.register("file_read", "Read a file's contents", {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read"},
                "max_bytes": {"type": "integer", "description": "Max bytes to read", "default": 1048576},
            },
            "required": ["path"],
        }, handler="builtin")

        self.register("file_write", "Write content to a file", {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"},
                "mode": {"type": "string", "description": "Write mode: overwrite or append", "default": "overwrite"},
            },
            "required": ["path", "content"],
        }, handler="builtin")

        self.register("http_request", "Make an HTTP request", {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to request"},
                "method": {"type": "string", "description": "HTTP method", "default": "GET"},
                "headers": {"type": "object", "description": "Request headers"},
                "body": {"type": "string", "description": "Request body"},
            },
            "required": ["url"],
        }, handler="builtin")

        self.register("python_exec", "Execute Python code and return output", {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 15},
            },
            "required": ["code"],
        }, handler="builtin")

    def register(self, name: str, description: str, parameters: Dict[str, Any],
                 handler: str = "builtin", endpoint: Optional[str] = None):
        self._tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "handler": handler,
            "endpoint": endpoint,
            "registered_at": datetime.now().isoformat(),
        }

    def unregister(self, name: str) -> bool:
        if name in self._tools and self._tools[name]["handler"] != "builtin":
            del self._tools[name]
            return True
        return False

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {"name": t["name"], "description": t["description"],
             "parameters": t["parameters"], "handler": t["handler"]}
            for t in self._tools.values()
        ]

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        return self._tools.get(name)

    async def call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Tool '{name}' not found"}

        if tool["handler"] == "builtin":
            return await self._call_builtin(name, arguments)
        elif tool["handler"] == "http" and tool.get("endpoint"):
            return await self._call_http(tool["endpoint"], arguments)
        else:
            return {"error": f"Unknown handler type: {tool['handler']}"}

    async def _call_builtin(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        executor = SandboxExecutor()

        if name == "shell":
            result = await executor.execute(args["command"], "shell", args.get("timeout", 15))
            return {"output": result.get("stdout", ""), "error": result.get("stderr", ""),
                    "exit_code": result.get("exit_code", -1), "status": result["status"]}

        elif name == "file_read":
            path = args["path"]
            max_bytes = args.get("max_bytes", 1048576)
            if not os.path.exists(path):
                return {"error": f"File not found: {path}"}
            if os.path.getsize(path) > max_bytes:
                return {"error": f"File too large (> {max_bytes} bytes)"}
            with open(path, "r", errors="replace") as f:
                return {"content": f.read(max_bytes), "path": path}

        elif name == "file_write":
            path = args["path"]
            mode = "a" if args.get("mode") == "append" else "w"
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, mode) as f:
                f.write(args["content"])
            return {"status": "written", "path": path, "bytes": len(args["content"])}

        elif name == "http_request":
            try:
                resp = await self._http_client.request(
                    method=args.get("method", "GET"),
                    url=args["url"],
                    headers=args.get("headers"),
                    content=args.get("body"),
                )
                return {
                    "status_code": resp.status_code,
                    "headers": dict(resp.headers),
                    "body": resp.text[:32768],
                }
            except Exception as e:
                return {"error": str(e)}

        elif name == "python_exec":
            result = await executor.execute(args["code"], "python", args.get("timeout", 15))
            return {"output": result.get("stdout", ""), "error": result.get("stderr", ""),
                    "exit_code": result.get("exit_code", -1), "status": result["status"]}

        return {"error": f"Builtin handler not implemented for '{name}'"}

    async def _call_http(self, endpoint: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            resp = await self._http_client.post(endpoint, json=arguments)
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    async def close(self):
        await self._http_client.aclose()


# ── Planning System ─────────────────────────────────────────────────

class Planner:
    """Task decomposition using the inference server."""

    def __init__(self, inference_url: str):
        self.inference_url = inference_url
        self._client = httpx.AsyncClient(timeout=60.0)

    async def plan(self, task: str, context: Optional[str] = None,
                   max_steps: int = 10) -> Dict[str, Any]:
        prompt = self._build_planning_prompt(task, context, max_steps)

        try:
            resp = await self._client.post(
                f"{self.inference_url}/inference/generate",
                json={"prompt": prompt, "max_tokens": 2048, "temperature": 0.3},
            )
            resp.raise_for_status()
            data = resp.json()
            raw_response = data.get("response", "")
            steps = self._parse_steps(raw_response)
            return {
                "task": task,
                "steps": steps,
                "total_steps": len(steps),
                "model": data.get("model", "inference"),
                "raw": raw_response[:4096],
            }
        except Exception as e:
            return {
                "task": task,
                "steps": [{"step": 1, "action": task, "tool": "python_exec", "status": "pending"}],
                "total_steps": 1,
                "error": str(e),
                "fallback": True,
            }

    def _build_planning_prompt(self, task: str, context: Optional[str], max_steps: int) -> str:
        parts = [
            "You are a task planning agent. Break the following task into concrete, executable steps.",
            "Each step should specify: step number, action, tool to use (shell/python_exec/file_read/file_write/http_request), and expected output.",
            f"Maximum {max_steps} steps. Return a JSON array of steps.",
            "",
            f"Task: {task}",
        ]
        if context:
            parts.append(f"\nContext: {context}")
        parts.append("")
        parts.append('Response format: [{"step": 1, "action": "...", "tool": "...", "args": {...}, "depends_on": []}]')
        parts.append("Return ONLY the JSON array, no other text.")
        return "\n".join(parts)

    def _parse_steps(self, raw: str) -> List[Dict[str, Any]]:
        raw = raw.strip()
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1:
            return self._fallback_steps(raw)
        try:
            steps = json.loads(raw[start:end + 1])
            if isinstance(steps, list):
                for i, step in enumerate(steps):
                    step.setdefault("step", i + 1)
                    step.setdefault("status", "pending")
                return steps[:20]
        except json.JSONDecodeError:
            pass
        return self._fallback_steps(raw)

    def _fallback_steps(self, raw: str) -> List[Dict[str, Any]]:
        lines = [l.strip() for l in raw.split("\n") if l.strip() and not l.strip().startswith("```")]
        steps = []
        for i, line in enumerate(lines[:10]):
            clean = line.lstrip("0123456789.-) ")
            if clean:
                steps.append({
                    "step": i + 1,
                    "action": clean,
                    "tool": "python_exec",
                    "status": "pending",
                })
        return steps or [{"step": 1, "action": raw[:200], "tool": "python_exec", "status": "pending"}]

    async def close(self):
        await self._client.aclose()


# ── Execution History & Cache ───────────────────────────────────────

class ExecutionHistory:
    """Track execution history with result caching."""

    def __init__(self, max_size: int = MAX_HISTORY):
        self._history: deque = deque(maxlen=max_size)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 3600

    def add(self, entry: Dict[str, Any]):
        entry["timestamp"] = datetime.now().isoformat()
        self._history.append(entry)

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        return list(self._history)[-limit:]

    def cache_key(self, code: str, language: str, env_key: str = "") -> str:
        content = f"{language}:{env_key}:{code}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get_cached(self, key: str) -> Optional[Dict[str, Any]]:
        entry = self._cache.get(key)
        if entry and (time.time() - entry["cached_at"]) < self._cache_ttl:
            return entry["result"]
        if entry:
            del self._cache[key]
        return None

    def set_cached(self, key: str, result: Dict[str, Any]):
        self._cache[key] = {"result": result, "cached_at": time.time()}

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    @property
    def total_executions(self) -> int:
        return len(self._history)


# ── Agent Loop ──────────────────────────────────────────────────────

class AgentRunner:
    """Full agent loop: plan → execute → observe → repeat."""

    def __init__(self, planner: Planner, executor: SandboxExecutor,
                 tools: ToolRegistry, history: ExecutionHistory):
        self.planner = planner
        self.executor = executor
        self.tools = tools
        self.history = history

    async def run(self, task: str, max_iterations: int = 5,
                  conversation: Optional[List[Dict[str, str]]] = None,
                  tool_filter: Optional[List[str]] = None) -> Dict[str, Any]:
        run_id = str(uuid.uuid4())[:8]
        start = time.time()
        steps_log: List[Dict[str, Any]] = []
        observations: List[str] = []

        plan_result = await self.planner.plan(task)
        steps_log.append({"phase": "plan", "result": plan_result})
        steps = plan_result.get("steps", [])

        if not steps:
            return {
                "run_id": run_id,
                "status": "completed",
                "task": task,
                "steps": steps_log,
                "summary": "No actionable steps could be planned.",
                "latency_ms": int((time.time() - start) * 1000),
            }

        iteration = 0
        for step in steps[:max_iterations]:
            iteration += 1
            tool_name = step.get("tool", "python_exec")
            action = step.get("action", "")
            args = step.get("args", {})

            if tool_filter and tool_name not in tool_filter:
                steps_log.append({
                    "phase": "execute",
                    "iteration": iteration,
                    "step": step,
                    "result": {"skipped": True, "reason": f"Tool '{tool_name}' not in allowed set"},
                })
                continue

            if tool_name == "python_exec":
                args.setdefault("code", action)
            elif tool_name == "shell":
                args.setdefault("command", action)
            elif tool_name == "file_read":
                args.setdefault("path", action)

            exec_result = await self.tools.call(tool_name, args)
            steps_log.append({
                "phase": "execute",
                "iteration": iteration,
                "step": step,
                "tool": tool_name,
                "result": exec_result,
            })

            output = exec_result.get("output", exec_result.get("content", exec_result.get("body", "")))
            if isinstance(output, str) and output:
                observations.append(f"Step {iteration} ({tool_name}): {output[:500]}")

            self.history.add({
                "type": "agent_step",
                "run_id": run_id,
                "iteration": iteration,
                "tool": tool_name,
                "action": action,
                "result": exec_result,
            })

            if exec_result.get("status") == TaskStatus.FAILED or exec_result.get("error"):
                steps_log.append({
                    "phase": "observe",
                    "iteration": iteration,
                    "observation": f"Step failed: {exec_result.get('error', 'unknown error')}",
                })

        summary = await self._summarize(task, observations)
        return {
            "run_id": run_id,
            "status": "completed",
            "task": task,
            "iterations": iteration,
            "steps": steps_log,
            "summary": summary,
            "latency_ms": int((time.time() - start) * 1000),
        }

    async def _summarize(self, task: str, observations: List[str]) -> str:
        if not observations:
            return "No observations collected."
        obs_text = "\n".join(observations[-10:])
        prompt = (
            f"Task: {task}\n\n"
            f"Execution observations:\n{obs_text}\n\n"
            f"Provide a concise summary of what was accomplished and any issues encountered."
        )
        try:
            resp = await self.planner._client.post(
                f"{self.planner.inference_url}/inference/generate",
                json={"prompt": prompt, "max_tokens": 512, "temperature": 0.3},
            )
            resp.raise_for_status()
            return resp.json().get("response", "Summary unavailable.")
        except Exception:
            return f"Completed {len(observations)} steps. Last observation: {observations[-1][:300]}"


# ── Globals ─────────────────────────────────────────────────────────

executor = SandboxExecutor()
tools = ToolRegistry()
history = ExecutionHistory()
planner = Planner(INFERENCE_URL)
agent = AgentRunner(planner, executor, tools, history)
_start_time = time.time()


# ── App ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await tools.close()
    await planner.close()


app = FastAPI(title="Kolibri Agent Service", version="1.0", lifespan=lifespan)


# ── Health & Status ─────────────────────────────────────────────────

@app.get("/agent/health")
async def health():
    inference_ok = False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{INFERENCE_URL}/inference/health")
            inference_ok = resp.status_code == 200
    except Exception:
        pass

    uptime = int(time.time() - _start_time)
    return {
        "status": "ok",
        "service": "agent",
        "port": SERVICE_PORT,
        "inference": "connected" if inference_ok else "disconnected",
        "inference_url": INFERENCE_URL,
        "active_executions": executor.active_count,
        "total_executions": history.total_executions,
        "cache_size": history.cache_size,
        "registered_tools": len(tools.list_tools()),
        "uptime_seconds": uptime,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/agent/status")
async def status():
    return {
        "active_tasks": executor.active_tasks,
        "active_count": executor.active_count,
        "max_concurrent": MAX_CONCURRENT,
        "total_executions": history.total_executions,
        "cache_size": history.cache_size,
        "recent_history": history.get_recent(10),
        "tools": tools.list_tools(),
    }


# ── Execute ─────────────────────────────────────────────────────────

@app.post("/agent/execute")
async def execute(req: ExecuteRequest):
    if not req.code.strip():
        raise HTTPException(400, "Code cannot be empty")

    cache_key = history.cache_key(req.code, req.language)
    cached = history.get_cached(cache_key)
    if cached:
        return {**cached, "cached": True}

    timeout = min(req.timeout, MAX_TIMEOUT)
    result = await executor.execute(
        code=req.code,
        language=req.language,
        timeout=timeout,
        env=req.env,
        workdir=req.workdir,
    )

    history.add({"type": "execute", "language": req.language, "result": result})
    if result["status"] == TaskStatus.COMPLETED:
        history.set_cached(cache_key, result)

    return result


# ── Plan ────────────────────────────────────────────────────────────

@app.post("/agent/plan")
async def plan(req: PlanRequest):
    if not req.task.strip():
        raise HTTPException(400, "Task cannot be empty")
    result = await planner.plan(req.task, req.context, req.max_steps)
    history.add({"type": "plan", "task": req.task, "result": result})
    return result


# ── Tools ───────────────────────────────────────────────────────────

@app.post("/agent/tools")
async def manage_tool(call: ToolCall):
    if not call.name:
        raise HTTPException(400, "Tool name required")
    result = await tools.call(call.name, call.arguments)
    history.add({"type": "tool_call", "tool": call.name, "args": call.arguments, "result": result})
    return {"tool": call.name, "result": result}


@app.post("/agent/tools/register")
async def register_tool(reg: ToolRegistration):
    tools.register(reg.name, reg.description, reg.parameters, reg.handler, reg.endpoint)
    return {"status": "registered", "name": reg.name}


@app.delete("/agent/tools/{name}")
async def unregister_tool(name: str):
    if tools.unregister(name):
        return {"status": "unregistered", "name": name}
    raise HTTPException(404, f"Tool '{name}' not found or is builtin")


@app.get("/agent/tools")
async def list_tools():
    return {"tools": tools.list_tools()}


# ── Run (Full Agent Loop) ──────────────────────────────────────────

@app.post("/agent/run")
async def run_agent(req: RunRequest):
    if not req.task.strip():
        raise HTTPException(400, "Task cannot be empty")

    result = await agent.run(
        task=req.task,
        max_iterations=req.max_iterations,
        conversation=req.conversation,
        tool_filter=req.tools,
    )
    history.add({"type": "run", "task": req.task, "result": result})
    return result


# ── Chat (Pipeline Integration) ─────────────────────────────────────

@app.post("/agent/chat")
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty")

    start = time.time()
    tools_used: List[Dict[str, Any]] = []
    response_text = ""

    plan_result = await planner.plan(req.message)
    steps = plan_result.get("steps", [])

    if steps:
        first_step = steps[0]
        tool_name = first_step.get("tool", "python_exec")
        args = first_step.get("args", {})

        if tool_name == "python_exec":
            args.setdefault("code", first_step.get("action", ""))
        elif tool_name == "shell":
            args.setdefault("command", first_step.get("action", ""))

        exec_result = await tools.call(tool_name, args)
        tools_used.append({"tool": tool_name, "args": args, "result": exec_result})

        output = exec_result.get("output", exec_result.get("content", exec_result.get("body", "")))

        summary_prompt = (
            f"User asked: {req.message}\n\n"
            f"I used the '{tool_name}' tool and got:\n{str(output)[:2000]}\n\n"
            f"Provide a helpful response to the user based on this result."
        )
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{INFERENCE_URL}/inference/generate",
                    json={"prompt": summary_prompt, "max_tokens": 1024, "temperature": 0.5},
                )
                resp.raise_for_status()
                response_text = resp.json().get("response", "")
        except Exception as e:
            response_text = f"Executed {tool_name}. Result:\n{str(output)[:2000]}"

    if not response_text:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{INFERENCE_URL}/inference/generate",
                    json={"prompt": req.message, "max_tokens": 2048, "temperature": 0.7},
                )
                resp.raise_for_status()
                response_text = resp.json().get("response", "I couldn't generate a response.")
        except Exception as e:
            response_text = f"Agent error: {e}"

    latency = int((time.time() - start) * 1000)
    history.add({
        "type": "chat",
        "message": req.message,
        "response": response_text[:500],
        "tools_used": len(tools_used),
        "latency_ms": latency,
    })

    return {
        "response": response_text,
        "tools_used": tools_used,
        "plan": plan_result,
        "latency_ms": latency,
    }


# ── History ─────────────────────────────────────────────────────────

@app.get("/agent/history")
async def get_history(limit: int = 50):
    return {
        "history": history.get_recent(limit),
        "total": history.total_executions,
    }


# ── Entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"🤖 Kolibri Agent Service on :{SERVICE_PORT}")
    print(f"   Inference: {INFERENCE_URL}")
    print(f"   Sandbox: {MAX_TIMEOUT}s timeout, {MAX_MEMORY_MB}MB memory limit")
    print(f"   Tools: {len(tools.list_tools())} registered")
    uvicorn.run(app, host="0.0.0.0", port=SERVICE_PORT)
