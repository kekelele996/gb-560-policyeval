import { api } from './client';
import type {
  ComplianceReport,
  Exemption,
  ExemptionStatus,
  MetaSummary,
  Paginated,
} from '../types/models';

export const governanceApi = {
  summary: () => api.get<MetaSummary>('/meta/summary'),
  exemptions: (params: { page?: number; page_size?: number; status?: string; namespace?: string } = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== '') query.set(key, String(value));
    });
    const text = query.toString();
    return api.get<Paginated<Exemption>>(`/exemptions${text ? `?${text}` : ''}`);
  },
  request: (payload: { violation_id: string; reason: string; expires_at?: string }) =>
    api.post<{ exemption: Exemption }>('/exemptions', payload),
  decide: (id: string, decision: 'approve' | 'reject', note = '') =>
    api.post<{ exemption: Exemption }>(`/exemptions/${id}/decision`, { decision, note }),
  report: (runId?: string) =>
    api.get<ComplianceReport>(`/reports/compliance${runId ? `?run_id=${runId}` : ''}`),
  exportReport: (runId?: string) =>
    api.rawGet(`/reports/compliance/export${runId ? `?run_id=${runId}` : ''}`),
};

export const exemptionStatusLabel = (status: ExemptionStatus): string =>
  ({ pending: '待审批', approved: '已通过', rejected: '已驳回', expired: '已过期' })[status];
