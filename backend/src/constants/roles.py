"""RBAC 角色与能力矩阵。

与 frontend/src/constants/roles.ts 对应；users.role 取值范围：
admin（平台管理员）/ engineer（策略工程师）/ owner（业务团队 owner）。
"""
from __future__ import annotations

ROLE_ADMIN = "admin"
ROLE_ENGINEER = "engineer"
ROLE_OWNER = "owner"

ALL_ROLES: tuple[str, ...] = (ROLE_ADMIN, ROLE_ENGINEER, ROLE_OWNER)

PERMISSIONS: dict[str, tuple[str, ...]] = {
    "bundles:read": ALL_ROLES,
    "bundles:import": (ROLE_ADMIN, ROLE_ENGINEER),
    "policies:read": ALL_ROLES,
    "policies:write": (ROLE_ADMIN, ROLE_ENGINEER),
    "policies:validate": ALL_ROLES,
    "runs:read": ALL_ROLES,
    "runs:trigger": (ROLE_ADMIN, ROLE_ENGINEER),
    "runs:retry": (ROLE_ADMIN, ROLE_ENGINEER),
    "violations:read": ALL_ROLES,
    "violations:update_status": (ROLE_ADMIN, ROLE_ENGINEER, ROLE_OWNER),
    "violations:remediation": (ROLE_ADMIN, ROLE_ENGINEER),
    "exemptions:read": ALL_ROLES,
    "exemptions:request": (ROLE_ADMIN, ROLE_ENGINEER, ROLE_OWNER),
    "exemptions:approve": (ROLE_ADMIN,),
    "report:read": ALL_ROLES,
    "audit:read": (ROLE_ADMIN,),
}

ROLE_LABELS: dict[str, str] = {
    ROLE_ADMIN: "平台管理员",
    ROLE_ENGINEER: "策略工程师",
    ROLE_OWNER: "业务团队 owner",
}


def role_can(role: str, action: str) -> bool:
    return role in PERMISSIONS.get(action, ())


def role_permissions(role: str) -> list[str]:
    return [action for action, roles in PERMISSIONS.items() if role in roles]
