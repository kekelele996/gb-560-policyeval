import { create } from 'zustand';
import { runApi } from '../api/run';
import { errorMessage } from '../utils/errorMessage';
import type { Run, RunDetail } from '../types/models';

interface RunState {
  runs: Run[];
  active: Run | null;
  detail: RunDetail | null;
  loading: boolean;
  creating: boolean;
  error: string | null;
  loadRuns: () => Promise<Run[]>;
  select: (run: Run) => Promise<void>;
  create: (bundleId: string) => Promise<Run | null>;
  refreshActive: () => Promise<void>;
}

export const useRunStore = create<RunState>((set, get) => ({
  runs: [],
  active: null,
  detail: null,
  loading: false,
  creating: false,
  error: null,
  loadRuns: async () => {
    set({ loading: true, error: null });
    try {
      const response = await runApi.list(1, 30);
      const activeId = get().active?.id;
      const active = response.items.find((item) => item.id === activeId) ?? response.items[0] ?? null;
      set({ runs: response.items, active, loading: false });
      if (active) {
        const payload = await runApi.detail(active.id);
        set({ active: payload.run, detail: payload.detail });
      }
      return response.items;
    } catch (error) {
      set({ loading: false, error: errorMessage(error) });
      return [];
    }
  },
  select: async (run) => {
    set({ active: run });
    try {
      const payload = await runApi.detail(run.id);
      set({ active: payload.run, detail: payload.detail });
    } catch (error) {
      set({ error: errorMessage(error) });
    }
  },
  create: async (bundleId) => {
    set({ creating: true, error: null });
    try {
      const payload = await runApi.create(bundleId);
      set({ creating: false, active: payload.run, detail: payload.detail });
      await get().loadRuns();
      return payload.run;
    } catch (error) {
      set({ creating: false, error: errorMessage(error) });
      return null;
    }
  },
  refreshActive: async () => {
    const active = get().active;
    if (!active) return;
    try {
      const payload = await runApi.detail(active.id);
      set({ active: payload.run, detail: payload.detail });
      if (payload.run.status !== 'running') {
        // 运行结束后同步刷新列表里的状态灯，避免表格显示旧的 running
        const list = await runApi.list(1, 30);
        set({ runs: list.items });
      }
    } catch (error) {
      set({ error: errorMessage(error) });
    }
  },
}));
