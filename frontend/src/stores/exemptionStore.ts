import { create } from 'zustand';
import { governanceApi } from '../api/governance';
import { errorMessage } from '../utils/errorMessage';
import type { ComplianceReport, Exemption, ExemptionStatus } from '../types/models';

interface ExemptionState {
  items: Exemption[];
  total: number;
  report: ComplianceReport | null;
  reportMarkdown: string;
  loading: boolean;
  acting: boolean;
  error: string | null;
  load: (status?: ExemptionStatus) => Promise<void>;
  loadReport: (runId?: string) => Promise<ComplianceReport | null>;
  decide: (id: string, decision: 'approve' | 'reject', note?: string) => Promise<boolean>;
  exportReport: (runId?: string) => Promise<void>;
}

export const useExemptionStore = create<ExemptionState>((set, get) => ({
  items: [],
  total: 0,
  report: null,
  reportMarkdown: '',
  loading: false,
  acting: false,
  error: null,
  load: async (status) => {
    set({ loading: true, error: null });
    try {
      const response = await governanceApi.exemptions({ status, page_size: 50 });
      set({ items: response.items, total: response.total, loading: false });
    } catch (error) {
      set({ loading: false, error: errorMessage(error) });
    }
  },
  loadReport: async (runId) => {
    try {
      const report = await governanceApi.report(runId);
      set({ report });
      return report;
    } catch (error) {
      set({ error: errorMessage(error) });
      return null;
    }
  },
  decide: async (id, decision, note = '') => {
    set({ acting: true, error: null });
    try {
      await governanceApi.decide(id, decision, note);
      set({ acting: false });
      await get().load();
      await get().loadReport();
      return true;
    } catch (error) {
      set({ acting: false, error: errorMessage(error) });
      return false;
    }
  },
  exportReport: async (runId) => {
    try {
      const markdown = await governanceApi.exportReport(runId);
      set({ reportMarkdown: markdown });
      const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `policyeval-compliance-${(runId ?? 'latest').slice(0, 8)}.md`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      set({ error: errorMessage(error) });
    }
  },
}));
