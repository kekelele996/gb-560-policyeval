import { useEffect } from 'react';
import { DslEditor } from '../components/business/DslEditor';
import { EvidencePath } from '../components/business/EvidencePath';
import { EmptyState } from '../components/common/EmptyState';
import { SeverityTag } from '../components/common/SeverityTag';
import { useAuthStore } from '../stores/authStore';
import { useBundleStore } from '../stores/bundleStore';
import { usePolicyStore } from '../stores/policyStore';
import { fmtDateTimeFull } from '../utils/format';

/** 策略编辑器：DSL 实时解析错误定位 + 试运行 + 保存。 */
export const PoliciesPage = () => {
  const can = useAuthStore((state) => state.can);
  const policies = usePolicyStore((state) => state.policies);
  const selected = usePolicyStore((state) => state.selected);
  const draftDsl = usePolicyStore((state) => state.draftDsl);
  const validateResult = usePolicyStore((state) => state.validateResult);
  const validating = usePolicyStore((state) => state.validating);
  const dryRun = usePolicyStore((state) => state.dryRun);
  const dryRunning = usePolicyStore((state) => state.dryRunning);
  const saving = usePolicyStore((state) => state.saving);
  const error = usePolicyStore((state) => state.error);
  const loadPolicies = usePolicyStore((state) => state.loadPolicies);
  const select = usePolicyStore((state) => state.select);
  const setDraft = usePolicyStore((state) => state.setDraft);
  const validate = usePolicyStore((state) => state.validate);
  const runDryRun = usePolicyStore((state) => state.runDryRun);
  const save = usePolicyStore((state) => state.save);
  const bundles = useBundleStore((state) => state.bundles);
  const loadBundles = useBundleStore((state) => state.loadBundles);

  useEffect(() => {
    void loadPolicies();
    void loadBundles();
  }, [loadPolicies, loadBundles]);

  const bundleId = bundles[0]?.id;
  const dirty = selected ? draftDsl !== selected.dsl_text : false;

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="page-kicker">POLICY DSL / 02</div>
          <h1 className="page-title">策略编辑器</h1>
          <div className="page-note">
            手写词法器 + 递归下降解析器：`all/any/not`、比较、路径通配 `containers[].resources.limits.cpu`、
            hasKey/count/startsWith/matches。解析失败给出行列号与期望 token。
          </div>
        </div>
      </div>

      <div className="split" style={{ gridTemplateColumns: 'minmax(0, 360px) minmax(0, 1fr)' }}>
        <div className="panel">
          <div className="panel-head">
            <h3 className="panel-title">策略清单</h3>
            <span className="panel-step">{policies.length} 条</span>
          </div>
          <div className="stack" data-testid="policy-list">
            {policies.map((policy) => (
              <button
                key={policy.id}
                className={`tree-doc${selected?.id === policy.id ? ' active' : ''}`}
                style={{ textAlign: 'left', background: 'transparent', border: 0, width: '100%', whiteSpace: 'nowrap' }}
                onClick={() => select(policy)}
                data-testid={`policy-item-${policy.code}`}
              >
                <span className="tree-kind" style={{ width: 72 }}>{policy.code}</span>
                <span
                  className="tree-name"
                  style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}
                  title={policy.title}
                >
                  {policy.title}
                </span>
                {policy.parse_error ? <span className="tag sev-critical" title="DSL 解析失败样本">ERR</span> : null}
                {!policy.enabled ? <span className="tag neutral" title="默认 disabled">OFF</span> : null}
                <SeverityTag severity={policy.severity} withLabel={false} />
              </button>
            ))}
            {policies.length === 0 ? <EmptyState title="还没有策略" /> : null}
          </div>
        </div>

        <div className="stack">
          <div className="panel">
            <div className="panel-head">
              <h3 className="panel-title">编辑器 · {selected?.code ?? '—'}</h3>
              <span className="panel-step">version {selected?.version ?? '—'}</span>
              <span className="spacer" />
              <span className="fresh">
                {selected ? `${selected.kind} · 更新于 ${fmtDateTimeFull(selected.updated_at)}` : ''}
              </span>
            </div>
            {selected ? (
              <div className="stack">
                <div className="btn-row">
                  <SeverityTag severity={selected.severity} />
                  <span className="tag neutral">{selected.kind}</span>
                  <span className="tag neutral">{selected.enabled ? 'enabled' : 'disabled'}</span>
                  <span className="hint">{selected.description}</span>
                </div>
                <DslEditor
                  value={draftDsl}
                  onChange={setDraft}
                  onValidate={() => void validate()}
                  validating={validating}
                  validateResult={validateResult}
                  onDryRun={() => bundleId && void runDryRun(bundleId)}
                  dryRunning={dryRunning}
                  storedSummary={selected.ast_summary}
                  canSave={can('policies:write')}
                  canDryRun={Boolean(bundleId)}
                  saving={saving}
                  dirty={dirty}
                  onSave={() => void save()}
                />
                {error ? <div className="dsl-error">{error}</div> : null}
                {selected.parse_error ? (
                  <div className="dsl-error" data-testid="stored-parse-error">
                    已落库的解析失败诊断：第 {selected.parse_error.line} 行第 {selected.parse_error.column} 列 —{' '}
                    {selected.parse_error.message}（期望 {selected.parse_error.expected.join(' / ')}）
                  </div>
                ) : null}
              </div>
            ) : (
              <EmptyState title="选择左侧一条策略开始编辑" />
            )}
          </div>

          {dryRun ? (
            <div className="panel" data-testid="dryrun-result">
              <div className="panel-head">
                <h3 className="panel-title">试运行结果 · {dryRun.policy_code}</h3>
                <span className="panel-step">{dryRun.bundle_name}</span>
              </div>
              <div className="metric-strip" style={{ border: 0 }}>
                <div className="metric">
                  <div className="metric-label">求值文档</div>
                  <div className="metric-value">{dryRun.evaluated_docs}</div>
                </div>
                <div className="metric">
                  <div className="metric-label">通过</div>
                  <div className="metric-value" style={{ color: 'var(--signal-green)' }}>{dryRun.matched_docs}</div>
                </div>
                <div className="metric tone-red">
                  <div className="metric-label">命中违规</div>
                  <div className="metric-value" data-testid="dryrun-violations">{dryRun.violation_count}</div>
                </div>
              </div>
              <div className="stack" style={{ marginTop: 10 }}>
                {dryRun.violations_preview.slice(0, 2).map((item) => (
                  <div key={`${item.namespace}-${item.resource_name}`}>
                    <div className="mono tiny" style={{ marginBottom: 4 }}>
                      {item.resource_kind}/{item.namespace}/{item.resource_name}
                    </div>
                    <EvidencePath evidence={item.evidence} maxRows={6} />
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};
