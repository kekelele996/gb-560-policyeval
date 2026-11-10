import type { Severity } from '../types/models';
import { SEVERITY_ORDER } from '../constants/enums';

/** 后端时间是 MySQL DATETIME（UTC naive，无时区后缀）：补 Z 再按本地时区展示。 */
const parseDate = (value: string): Date => {
  const hasTimezone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(value);
  return new Date(hasTimezone ? value : `${value}Z`);
};

export const fmtDateTime = (value?: string | null): string => {
  if (!value) return '—';
  const date = parseDate(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
};

export const fmtDateTimeFull = (value?: string | null): string => {
  if (!value) return '—';
  const date = parseDate(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(date);
};

export const fmtDuration = (start?: string | null, end?: string | null): string => {
  if (!start || !end) return '—';
  const ms = parseDate(end).getTime() - parseDate(start).getTime();
  if (Number.isNaN(ms) || ms < 0) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
};

export const sortBySeverity = <T extends { severity: Severity }>(rows: T[]): T[] =>
  [...rows].sort((a, b) => SEVERITY_ORDER[b.severity] - SEVERITY_ORDER[a.severity]);

export const truncate = (value: unknown, max = 96): string => {
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  if (text === undefined) return '—';
  return text.length > max ? `${text.slice(0, max)}…` : text;
};

export const fmtPercent = (value?: number | null): string =>
  value === null || value === undefined ? '—' : `${value.toFixed(1)}%`;

export const fmtCount = (value?: number | null): string =>
  value === null || value === undefined ? '—' : String(value);
