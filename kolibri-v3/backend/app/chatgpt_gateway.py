"""ChatGPT Gateway — proxies requests through browser session to ChatGPT backend API.

This gateway allows using ChatGPT Pro subscription without API credits by
routing requests through the authenticated browser session.
"""

from __future__ import annotations

import json
import os
import sqlite3
import hashlib
import threading
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/v1/chatgpt-gateway", tags=["chatgpt-gateway"])

# Chrome cookie decryption
_CHROME_KEY_PASSWORD = None
_CHROME_KEY_CACHE: bytes | None = None
_CHROME_KEY_LOCK = threading.Lock()


def _get_chrome_key() -> bytes:
    global _CHROME_KEY_CACHE
    if _CHROME_KEY_CACHE is not None:
        return _CHROME_KEY_CACHE
    with _CHROME_KEY_LOCK:
        if _CHROME_KEY_CACHE is not None:
            return _CHROME_KEY_CACHE
        # Try environment variable first
        env_key = os.environ.get("CHROME_COOKIE_KEY")
        if env_key:
            _CHROME_KEY_CACHE = hashlib.pbkdf2_hmac(
                'sha1', env_key.encode(), b'saltysalt', 1003, dklen=16
            )
            return _CHROME_KEY_CACHE
        # Try keychain (may timeout)
        import subprocess
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", "Chrome Safe Storage", "-w"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                key_password = result.stdout.strip()
                _CHROME_KEY_CACHE = hashlib.pbkdf2_hmac(
                    'sha1', key_password.encode(), b'saltysalt', 1003, dklen=16
                )
                return _CHROME_KEY_CACHE
        except (subprocess.TimeoutExpired, Exception):
            pass
        raise RuntimeError(
            "Cannot get Chrome encryption key. Set CHROME_COOKIE_KEY env var."
        )


def _decrypt_chrome_cookie(encrypted_value: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.backends import default_backend

    if encrypted_value[:3] != b'v10':
        raise ValueError("Unknown Chrome cookie encryption format")

    key = _get_chrome_key()
    iv = b' ' * 16
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(encrypted_value[3:]) + decryptor.finalize()

    unpadder = padding.PKCS7(128).unpadder()
    unpadded = unpadder.update(decrypted) + unpadder.finalize()

    # Find JWT token (starts with eyJ)
    token_str = unpadded.decode('latin-1')
    jwt_start = token_str.find('eyJ')
    if jwt_start >= 0:
        return token_str[jwt_start:]
    return token_str


def _get_session_token() -> str | None:
    """Read ChatGPT session token from Chrome cookies database."""
    cookies_path = Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies"
    if not cookies_path.exists():
        return None

    try:
        conn = sqlite3.connect(str(cookies_path))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT encrypted_value FROM cookies
            WHERE host_key LIKE '%chatgpt.com%'
            AND name = '__Secure-next-auth.session-token'
        """)
        row = cursor.fetchone()
        conn.close()

        if row and row[0]:
            return _decrypt_chrome_cookie(row[0])
    except Exception:
        pass
    return None


def _get_access_token(session_token: str) -> str | None:
    """Get access token from ChatGPT page using session token."""
    # This would need browser automation to extract the access token
    # For now, return None and rely on the session token directly
    return None


@router.get("/status")
async def gateway_status():
    """Check gateway status and session availability."""
    session_token = _get_session_token()
    return {
        "status": "ok" if session_token else "no_session",
        "session_available": session_token is not None,
        "message": "ChatGPT session found" if session_token else "No ChatGPT session in Chrome"
    }


@router.post("/chat/completions")
async def chat_completions(request: Request):
    """Proxy chat completion requests to ChatGPT backend API."""
    body = await request.json()

    # Get session token
    session_token = _get_session_token()
    if not session_token:
        return JSONResponse(
            status_code=401,
            content={"error": {"message": "No ChatGPT session available. Please login to ChatGPT in Chrome."}}
        )

    # Convert OpenAI format to ChatGPT format
    messages = body.get("messages", [])
    model = body.get("model", "gpt-4o")

    # Build ChatGPT request
    chatgpt_messages = []
    for msg in messages:
        if msg.get("role") == "system":
            # System message becomes part of the first user message
            continue
        chatgpt_messages.append({
            "id": str(uuid.uuid4()),
            "author": {"role": msg.get("role", "user")},
            "content": {"content_type": "text", "parts": [msg.get("content", "")]}
        })

    if not chatgpt_messages:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "No user messages provided"}}
        )

    chatgpt_payload = {
        "action": "next",
        "messages": chatgpt_messages,
        "model": model,
        "parent_message_id": str(uuid.uuid4()),
        "timezone_offset_min": -180,
    }

    # Make request to ChatGPT backend API
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                "https://chatgpt.com/backend-api/conversation",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {session_token}",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                },
                json=chatgpt_payload,
            )

            if response.status_code != 200:
                return JSONResponse(
                    status_code=response.status_code,
                    content={"error": {"message": f"ChatGPT API returned {response.status_code}"}}
                )

            # Parse SSE response
            response_text = response.text
            content_parts = []

            for line in response_text.split("\n"):
                if line.startswith("data: "):
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        if chunk.get("message", {}).get("content", {}).get("parts"):
                            content_parts.extend(chunk["message"]["content"]["parts"])
                    except json.JSONDecodeError:
                        continue

            content = "".join(content_parts) if content_parts else "No response from ChatGPT"

            # Return in OpenAI format
            return {
                "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                }
            }

        except httpx.TimeoutException:
            return JSONResponse(
                status_code=504,
                content={"error": {"message": "ChatGPT API request timed out"}}
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": {"message": f"Gateway error: {str(e)}"}}
            )
