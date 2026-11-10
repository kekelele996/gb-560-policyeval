/** 前端能力矩阵：与 backend/src/constants/roles.py PERMISSIONS 对应。
 * 仅用于按钮显隐；真正的 403 由后端强制。 */
import type { Role } from '../types/models';

export type Permission =
  | 'bundles:read'
  | 'bundles:import'
  | 'policies:read'
  | 'policies:write'
  | 'policies:validate'
  | 'runs:read'
  | 'runs:trigger'
  | 'runs:retry'
  | 'violations:read'
  | 'violations:update_status'
  | 'violations:remediation'
  | 'exemptions:read'
  | 'exemptions:request'
  | 'exemptions:approve'
  | 'report:read'
  | 'audit:read';

export const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  admin: [
    'bundles:read', 'bundles:import', 'policies:read', 'policies:write', 'policies:validate',
    'runs:read', 'runs:trigger', 'runs:retry', 'violations:read', 'violations:update_status',
    'violations:remediation', 'exemptions:read', 'exemptions:request', 'exemptions:approve',
    'report:read', 'audit:read',
  ],
  engineer: [
    'bundles:read', 'bundles:import', 'policies:read', 'policies:write', 'policies:validate',
    'runs:read', 'runs:trigger', 'runs:retry', 'violations:read', 'violations:update_status',
    'violations:remediation', 'exemptions:read', 'exemptions:request', 'report:read',
  ],
  owner: [
    'bundles:read', 'policies:read', 'policies:validate', 'runs:read',
    'violations:read', 'violations:update_status', 'exemptions:read', 'exemptions:request',
    'report:read',
  ],
};

export const can = (role: Role | undefined | null, permission: Permission): boolean => {
  if (!role) return false;
  return ROLE_PERMISSIONS[role].includes(permission);
};
