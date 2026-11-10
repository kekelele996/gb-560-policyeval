import { create } from 'zustand';
import { policyApi } from '../api/policy';
import { errorMessage } from '../utils/errorMessage';
import type { DryRunResult, ParseError, Policy, ValidateResult } from '../types/models';

interface PolicyState {
  policies: Policy[];
  selected: Policy | null;
  draftDsl: string;
  validateResult: ValidateResult | null;
  validating: boolean;
  dryRun: DryRunResult | null;
  dryRunning: boolean;
  saving: boolean;
  error: string | null;
  loadPolicies: () => Promise<Policy[]>;
  select: (policy: Policy) => void;
  setDraft: (text: string) => void;
  validate: () => Promise<ValidateResult>;
  runDryRun: (bundleId: string) => Promise<DryRunResult | null>;
  save: () => Promise<Policy | null>;
  clearResult: () => void;
}

export const usePolicyStore = create<PolicyState>((set, get) => ({
  policies: [],
  selected: null,
  draftDsl: '',
  validateResult: null,
  validating: false,
  dryRun: null,
  dryRunning: false,
  saving: false,
  error: null,
  loadPolicies: async () => {
    try {
      const response = await policyApi.list();
      const current = get().selected;
      const selected = current
        ? response.items.find((item) => item.id === current.id) ?? response.items[0] ?? null
        : response.items[0] ?? null;
      set({
        policies: response.items,
        selected,
        draftDsl: selected ? selected.dsl_text : '',
        error: null,
      });
      return response.items;
    } catch (error) {
      set({ error: errorMessage(error) });
      return [];
    }
  },
  select: (policy) =>
    set({
      selected: policy,
      draftDsl: policy.dsl_text,
      validateResult: null,
      dryRun: null,
      error: null,
    }),
  setDraft: (text) => set({ draftDsl: text, validateResult: null }),
  validate: async () => {
    set({ validating: true, error: null });
    try {
      const result = await policyApi.validate(get().draftDsl);
      set({ validateResult: result, validating: false });
      return result;
    } catch (error) {
      set({ validating: false, error: errorMessage(error) });
      const fallback: ValidateResult = {
        ok: false,
        error: {
          message: errorMessage(error), line: 0, column: 0, expected: [], token: '', offset: 0, snippet: '',
        } as ParseError,
      };
      set({ validateResult: fallback });
      return fallback;
    }
  },
  runDryRun: async (bundleId) => {
    const selected = get().selected;
    if (!selected) return null;
    set({ dryRunning: true, error: null, dryRun: null });
    try {
      const result = await policyApi.dryRun(selected.id, bundleId);
      set({ dryRun: result, dryRunning: false });
      return result;
    } catch (error) {
      set({ dryRunning: false, error: errorMessage(error) });
      return null;
    }
  },
  save: async () => {
    const selected = get().selected;
    if (!selected) return null;
    set({ saving: true, error: null });
    try {
      const response = await policyApi.update(selected.id, { dsl_text: get().draftDsl });
      set((state) => ({
        saving: false,
        selected: response.policy,
        policies: state.policies.map((item) => (item.id === response.policy.id ? response.policy : item)),
      }));
      return response.policy;
    } catch (error) {
      set({ saving: false, error: errorMessage(error) });
      return null;
    }
  },
  clearResult: () => set({ validateResult: null, dryRun: null, error: null }),
}));
