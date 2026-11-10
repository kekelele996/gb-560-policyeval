"""RBAC 依赖：按能力矩阵校验角色。"""
from __future__ import annotations

from fastapi import Depends

from src.constants import error_codes as codes
from src.constants.roles import role_can
from src.middlewares.auth import get_current_user
from src.models.user import User
from src.utils.errors import AppError


def require(action: str):
    """用法：`user: User = Depends(require("runs:trigger"))`。"""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if not role_can(user.role, action):
            raise AppError(
                codes.FORBIDDEN,
                f"当前角色（{user.role}）无 {action} 权限",
                f"role={user.role} action={action}",
                extra={"action": action, "role": user.role},
            )
        return user

    return dependency
