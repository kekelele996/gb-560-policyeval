import { create } from 'zustand';
import { bundleApi } from '../api/bundle';
import { errorMessage } from '../utils/errorMessage';
import type { Bundle, BundleDetail } from '../types/models';

interface BundleState {
  bundles: Bundle[];
  active: BundleDetail | null;
  activeDocYaml: string;
  activeDocKey: string | null;
  loading: boolean;
  error: string | null;
  loadBundles: () => Promise<Bundle[]>;
  loadActive: (id: string) => Promise<BundleDetail | null>;
  openDoc: (kind: string, name: string, namespace: string) => Promise<void>;
  clearError: () => void;
}

export const useBundleStore = create<BundleState>((set, get) => ({
  bundles: [],
  active: null,
  activeDocYaml: '',
  activeDocKey: null,
  loading: false,
  error: null,
  loadBundles: async () => {
    set({ loading: true, error: null });
    try {
      const response = await bundleApi.list();
      set({ bundles: response.items, loading: false });
      const first = response.items[0];
      if (first && !get().active) await get().loadActive(first.id);
      return response.items;
    } catch (error) {
      set({ loading: false, error: errorMessage(error) });
      return [];
    }
  },
  loadActive: async (id) => {
    set({ loading: true, error: null });
    try {
      const detail = await bundleApi.detail(id);
      set({ active: detail, loading: false });
      const firstDoc = detail.tree_groups[0]?.docs[0];
      if (firstDoc) {
        await get().openDoc(firstDoc.kind, firstDoc.name, firstDoc.namespace);
      }
      return detail;
    } catch (error) {
      set({ loading: false, error: errorMessage(error) });
      return null;
    }
  },
  openDoc: async (kind, name, namespace) => {
    const active = get().active;
    if (!active) return;
    const key = `${kind}/${namespace}/${name}`;
    if (get().activeDocKey === key) return;
    try {
      const doc = await bundleApi.doc(active.bundle.id, kind, name, namespace);
      set({ activeDocYaml: doc.doc_yaml, activeDocKey: key });
    } catch (error) {
      set({ error: errorMessage(error) });
    }
  },
  clearError: () => set({ error: null }),
}));
