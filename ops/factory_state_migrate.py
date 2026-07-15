#!/usr/bin/env python3
"""Export/import a Kolibri Redis namespace for controlled CP migration."""
from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path


class Redis:
    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self.sock = socket.create_connection((self.host, self.port), timeout=30)
        self.stream = self.sock.makefile("rb")

    def command(self, *parts):
        payload = f"*{len(parts)}\r\n".encode()
        for part in parts:
            raw = str(part).encode()
            payload += f"${len(raw)}\r\n".encode() + raw + b"\r\n"
        self.sock.sendall(payload)
        return self._read(self.stream)

    def _read(self, stream):
        marker = stream.read(1)
        if marker == b"+": return stream.readline().rstrip(b"\r\n").decode()
        if marker == b"-": raise RuntimeError(stream.readline().decode().strip())
        if marker == b":": return int(stream.readline())
        if marker == b"$":
            size = int(stream.readline())
            if size < 0: return None
            data = stream.read(size); stream.read(2)
            return data.decode()
        if marker == b"*":
            size = int(stream.readline())
            if size < 0: return None
            return [self._read(stream) for _ in range(size)]
        raise RuntimeError(f"unsupported RESP marker: {marker!r}")

    def keys(self, pattern: str):
        cursor = "0"
        while True:
            cursor, keys = self.command("SCAN", cursor, "MATCH", pattern, "COUNT", 500)
            yield from keys
            if cursor == "0": break


def export_state(redis: Redis, namespace: str, output: Path) -> int:
    count = 0
    with output.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"format": 1, "namespace": namespace}) + "\n")
        for key in sorted(redis.keys(f"{namespace}:*")):
            kind = redis.command("TYPE", key)
            if kind == "string": value = redis.command("GET", key)
            elif kind == "set": value = redis.command("SMEMBERS", key) or []
            elif kind == "list": value = redis.command("LRANGE", key, 0, -1) or []
            elif kind == "hash": value = redis.command("HGETALL", key) or []
            elif kind == "zset": value = redis.command("ZRANGE", key, 0, -1, "WITHSCORES") or []
            else: raise RuntimeError(f"unsupported Redis type {kind} for {key}")
            fh.write(json.dumps({"key": key, "type": kind, "value": value, "pttl": redis.command("PTTL", key)}, ensure_ascii=False) + "\n")
            count += 1
    return count


def import_state(redis: Redis, namespace: str, source: Path, replace: bool) -> int:
    if replace:
        batch = []
        for key in redis.keys(f"{namespace}:*"):
            batch.append(key)
            if len(batch) == 200:
                redis.command("DEL", *batch); batch = []
        if batch: redis.command("DEL", *batch)
    count = 0
    with source.open(encoding="utf-8") as fh:
        header = json.loads(next(fh))
        if header.get("namespace") != namespace: raise RuntimeError("snapshot namespace mismatch")
        for line in fh:
            item = json.loads(line); key, kind, value = item["key"], item["type"], item["value"]
            if kind == "string": redis.command("SET", key, value)
            elif kind == "set" and value: redis.command("SADD", key, *value)
            elif kind == "list" and value: redis.command("RPUSH", key, *value)
            elif kind == "hash" and value: redis.command("HSET", key, *value)
            elif kind == "zset" and value:
                pairs = []
                for member, score in zip(value[0::2], value[1::2]): pairs.extend([score, member])
                redis.command("ZADD", key, *pairs)
            ttl = int(item.get("pttl", -1))
            if ttl > 0: redis.command("PEXPIRE", key, ttl)
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("export", "import"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--namespace", default="kolibri_factory_mvp")
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    redis = Redis(args.host, args.port)
    count = export_state(redis, args.namespace, args.file) if args.mode == "export" else import_state(redis, args.namespace, args.file, args.replace)
    print(json.dumps({"mode": args.mode, "namespace": args.namespace, "keys": count, "file": str(args.file)}))
    return 0


if __name__ == "__main__": raise SystemExit(main())
