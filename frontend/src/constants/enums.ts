/** 共享枚举（前端侧）：与 backend/src/constants/enums.py 一一对应。
 * 出现位置：SeverityTag / StatusPill / 各页面筛选 / README「枚举出现位置」。 */
import type { ExemptionStatus, Role, Severity, ViolationStatus, RunStatus } from '../types/models';

export const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low'];

export const SEVERITY_LABELS: Record<Severity, string> = {
  critical: '严重',
  high: '高',
  medium: '中',
  low: '低',
};

export const SEVERITY_ORDER: Record<Severity, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
};

export const SEVERITY_SIGNAL: Record<Severity, string> = {
  critical: 'red',
  high: 'amber',
  medium: 'amber',
  low: 'green',
};

export const VIOLATION_STATUSES: ViolationStatus[] = ['open', 'exception', 'fixed'];

export const VIOLATION_STATUS_LABELS: Record<ViolationStatus, string> = {
  open: '待整改',
  exception: '已豁免',
  fixed: '已修复',
};

export const RUN_STATUSES: RunStatus[] = ['running', 'done', 'failed'];

export const RUN_STATUS_LABELS: Record<RunStatus, string> = {
  running: '运行中',
  done: '已完成',
  failed: '失败',
};

export const EXEMPTION_STATUSES: ExemptionStatus[] = ['pending', 'approved', 'rejected', 'expired'];

export const EXEMPTION_STATUS_LABELS: Record<ExemptionStatus, string> = {
  pending: '待审批',
  approved: '已通过',
  rejected: '已驳回',
  expired: '已过期',
};

export const ROLE_LABELS: Record<Role, string> = {
  admin: '平台管理员',
  engineer: '策略工程师',
  owner: '业务团队 owner',
};

export const RULE_KIND_LABELS: Record<string, string> = {
  Pod: 'Pod',
  Deployment: 'Deployment',
  Namespace: 'Namespace',
  LimitRange: 'LimitRange',
};

export const SEVERITY_FROM_ENUM = {
  LOW: 'low',
  MEDIUM: 'medium',
  HIGH: 'high',
  CRITICAL: 'critical',
} as const;
