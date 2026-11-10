"""认证：Bearer token -> request.state.user。

挂成 FastAPI 依赖而不是全局中间件：白名单靠路由声明，不依赖路径字符串匹配。
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants import error_codes as codes
from src.models.user import User
from src.utils.errors import AppError
from src.utils.jwt import decode_token


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    return header.split(" ", 1)[1].strip()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _extract_bearer(request)
    if not token:
        raise AppError(codes.AUTH_REQUIRED, "请先登录", "missing Authorization header")
    payload = decode_token(token)
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise AppError(codes.AUTH_INVALID, "登录状态无效，请重新登录", "user missing/inactive")
    request.state.user = user
    return user


def current_user_payload(user: User) -> dict[str, Any]:
    from src.schemas.auth import serialize_user

    return serialize_user(user)


def user_scope(user: User) -> list[str] | None:
    """owner 角色只读本命名空间；返回 None 表示不限。"""
    return user.scope_namespaces if user.role == "owner" else None


def enforce_namespace_scope(user: User, namespace: str) -> None:
    scope = user_scope(user)
    if scope and namespace not in scope:
        raise AppError(
            codes.FORBIDDEN,
            "当前账号无权访问该命名空间的数据",
            f"role={user.role} namespace={namespace} scope={scope}",
            extra={"namespace": namespace, "scope": scope},
        )
