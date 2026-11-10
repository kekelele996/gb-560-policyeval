import { api } from './client';
import type { Bundle, BundleDetail } from '../types/models';

export const bundleApi = {
  list: () => api.get<{ items: Bundle[]; total: number }>('/bundles'),
  detail: (id: string) => api.get<BundleDetail>(`/bundles/${id}`),
  import: (payload: {
    name: string;
    source: string;
    cluster: string;
    k8s_version: string;
    file_count: number;
    yaml_text: string;
  }) => api.post<{ bundle: Bundle }>('/bundles', payload),
  doc: (id: string, kind: string, name: string, namespace?: string) => {
    const query = new URLSearchParams({ kind, name });
    if (namespace) query.set('namespace', namespace);
    return api.get<{ kind: string; name: string; namespace: string; doc_yaml: string }>(
      `/bundles/${id}/doc?${query.toString()}`,
    );
  },
};
