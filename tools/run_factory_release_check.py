#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import urllib.request

from run_factory_canary import run

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "var" / "release-check" / "factory"
PORT = 8291
URL = f"http://127.0.0.1:{PORT}"


def terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=8)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
env = os.environ.copy()
env.update({
    "PYTHONPATH": str(ROOT / "services/api-gateway"),
    "KOLIBRI_ENV": "test",
    "KOLIBRI_DATA_DIR": str(OUT / "data"),
    "KOLIBRI_DB_PATH": str(OUT / "data" / "kolibri.db"),
    "KOLIBRI_ARTIFACT_DIR": str(OUT / "data" / "artifacts"),
    "KOLIBRI_SESSION_SECRET": "release-check-session-secret",
    "KOLIBRI_NODE_JOIN_TOKEN": "release-check-node-secret",
    "KOLIBRI_OWNER_ACCESS_TOKEN": "release-check-owner-secret",
})
log = (OUT / "api.log").open("w", encoding="utf-8")
process = subprocess.Popen(
    [str(ROOT / ".venv/bin/python"), "-m", "uvicorn", "main:app", "--app-dir", "services/api-gateway", "--host", "127.0.0.1", "--port", str(PORT)],
    cwd=ROOT,
    env=env,
    stdout=log,
    stderr=subprocess.STDOUT,
    text=True,
    start_new_session=True,
)
try:
    for _ in range(150):
        try:
            with urllib.request.urlopen(f"{URL}/ready", timeout=.5) as response:
                if response.status == 200:
                    break
        except Exception:
            time.sleep(.1)
    else:
        raise RuntimeError("Factory release-check API did not become ready")
    report = run(URL, "release-check-node-secret", "release-check-owner-secret")
    (OUT / "factory-canary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ok: authenticated factory canary passed")
finally:
    terminate(process)
    log.close()
