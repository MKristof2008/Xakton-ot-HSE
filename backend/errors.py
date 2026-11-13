"""Ошибки API в формате контракта: {"error": {"code": ..., "message": ...}}."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """Прикладная ошибка с кодом контракта и HTTP-статусом."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def error_response(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.code, exc.message, exc.status_code)


async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Голый HTTPException тоже отдаём в контрактном формате."""
    code = {400: "BAD_INPUT", 401: "BAD_INPUT", 403: "BAD_INPUT", 404: "NOT_FOUND",
            405: "BAD_INPUT", 409: "ALREADY_SOLD", 413: "TOO_LARGE",
            415: "UNSUPPORTED_TYPE"}.get(exc.status_code)
    if code is None:
        code = "INTERNAL" if exc.status_code >= 500 else "BAD_INPUT"
    detail: Any = exc.detail
    message = detail if isinstance(detail, str) else code.lower()
    return error_response(code, message, exc.status_code)


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Ошибки валидации не раскрывают внутренние детали — только поля."""
    parts = []
    for item in exc.errors()[:5]:
        loc = ".".join(str(part) for part in item.get("loc", ()) if part != "body")
        parts.append(loc or "запрос")
    message = "некорректные параметры: " + ", ".join(parts) if parts else "некорректный запрос"
    return error_response("BAD_INPUT", message, 400)


async def internal_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    """Внутренняя ошибка: наружу — только код, без трейсбека."""
    return error_response("INTERNAL", "внутренняя ошибка сервера", 500)