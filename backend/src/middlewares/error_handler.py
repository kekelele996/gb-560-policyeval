"""统一异常处理：AppError -> JSON；参数校验/未知异常结构化。"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.constants import error_codes as codes
from src.utils.errors import AppError
from src.utils.logger import get_logger

logger = get_logger("policyeval.error")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", None)
        return JSONResponse(status_code=exc.http_status, content=exc.to_payload(trace_id))

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": codes.VALIDATION_ERROR,
                "message": "请求参数不合法",
                "detail": str(exc.errors()[:3]),
                "trace_id": getattr(request.state, "trace_id", None),
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": "HTTP_ERROR",
                "message": str(exc.detail),
                "detail": "",
                "trace_id": getattr(request.state, "trace_id", None),
            },
        )

    @app.exception_handler(Exception)
    async def handle_unknown(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "code": codes.INTERNAL_ERROR,
                "message": "服务内部错误",
                "detail": str(exc)[:300],
                "trace_id": getattr(request.state, "trace_id", None),
            },
        )
