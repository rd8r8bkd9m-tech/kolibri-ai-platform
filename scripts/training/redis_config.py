#!/usr/bin/env python3
"""Redis configuration check and setup for Kolibri training cluster.

Verifies Redis connectivity, sets up required keys/prefixes,
and validates cluster configuration for all nodes.

Usage:
  python3 redis_config.py check
  python3 redis_config.py setup
  python3 redis_config.py nodes
  python3 redis_config.py reset-jobs
"""

import argparse
import json
import os
import sys
import time
from typing import Optional

try:
    import redis as redis_lib
except ImportError:
    redis_lib = None


DEFAULT_HOST = os.environ.get("KOLIBRI_REDIS", "10.99.0.1")
DEFAULT_PORT = int(os.environ.get("KOLIBRI_REDIS_PORT", "6379"))

REDIS_PREFIXES = [
    "kolibri:training:",
    "kolibri:state:",
    "kolibri:jobs:",
    "kolibri:resources:",
]

REQUIRED_CONFIG = {
    "maxmemory-policy": "allkeys-lru",
    "tcp-keepalive": "300",
    "timeout": "0",
}


def check_redis(host: str, port: int) -> dict:
    """Check Redis connectivity and configuration."""
    result = {
        "connected": False,
        "version": None,
        "memory": None,
        "clients": None,
        "config": {},
        "issues": [],
    }

    if redis_lib is None:
        result["issues"].append("redis package not installed")
        return result

    try:
        r = redis_lib.Redis(host=host, port=port, decode_responses=True, socket_timeout=5)
        r.ping()
        result["connected"] = True
    except Exception as e:
        result["issues"].append(f"Connection failed: {e}")
        return result

    try:
        info = r.info()
        result["version"] = info.get("redis_version")
        result["memory"] = {
            "used_mb": info.get("used_memory", 0) / 1e6,
            "peak_mb": info.get("used_memory_peak", 0) / 1e6,
            "max_mb": (info.get("maxmemory", 0) or 0) / 1e6,
        }
        result["clients"] = {
            "connected": info.get("connected_clients", 0),
            "blocked": info.get("blocked_clients", 0),
        }
    except Exception as e:
        result["issues"].append(f"Info command failed: {e}")

    # Check important config values
    try:
        for key, expected in REQUIRED_CONFIG.items():
            actual = r.config_get(key).get(key)
            result["config"][key] = actual
            if actual and actual != expected:
                result["issues"].append(
                    f"Config {key}={actual}, recommended={expected}"
                )
    except Exception:
        pass  # CONFIG GET may be disabled

    # Check persistence
    try:
        persistence = r.info("persistence")
        if persistence.get("rdb_last_bgsave_status") != "ok":
            result["issues"].append("RDB last save failed")
    except Exception:
        pass

    return result


def setup_redis(host: str, port: int) -> dict:
    """Set up Redis keys and prefixes for Kolibri training."""
    result = {"setup": [], "errors": []}

    if redis_lib is None:
        result["errors"].append("redis package not installed")
        return result

    try:
        r = redis_lib.Redis(host=host, port=port, decode_responses=True, socket_timeout=5)
        r.ping()
    except Exception as e:
        result["errors"].append(f"Connection failed: {e}")
        return result

    # Set up initial state keys
    initial_keys = {
        "kolibri:state:cluster_version": "1.0.0",
        "kolibri:state:training_enabled": "true",
        "kolibri:state:last_setup": str(time.time()),
    }

    for key, value in initial_keys.items():
        try:
            r.set(key, value)
            result["setup"].append(f"Set {key} = {value}")
        except Exception as e:
            result["errors"].append(f"Failed to set {key}: {e}")

    # Set recommended config
    try:
        r.config_set("tcp-keepalive", "300")
        result["setup"].append("Set tcp-keepalive=300")
    except Exception:
        result["setup"].append("Note: CONFIG SET not available (may need manual config)")

    # Verify training namespace is accessible
    try:
        test_key = "kolibri:training:_test"
        r.set(test_key, "ok", ex=10)
        val = r.get(test_key)
        r.delete(test_key)
        if val == "ok":
            result["setup"].append("Training namespace verified")
        else:
            result["errors"].append("Training namespace test failed")
    except Exception as e:
        result["errors"].append(f"Namespace test failed: {e}")

    return result


