from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def error_payload(code: str, message: str, detail: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if detail is not None:
        payload["detail"] = detail
    return payload


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, error: ApiError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=error.status_code,
            content=error_payload(error.code, error.message, error.message),
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(
        request: Request,
        error: HTTPException,
    ) -> JSONResponse:
        del request
        message = str(error.detail)
        code = "NOT_FOUND" if error.status_code == 404 else "HTTP_ERROR"
        return JSONResponse(
            status_code=error.status_code,
            content=error_payload(code, message, error.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=422,
            content=error_payload(
                "VALIDATION_ERROR",
                "Request validation failed.",
                error.errors(),
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        error: Exception,
    ) -> JSONResponse:
        del request
        logger.exception("Unhandled application exception", exc_info=error)
        return JSONResponse(
            status_code=500,
            content=error_payload("INTERNAL_ERROR", "Internal server error."),
        )
