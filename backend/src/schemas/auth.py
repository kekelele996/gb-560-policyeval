from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # 普通字符串 + 正则：演示域名 policyeval.demo 属保留 TLD，email-validator 会拒绝
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=1, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str


def serialize_user(user: Any) -> dict[str, Any]:
    from src.constants.roles import ROLE_LABELS

    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "role_label": ROLE_LABELS.get(user.role, user.role),
        "scope_namespaces": user.scope_namespaces,
        "is_active": user.is_active,
    }
