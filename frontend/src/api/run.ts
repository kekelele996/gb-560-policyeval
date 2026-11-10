import { api } from './client';
import type {
  Advice,
  Paginated,
  Run,
  RunDetail,
  RunPayload,
  Violation,
  ViolationDetail,
  ViolationSummary,
  ViolationStatus,
} from '../types/models';

export interface ViolationFilters {
  page?: number;
  page_size?: number;
  run_id?: string;
  severity?: string;
  namespace?: string;
  status?: string;
  source?: string;
  keyword?: string;
}

const buildQuery = (filters: Record<string, string | number | undefined>): string => {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== '' && value !== null) query.set(key, String(value));
  });
  const text = query.toString();
  return text ? `?${text}` : '';
};

export const runApi = {
  list: (page = 1, pageSize = 20) =>
    api.get<Paginated<Run>>(`/runs?page=${page}&page_size=${pageSize}`),
  create: (bundle_id: string, policy_ids?: string[]) =>
    api.post<RunPayload>('/runs', { bundle_id, policy_ids }),
  detail: (id: string) => api.get<RunPayload>(`/runs/${id}`),
  retry: (id: string) => api.post<{ run: Run }>(`/runs/${id}/retry`),
  execute: (id: string) => api.post<RunPayload & { result?: unknown }>(`/runs/${id}/execute`),

  violations: (filters: ViolationFilters) =>
    api.get<Paginated<Violation>>(`/violations${buildQuery({ ...filters })}`),
  violationSummary: (run_id?: string) =>
    api.get<ViolationSummary>(`/violations/summary${run_id ? `?run_id=${run_id}` : ''}`),
  violationDetail: (id: string) =>
    api.get<{ violation: ViolationDetail }>(`/violations/${id}`),
  updateViolationStatus: (id: string, status: ViolationStatus, note = '') =>
    api.patch<{ violation: ViolationDetail }>(`/violations/${id}/status`, { status, note }),
  generateRemediation: (id: string, note = '') =>
    api.post<{ advice: Advice }>(`/violations/${id}/remediation`, { note }),
  remediation: (id: string) =>
    api.get<{ advice: Advice | null }>(`/violations/${id}/remediation`),
};
