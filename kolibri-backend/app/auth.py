"""JWT authentication for Kolibri."""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from jwt import InvalidTokenError
import bcrypt
from fastapi import Cookie, Depends, HTTPException, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db

DEVELOPMENT_SECRET = "kolibri-dev-secret-change-in-production"
SECRET_KEY = os.getenv("JWT_SECRET_KEY", DEVELOPMENT_SECRET)
ALGORITHM = "HS256"
TOKEN_ISSUER = "kolibri"
TOKEN_AUDIENCE = "kolibri-portal"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", "1440"))

security = HTTPBearer(auto_error=False)
OPERATOR_ROLES = frozenset({"owner", "superadmin"})
OPERATOR_CACHE_HEADERS = {"Cache-Control": "private, no-store"}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iss": TOKEN_ISSUER, "aud": TOKEN_AUDIENCE})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer=TOKEN_ISSUER,
            audience=TOKEN_AUDIENCE,
        )
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def validate_auth_configuration() -> None:
    production = bool(
        os.getenv("KOLIBRI_ACTIVE_RELEASE_ID", "").strip()
        or os.getenv("KOLIBRI_PUBLIC_BASE_URL", "").strip()
        or os.getenv("KOLIBRI_REQUIRE_SECURE_AUTH", "").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    if production and (SECRET_KEY == DEVELOPMENT_SECRET or len(SECRET_KEY.encode("utf-8")) < 32):
        raise RuntimeError("jwt_secret_not_configured")


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_cookie: Optional[str] = Cookie(None, alias="kolibri_auth"),
    db: Session = Depends(get_db),
):
    from app.models import UserDB
    token = credentials.credentials if credentials else auth_cookie
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    user = db.query(UserDB).filter(
        UserDB.id == user_id,
        UserDB.is_active.is_(True),
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_cookie: Optional[str] = Cookie(None, alias="kolibri_auth"),
    db: Session = Depends(get_db),
):
    from app.models import UserDB
    token = credentials.credentials if credentials else auth_cookie
    if not token:
        return None
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if user_id:
            return db.query(UserDB).filter(
                UserDB.id == user_id,
                UserDB.is_active.is_(True),
            ).first()
    except HTTPException:
        pass
    return None


def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_cookie: Optional[str] = Cookie(None, alias="kolibri_auth"),
    db: Session = Depends(get_db),
):
    """Required auth — raises 401 if no valid token."""
    from app.models import UserDB
    token = credentials.credentials if credentials else auth_cookie
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    user = db.query(UserDB).filter(
        UserDB.id == user_id,
        UserDB.is_active.is_(True),
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_operator_user(
    response: Response,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_cookie: Optional[str] = Cookie(None, alias="kolibri_auth"),
    db: Session = Depends(get_db),
):
    """Require an active persisted owner/admin account for operator surfaces.

    Browser route guards are UX only.  This dependency is the app-level
    authorization boundary for Control Center data and fails closed before an
    adapter or global aggregate is queried.
    """

    from app.models import UserDB

    response.headers.update(OPERATOR_CACHE_HEADERS)
    token = credentials.credentials if credentials else auth_cookie
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers=OPERATOR_CACHE_HEADERS,
        )
    try:
        payload = decode_token(token)
    except HTTPException as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.detail,
            headers=OPERATOR_CACHE_HEADERS,
        ) from exc
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers=OPERATOR_CACHE_HEADERS,
        )
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers=OPERATOR_CACHE_HEADERS,
        )
    if not bool(user.is_active):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive operator account",
            headers=OPERATOR_CACHE_HEADERS,
        )
    if str(user.role or "").strip().lower() not in OPERATOR_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator role required",
            headers=OPERATOR_CACHE_HEADERS,
        )
    return user
