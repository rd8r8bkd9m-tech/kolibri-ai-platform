from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


@dataclass
class APIError(Exception):
    message: str
    status_code: int = 400
    type: str = "invalid_request_error"
    param: str | None = None
    code: str | None = None

    def body(self) -> dict[str, Any]:
        return {
            "error": {
                "message": self.message,
                "type": self.type,
                "param": self.param,
                "code": self.code,
            }
        }


async def api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.body())


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    location = first.get("loc", [])
    param = ".".join(str(part) for part in location if part not in {"body", "query", "path"}) or None
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "message": first.get("msg", "Invalid request"),
                "type": "invalid_request_error",
                "param": param,
                "code": "validation_error",
            }
        },
    )