def list_nodes(host: str, port: int) -> list:
    """List all known cluster nodes from Redis."""
    if redis_lib is None:
        return [{"error": "redis package not installed"}]

    try:
        r = redis_lib.Redis(host=host, port=port, decode_responses=True, socket_timeout=5)
        r.ping()
    except Exception as e:
        return [{"error": f"Connection failed: {e}"}]

    nodes = []
    for key in r.scan_iter("kolibri:training:nodes:*"):
        node_data = r.hgetall(key)
        name = key.split(":")[-1]
        load = {}
        try:
            load = json.loads(node_data.get("load", "{}"))
        except Exception:
            pass

        last_seen = float(node_data.get("last_seen", 0))
        age = time.time() - last_seen
        online = age < 120  # Consider offline if no heartbeat in 2 minutes

        nodes.append({
            "name": name,
            "status": "online" if online else "offline",
            "cpu": load.get("cpu_percent", "?"),
            "mem": load.get("mem_percent", "?"),
            "last_seen_ago": f"{age:.0f}s",
        })

    return sorted(nodes, key=lambda n: n["name"])


def reset_jobs(host: str, port: int, status: str = None) -> dict:
    """Reset training jobs. Optionally filter by status."""
    result = {"deleted": 0, "errors": []}

    if redis_lib is None:
        result["errors"].append("redis package not installed")
        return result

    try:
        r = redis_lib.Redis(host=host, port=port, decode_responses=True, socket_timeout=5)
        r.ping()
    except Exception as e:
        result["errors"].append(f"Connection failed: {e}")
        return result

    for key in r.scan_iter("kolibri:training:job:*"):
        if status:
            job_status = r.hget(key, "status")
            if job_status != status:
                continue
        r.delete(key)
        result["deleted"] += 1

    return result


def main():
    parser = argparse.ArgumentParser(description="Kolibri Redis configuration")
    parser.add_argument("--host", type=str, default=DEFAULT_HOST, help="Redis host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Redis port")

    subparsers = parser.add_subparsers(dest="command", help="Command")
    subparsers.add_parser("check", help="Check Redis connectivity and config")
    subparsers.add_parser("setup", help="Initialize Redis for Kolibri training")
    subparsers.add_parser("nodes", help="List cluster nodes")

    reset_parser = subparsers.add_parser("reset-jobs", help="Reset training jobs")
    reset_parser.add_argument("--status", type=str, default=None,
                              help="Only reset jobs with this status")

    args = parser.parse_args()

    if args.command == "check":
        result = check_redis(args.host, args.port)
        print(f"Redis at {args.host}:{args.port}")
        print(f"  Connected: {result['connected']}")
        if result["version"]:
            print(f"  Version: {result['version']}")
        if result["memory"]:
            m = result["memory"]
            print(f"  Memory: {m['used_mb']:.1f}MB used, {m['peak_mb']:.1f}MB peak")
            if m["max_mb"]:
                print(f"  Max memory: {m['max_mb']:.0f}MB")
        if result["clients"]:
            c = result["clients"]
            print(f"  Clients: {c['connected']} connected, {c['blocked']} blocked")
        if result["issues"]:
            print("\n  Issues:")
            for issue in result["issues"]:
                print(f"    - {issue}")
        return 0 if result["connected"] else 1

    elif args.command == "setup":
        result = setup_redis(args.host, args.port)
        for item in result["setup"]:
            print(f"  OK: {item}")
        for err in result["errors"]:
            print(f"  ERR: {err}")
        return 0 if not result["errors"] else 1

    elif args.command == "nodes":
        nodes = list_nodes(args.host, args.port)
        if not nodes:
            print("No cluster nodes found in Redis.")
        else:
            print(f"{'Node':<20} {'Status':<10} {'CPU':<8} {'MEM':<8} {'Last Seen'}")
            print("-" * 60)
            for n in nodes:
                print(f"{n['name']:<20} {n['status']:<10} {n['cpu']:<8} {n['mem']:<8} {n['last_seen_ago']}")
        return 0

    elif args.command == "reset-jobs":
        result = reset_jobs(args.host, args.port, status=args.status)
        print(f"Deleted {result['deleted']} job(s)")
        for err in result["errors"]:
            print(f"  ERR: {err}")
        return 0

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    exit(main() or 0)
