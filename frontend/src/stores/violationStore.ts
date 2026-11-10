import { create } from 'zustand';
import { runApi, type ViolationFilters } from '../api/run';
import { errorMessage } from '../utils/errorMessage';
import type {
  Advice,
  Paginated,
  Violation,
  ViolationDetail,
  ViolationStatus,
  ViolationSummary,
} from '../types/models';

interface ViolationState {
  items: Violation[];
  total: number;
  pages: number;
  filters: ViolationFilters;
  summary: ViolationSummary | null;
  detail: ViolationDetail | null;
  advice: Advice | null;
  loading: boolean;
  detailLoading: boolean;
  error: string | null;
  load: (filters?: Partial<ViolationFilters>) => Promise<void>;
  loadSummary: (runId?: string) => Promise<ViolationSummary | null>;
  open: (id: string) => Promise<ViolationDetail | null>;
  close: () => void;
  generatePatch: (id: string) => Promise<Advice | null>;
  setStatus: (id: string, status: ViolationStatus) => Promise<void>;
  setFilters: (next: Partial<ViolationFilters>) => void;
}

export const useViolationStore = create<ViolationState>((set, get) => ({
  items: [],
  total: 0,
  pages: 0,
  filters: { page: 1, page_size: 20 },
  summary: null,
  detail: null,
  advice: null,
  loading: false,
  detailLoading: false,
  error: null,
  load: async (next = {}) => {
    const filters = { ...get().filters, ...next };
    set({ loading: true, error: null, filters });
    try {
      const response: Paginated<Violation> = await runApi.violations(filters);
      set({ items: response.items, total: response.total, pages: response.pages, loading: false });
    } catch (error) {
      set({ loading: false, error: errorMessage(error) });
    }
  },
  loadSummary: async (runId) => {
    try {
      const summary = await runApi.violationSummary(runId);
      set({ summary });
      return summary;
    } catch (error) {
      set({ error: errorMessage(error) });
      return null;
    }
  },
  open: async (id) => {
    set({ detailLoading: true, error: null });
    try {
      const response = await runApi.violationDetail(id);
      set({ detail: response.violation, advice: response.violation.advice, detailLoading: false });
      return response.violation;
    } catch (error) {
      set({ detailLoading: false, error: errorMessage(error) });
      return null;
    }
  },
  close: () => set({ detail: null, advice: null }),
  generatePatch: async (id) => {
    try {
      const response = await runApi.generateRemediation(id);
      set({ advice: response.advice });
      return response.advice;
    } catch (error) {
      set({ error: errorMessage(error) });
      return null;
    }
  },
  setStatus: async (id, status) => {
    try {
      const response = await runApi.updateViolationStatus(id, status);
      set({ detail: response.violation });
      await get().load();
    } catch (error) {
      set({ error: errorMessage(error) });
    }
  },
  setFilters: (next) => set({ filters: { ...get().filters, ...next } }),
}));
