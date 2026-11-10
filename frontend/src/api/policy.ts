import { api } from './client';
import type { DryRunResult, Policy, ValidateResult } from '../types/models';

export const policyApi = {
  list: (enabled?: boolean) =>
    api.get<{ items: Policy[]; total: number }>(
      `/policies${enabled === undefined ? '' : `?enabled=${enabled}`}`,
    ),
  detail: (id: string) => api.get<{ policy: Policy }>(`/policies/${id}`),
  validate: (dsl_text: string) => api.post<ValidateResult>('/policies/validate', { dsl_text }),
  create: (payload: {
    code: string;
    title: string;
    severity: string;
    kind: string;
    dsl_text: string;
    description?: string;
    enabled?: boolean;
  }) => api.post<{ policy: Policy }>('/policies', payload),
  update: (id: string, payload: Partial<{
    title: string;
    severity: string;
    kind: string;
    dsl_text: string;
    enabled: boolean;
    description: string;
  }>) => api.put<{ policy: Policy }>(`/policies/${id}`, payload),
  dryRun: (id: string, bundle_id: string) =>
    api.post<DryRunResult>(`/policies/${id}/dry-run`, { bundle_id }),
  options: () =>
    api.get<{ items: { id: string; code: string; title: string; severity: string; enabled: boolean }[] }>(
      '/policies/options',
    ),
};
