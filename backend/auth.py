import time
import sqlite3
from typing import Optional

import jwt
import bcrypt
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from config import DB_PATH, JWT_SECRET, JWT_ALGORITHM, JWT_ACCESS_TOKEN_EXPIRE_MINUTES, JWT_REFRESH_TOKEN_EXPIRE_DAYS

security = HTTPBearer(auto_error=False)


class UserRegister(BaseModel):
    username: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    created_at: float


def init_users_table():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at REAL NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS refresh_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token TEXT UNIQUE NOT NULL,
        expires_at REAL NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""")
    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hash.encode("utf-8"))


def create_access_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "type": "access",
        "exp": time.time() + JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": time.time() + JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute(
        "INSERT INTO refresh_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
        (user_id, token, payload["exp"]),
    )
    conn.commit()
    conn.close()
    return token


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def register_user(data: UserRegister) -> TokenResponse:
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (data.username,))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Username already exists")

    now = time.time()
    c.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
        (data.username, hash_password(data.password), now),
    )
    user_id = c.lastrowid
    conn.commit()
    conn.close()

    access = create_access_token(user_id, data.username)
    refresh = create_refresh_token(user_id)
    return TokenResponse(access_token=access, refresh_token=refresh)


def login_user(data: UserLogin) -> TokenResponse:
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT id, password_hash FROM users WHERE username = ?", (data.username,))
    row = c.fetchone()
    conn.close()

    if not row or not verify_password(data.password, row[1]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access = create_access_token(row[0], data.username)
    refresh = create_refresh_token(row[0])
    return TokenResponse(access_token=access, refresh_token=refresh)


def refresh_access_token(refresh_token: str) -> TokenResponse:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT user_id FROM refresh_tokens WHERE token = ? AND expires_at > ?",
              (refresh_token, time.time()))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=401, detail="Refresh token revoked or expired")

    c.execute("SELECT username FROM users WHERE id = ?", (row[0],))
    user_row = c.fetchone()
    conn.close()

    if not user_row:
        raise HTTPException(status_code=401, detail="User not found")

    access = create_access_token(row[0], user_row[0])
    new_refresh = create_refresh_token(row[0])
    return TokenResponse(access_token=access, refresh_token=new_refresh)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    if not credentials:
        return None
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        return None
    return {"id": int(payload["sub"]), "username": payload.get("username")}


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Not an access token")
    return {"id": int(payload["sub"]), "username": payload.get("username")}
