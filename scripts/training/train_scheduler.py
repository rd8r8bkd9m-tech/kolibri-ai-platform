#!/usr/bin/env python3
"""Training scheduler for Kolibri AI Platform.

Monitors system load and runs fine-tuning jobs during low-load periods.
Uses Redis for distributed coordination and job state tracking.

Features:
  - CPU/memory load monitoring via psutil
  - Configurable load thresholds for scheduling
  - Redis-based job queue and status tracking
  - Automatic retry on failure
  - Cluster-aware: prevents concurrent training on multiple nodes

Usage:
  python3 train_scheduler.py --redis-host 10.99.0.1
  python3 train_scheduler.py --redis-host 10.99.0.1 --max-cpu 50 --max-mem 70
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import psutil

try:
    import redis as redis_lib
except ImportError:
    redis_lib = None


REDIS_PREFIX = "kolibri:training"
NODE_NAME = os.environ.get("KOLIBRI_NODE_NAME", "home")


class TrainingScheduler:
    """Monitors system load and dispatches fine-tuning jobs."""

    def __init__(
        self,
        redis_host: str = "10.99.0.1",
        redis_port: int = 6379,
        max_cpu_percent: float = 50.0,
        max_mem_percent: float = 70.0,
        check_interval: int = 30,
        cooldown: int = 300,
        script_dir: str = None,
    ):
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.max_cpu = max_cpu_percent
        self.max_mem = max_mem_percent
        self.check_interval = check_interval
        self.cooldown = cooldown
        self.script_dir = Path(script_dir or Path(__file__).parent)
        self.running = True
        self.redis: Optional[redis_lib.Redis] = None
        self.last_train_time = 0

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        print(f"\nReceived signal {signum}, shutting down...")
        self.running = False

    def connect_redis(self) -> bool:
        """Connect to Redis. Returns True on success."""
        if redis_lib is None:
            print("Error: redis package not installed. pip install redis")
            return False
        try:
            self.redis = redis_lib.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=True,
                socket_timeout=5,
            )
            self.redis.ping()
            print(f"Connected to Redis at {self.redis_host}:{self.redis_port}")
            return True
        except Exception as e:
            print(f"Redis connection failed: {e}")
            return False

    def get_system_load(self) -> dict:
        """Get current CPU and memory usage."""
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage("/")
        return {
            "cpu_percent": cpu,
            "mem_percent": mem.percent,
            "mem_available_gb": mem.available / 1e9,
            "swap_percent": swap.percent,
            "disk_percent": disk.percent,
            "timestamp": time.time(),
        }

    def is_low_load(self) -> bool:
        """Check if system load is below thresholds."""
        load = self.get_system_load()
        if load["cpu_percent"] > self.max_cpu:
            return False
        if load["mem_percent"] > self.max_mem:
            return False
        if time.time() - self.last_train_time < self.cooldown:
            return False
        return True

    def update_node_status(self, load: dict):
        """Publish node load to Redis for cluster visibility."""
        if not self.redis:
            return
        try:
            self.redis.hset(
                f"{REDIS_PREFIX}:nodes:{NODE_NAME}",
                mapping={
                    "load": json.dumps(load),
                    "status": "idle",
                    "last_seen": str(time.time()),
                },
            )
        except Exception:
            pass

    def get_pending_jobs(self) -> list:
        """Get pending training jobs from Redis queue."""
        if not self.redis:
            return []
        try:
            jobs = []
            for key in self.redis.scan_iter(f"{REDIS_PREFIX}:job:*"):
                job = self.redis.hgetall(key)
                if job.get("status") == "pending":
                    job["key"] = key
                    jobs.append(job)
            # Sort by priority, then created_at
            jobs.sort(key=lambda j: (int(j.get("priority", 999)), float(j.get("created_at", 0))))
            return jobs
        except Exception as e:
            print(f"Error fetching jobs: {e}")
            return []

    def claim_job(self, job_key: str) -> bool:
        """Atomically claim a job for this node."""
        if not self.redis:
            return False
        try:
            # Use a simple lock: set status to "running" only if still "pending"
            pipe = self.redis.pipeline()
            pipe.watch(job_key)
            status = pipe.hget(job_key, "status")
            if status != "pending":
                pipe.unwatch()
                return False
            pipe.multi()
            pipe.hset(job_key, mapping={
                "status": "running",
                "node": NODE_NAME,
                "started_at": str(time.time()),
            })
            pipe.execute()
            return True
        except Exception as e:
            print(f"Error claiming job: {e}")
            return False

    def update_job_status(self, job_key: str, status: str, detail: str = ""):
        """Update job status in Redis."""
        if not self.redis:
            return
        try:
            mapping = {"status": status, "updated_at": str(time.time())}
            if detail:
                mapping["detail"] = detail
            if status in ("completed", "failed"):
                mapping["finished_at"] = str(time.time())
            self.redis.hset(job_key, mapping=mapping)
        except Exception:
            pass

    def run_training_job(self, job: dict) -> bool:
        """Execute a training job as a subprocess."""
        job_key = job["key"]
        job_id = job_key.split(":")[-1]

        train_data = job.get("train_data", "data/train_conversations.jsonl")
        val_data = job.get("val_data", "data/val_conversations.jsonl")
        model = job.get("model", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
        epochs = job.get("epochs", "3")
        lora_r = job.get("lora_r", "16")
        batch_size = job.get("batch_size", "2")
        output_dir = job.get("output_dir", f"output/tinyllama-{job_id}")

        self.update_job_status(job_key, "running", "Starting training")

        cmd = [
            sys.executable, str(self.script_dir / "finetune.py"),
            "--model", model,
            "--train-data", train_data,
            "--val-data", val_data,
            "--output-dir", output_dir,
            "--epochs", str(epochs),
            "--lora-r", str(lora_r),
            "--batch-size", str(batch_size),
            "--redis-host", self.redis_host,
            "--redis-port", str(self.redis_port),
            "--job-id", job_id,
            "--cpu",
        ]

        if job.get("export_gguf") == "true":
            cmd.append("--export-gguf")
            if job.get("llama_cpp_path"):
                cmd.extend(["--llama-cpp-path", job["llama_cpp_path"]])

        print(f"Running training job {job_id}: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=7200,  # 2 hour timeout
                cwd=str(self.script_dir),
            )

            if result.returncode == 0:
                self.update_job_status(job_key, "completed", "Training finished successfully")
                print(f"Job {job_id} completed successfully")
                return True
            else:
                error = result.stderr[-500:] if result.stderr else "Unknown error"
                self.update_job_status(job_key, "failed", error)
                print(f"Job {job_id} failed: {error}")
                return False

        except subprocess.TimeoutExpired:
            self.update_job_status(job_key, "failed", "Training timed out (2h)")
            print(f"Job {job_id} timed out")
            return False
        except Exception as e:
            self.update_job_status(job_key, "failed", str(e))
            print(f"Job {job_id} error: {e}")
            return False

    def submit_job(
        self,
        train_data: str = "data/train_conversations.jsonl",
        val_data: str = "data/val_conversations.jsonl",
        model: str = "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        epochs: int = 3,
        lora_r: int = 16,
        batch_size: int = 2,
        priority: int = 10,
        export_gguf: bool = False,
    ) -> str:
        """Submit a new training job to the queue. Returns job ID."""
        if not self.redis:
            raise RuntimeError("Not connected to Redis")

        job_id = f"job_{int(time.time() * 1000)}"
        job_key = f"{REDIS_PREFIX}:job:{job_id}"

        self.redis.hset(job_key, mapping={
            "id": job_id,
            "status": "pending",
            "train_data": train_data,
            "val_data": val_data,
            "model": model,
            "epochs": str(epochs),
            "lora_r": str(lora_r),
            "batch_size": str(batch_size),
            "priority": str(priority),
            "export_gguf": str(export_gguf).lower(),
            "created_at": str(time.time()),
            "submitted_by": NODE_NAME,
        })

        print(f"Submitted training job: {job_id}")
        return job_id

    def get_job_status(self, job_id: str) -> dict:
        """Get status of a training job."""
        if not self.redis:
            return {"error": "Not connected to Redis"}
        job_key = f"{REDIS_PREFIX}:job:{job_id}"
        return self.redis.hgetall(job_key) or {"error": "Job not found"}

    def list_jobs(self, status: str = None) -> list:
        """List all training jobs, optionally filtered by status."""
        if not self.redis:
            return []
        jobs = []
        for key in self.redis.scan_iter(f"{REDIS_PREFIX}:job:*"):
            job = self.redis.hgetall(key)
            if status is None or job.get("status") == status:
                jobs.append(job)
        jobs.sort(key=lambda j: float(j.get("created_at", 0)), reverse=True)
        return jobs

    def run_scheduler_loop(self):
        """Main scheduler loop: monitor load and dispatch jobs."""
        print(f"Training scheduler started (node: {NODE_NAME})")
        print(f"  Max CPU: {self.max_cpu}%")
        print(f"  Max Memory: {self.max_mem}%")
        print(f"  Check interval: {self.check_interval}s")
        print(f"  Cooldown: {self.cooldown}s")
        print()

        while self.running:
            load = self.get_system_load()
            self.update_node_status(load)

            if self.is_low_load():
                jobs = self.get_pending_jobs()
                if jobs:
                    job = jobs[0]
                    job_key = job["key"]
                    print(f"Low load detected, attempting to claim job: {job_key}")

                    if self.claim_job(job_key):
                        self.last_train_time = time.time()
                        self.run_training_job(job)
                    else:
                        print("Job already claimed by another node")
            else:
                cpu = load["cpu_percent"]
                mem = load["mem_percent"]
                remaining = max(0, self.cooldown - (time.time() - self.last_train_time))
                print(
                    f"High load: CPU {cpu:.0f}% (max {self.max_cpu}%), "
                    f"MEM {mem:.0f}% (max {self.max_mem}%)"
                    + (f", cooldown {remaining:.0f}s" if remaining > 0 else ""),
                )

            time.sleep(self.check_interval)

        print("Scheduler stopped.")


def main():
    parser = argparse.ArgumentParser(description="Kolibri training scheduler")
    parser.add_argument("--redis-host", type=str, default="10.99.0.1", help="Redis host")
    parser.add_argument("--redis-port", type=int, default=6379, help="Redis port")
    parser.add_argument("--max-cpu", type=float, default=50.0,
                        help="Max CPU percent to allow training")
    parser.add_argument("--max-mem", type=float, default=70.0,
                        help="Max memory percent to allow training")
    parser.add_argument("--check-interval", type=int, default=30,
                        help="Load check interval in seconds")
    parser.add_argument("--cooldown", type=int, default=300,
                        help="Cooldown between training runs in seconds")
    parser.add_argument("--script-dir", type=str, default=None,
                        help="Directory containing training scripts")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Schedule command (default)
    subparsers.add_parser("run", help="Run the scheduler loop")

    # Submit command
    submit_parser = subparsers.add_parser("submit", help="Submit a training job")
    submit_parser.add_argument("--train-data", type=str, default="data/train_conversations.jsonl")
    submit_parser.add_argument("--val-data", type=str, default="data/val_conversations.jsonl")
    submit_parser.add_argument("--model", type=str, default="TinyLlama/TinyLlama-1.1B-Chat-v1.0")
    submit_parser.add_argument("--epochs", type=int, default=3)
    submit_parser.add_argument("--lora-r", type=int, default=16)
    submit_parser.add_argument("--batch-size", type=int, default=2)
    submit_parser.add_argument("--priority", type=int, default=10)
    submit_parser.add_argument("--export-gguf", action="store_true")

    # Status command
    status_parser = subparsers.add_parser("status", help="Check job status")
    status_parser.add_argument("--job-id", type=str, required=True)

    # List command
    list_parser = subparsers.add_parser("list", help="List training jobs")
    list_parser.add_argument("--status", type=str, default=None,
                             help="Filter by status (pending/running/completed/failed)")

    # Load check
    subparsers.add_parser("load", help="Print current system load")

    args = parser.parse_args()

    scheduler = TrainingScheduler(
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        max_cpu_percent=args.max_cpu,
        max_mem_percent=args.max_mem,
        check_interval=args.check_interval,
        cooldown=args.cooldown,
        script_dir=args.script_dir,
    )

    if args.command == "load":
        load = scheduler.get_system_load()
        print(json.dumps(load, indent=2))
        low = (
            load["cpu_percent"] < args.max_cpu
            and load["mem_percent"] < args.max_mem
        )
        print(f"\nLow load: {low}")
        return

    if not scheduler.connect_redis():
        return 1

    if args.command == "submit":
        job_id = scheduler.submit_job(
            train_data=args.train_data,
            val_data=args.val_data,
            model=args.model,
            epochs=args.epochs,
            lora_r=args.lora_r,
            batch_size=args.batch_size,
            priority=args.priority,
            export_gguf=args.export_gguf,
        )
        print(f"Job ID: {job_id}")
        return

    if args.command == "status":
        status = scheduler.get_job_status(args.job_id)
        print(json.dumps(status, indent=2))
        return

    if args.command == "list":
        jobs = scheduler.list_jobs(status=args.status)
        if not jobs:
            print("No training jobs found.")
        else:
            for j in jobs:
                print(f"  {j.get('id', '?'):20s}  {j.get('status', '?'):10s}  "
                      f"created={j.get('created_at', '?')}")
        return

    # Default: run scheduler
    scheduler.run_scheduler_loop()
    return 0


if __name__ == "__main__":
    exit(main() or 0)
