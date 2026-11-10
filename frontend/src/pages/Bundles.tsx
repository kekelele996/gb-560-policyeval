import { useEffect, useState } from 'react';
import { ParseTree } from '../components/business/ParseTree';
import { EmptyState } from '../components/common/EmptyState';
import { useAuthStore } from '../stores/authStore';
import { useBundleStore } from '../stores/bundleStore';
import { bundleApi } from '../api/bundle';
import { errorMessage } from '../utils/errorMessage';
import { fmtDateTime } from '../utils/format';

/** 清单包解析页：左侧 YAML 原文 / 右侧文档树（kind/name/namespace）。 */
export const BundlesPage = () => {
  const can = useAuthStore((state) => state.can);
  const bundles = useBundleStore((state) => state.bundles);
  const active = useBundleStore((state) => state.active);
  const docYaml = useBundleStore((state) => state.activeDocYaml);
  const activeDocKey = useBundleStore((state) => state.activeDocKey);
  const loadBundles = useBundleStore((state) => state.loadBundles);
  const openDoc = useBundleStore((state) => state.openDoc);
  const loadActive = useBundleStore((state) => state.loadActive);
  const loading = useBundleStore((state) => state.loading);
  const [importOpen, setImportOpen] = useState(false);
  const [name, setName] = useState('lanchuan-prod 2027Q1');
  const [yamlText, setYamlText] = useState('');
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);

  useEffect(() => {
    void loadBundles();
  }, [loadBundles]);

  const quotaDocs = (active?.bundle.parsed_tree ?? []).filter(
    (doc) => doc.kind === 'ResourceQuota' || doc.kind === 'LimitRange',
  ).length;

  const onImport = async () => {
    setImporting(true);
    setImportError(null);
    try {
      await bundleApi.import({
        name,
        source: 'upload',
        cluster: 'lanchuan-prod-cn-shanghai',
        k8s_version: 'v1.29.4',
        file_count: Math.max(1, yamlText.split('---').length),
        yaml_text: yamlText,
      });
      setImportOpen(false);
      setYamlText('');
      await loadBundles();
    } catch (error) {
      setImportError(errorMessage(error));
    } finally {
      setImporting(false);
    }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="page-kicker">BUNDLE PARSING / 01</div>
          <h1 className="page-title">清单包解析</h1>
          <div className="page-note">
            GitOps 导出的多文档 YAML 由后端 PyYAML 真实解析；点右侧任意文档，左侧显示该文档原文。
          </div>
        </div>
        <span className="spacer" />
        <button className="btn ghost" onClick={() => setImportOpen((open) => !open)} data-testid="bundle-import-toggle">
          {importOpen ? '收起导入面板' : '导入新的 GitOps 清单'}
        </button>
      </div>

      <div className="metric-strip" data-testid="bundle-metrics">
        <div className="metric">
          <div className="metric-label">文档数</div>
          <div className="metric-value">{active?.doc_count ?? '—'}</div>
        </div>
        <div className="metric">
          <div className="metric-label">文件数</div>
          <div className="metric-value">{active?.bundle.file_count ?? '—'}</div>
        </div>
        <div className="metric">
          <div className="metric-label">命名空间</div>
          <div className="metric-value">{active?.namespace_count ?? '—'}</div>
        </div>
        <div className="metric">
          <div className="metric-label">配额类文档</div>
          <div className="metric-value">{quotaDocs}</div>
        </div>
        <div className="metric">
          <div className="metric-label">K8s 版本</div>
          <div className="metric-value" style={{ fontSize: 'var(--step-1)' }}>
            {active?.bundle.k8s_version ?? '—'}
          </div>
        </div>
      </div>

      {importOpen ? (
        <div className="panel" style={{ marginTop: 14 }}>
          <div className="panel-head">
            <h3 className="panel-title">导入清单包</h3>
            <span className="panel-step">POST /api/bundles</span>
          </div>
          <div className="split-even">
            <div className="stack">
              <div className="field">
                <label className="field-label">清单包名称</label>
                <input className="input" value={name} onChange={(event) => setName(event.target.value)} data-testid="bundle-name-input" />
              </div>
              <div className="field">
                <label className="field-label">YAML 原文（支持多文档 ---）</label>
                <textarea
                  className="textarea"
                  rows={9}
                  value={yamlText}
                  onChange={(event) => setYamlText(event.target.value)}
                  placeholder="apiVersion: apps/v1&#10;kind: Deployment&#10;..."
                  data-testid="bundle-yaml-input"
                />
              </div>
              <div className="btn-row">
                <button className="btn primary" onClick={onImport} disabled={importing || !can('bundles:import')} data-testid="bundle-import-submit">
                  {importing ? '解析中…' : '解析并导入'}
                </button>
                <span className="hint">导入会真实解析 YAML；同名清单包返回 409。</span>
              </div>
              {importError ? <div className="dsl-error" data-testid="bundle-import-error">{importError}</div> : null}
            </div>
            <div className="notice">
              上游是 GitOps 仓库导出的清单与配额快照；本页只做解析与文档树展示，评估在「评估运行」页发起。
              当前演示清单包为 12 个文件 / 120 个文档的合成数据（含 2 个 ResourceQuota、1 个 LimitRange、2 个故意超配额 ns）。
            </div>
          </div>
        </div>
      ) : null}

      {active ? (
        <div className="split" style={{ marginTop: 14 }}>
          <div className="panel">
            <div className="panel-head">
              <h3 className="panel-title">YAML 原文 · {activeDocKey ?? '未选中'}</h3>
              <span className="panel-step">PyYAML safe_load_all</span>
            </div>
            <pre className="yaml-view" data-testid="doc-yaml">
              {docYaml || '# 从右侧选择一个文档'}
            </pre>
          </div>
          <div className="panel">
            <div className="panel-head">
              <h3 className="panel-title">文档树</h3>
              <span className="panel-step">{active.doc_count} docs</span>
              <span className="spacer" />
              <span className="fresh">
                {active.bundle.source} · {fmtDateTime(active.bundle.imported_at)}
              </span>
            </div>
            <ParseTree
              groups={active.tree_groups}
              activeKey={activeDocKey}
              onSelect={(doc) => void openDoc(doc.kind, doc.name, doc.namespace)}
            />
          </div>
        </div>
      ) : loading ? (
        <div className="empty" style={{ marginTop: 14 }}>正在加载清单包…</div>
      ) : (
        <EmptyState title="还没有清单包" testId="bundles-empty">
          用 engineer/admin 账号在「导入新的 GitOps 清单」粘贴多文档 YAML，或等待 seed 完成。
        </EmptyState>
      )}
    </div>
  );
};
