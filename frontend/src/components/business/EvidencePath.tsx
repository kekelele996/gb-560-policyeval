import type { Evidence } from '../../types/models';
import { truncate } from '../../utils/format';

interface Props {
  evidence: Evidence;
  maxRows?: number;
}

const SHORT_SOURCE: Record<string, string> = {
  ResourceQuota: 'RQ',
  LimitRange: 'LR',
  'platform-default': '平台默认',
};

const renderValue = (value: unknown): string => {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'string') return `"${value}"`;
  return truncate(value, 80);
};

/** 证据链渲染：DSL 求值 -> 叶子路径 + actual + expected；配额 -> used/threshold。
 *  违规页与策略试运行页共用。 */
export const EvidencePath = ({ evidence, maxRows = 12 }: Props) => {
  if (evidence.algorithm === 'quota-aggregation') {
    return (
      <div className="evidence-list" data-testid="evidence-list">
        <div className="evidence-row failed" data-testid="evidence-quota-summary">
          <span className="evidence-path mono">{evidence.metric ?? 'metric'}</span>
          <span className="evidence-val mono" data-testid="evidence-used">
            实际 {evidence.used?.display ?? '—'}
          </span>
          <span className="evidence-val mono" style={{ whiteSpace: 'nowrap' }}>
            阈值 {evidence.threshold?.display ?? '—'} ·{' '}
            {SHORT_SOURCE[evidence.threshold_source ?? ''] ?? evidence.threshold_source ?? '—'}
          </span>
          <span className="evidence-flag failed">
            {evidence.ratio !== null && evidence.ratio !== undefined ? `×${evidence.ratio}` : '超限'}
          </span>
        </div>
        <div className="evidence-row failed">
          <span className="evidence-path mono">超标幅度</span>
          <span className="evidence-val mono" data-testid="evidence-over-pct">
            {evidence.over_pct !== undefined ? `${evidence.over_pct}%` : '—'}
          </span>
          <span className="evidence-val mono" style={{ whiteSpace: 'nowrap' }}>
            {evidence.workload_count ?? '—'} 个工作负载 / {evidence.pod_count ?? '—'} Pod
          </span>
          <span className="evidence-flag failed"></span>
        </div>
        {evidence.formula ? (
          <div className="evidence-row passed" style={{ gridTemplateColumns: '1fr' }}>
            <span className="evidence-path mono">口径：{evidence.formula}</span>
          </div>
        ) : null}
      </div>
    );
  }
  const leaves = evidence.leaf_results ?? [];
  return (
    <div className="evidence-list" data-testid="evidence-list">
      {leaves.slice(0, maxRows).map((leaf, index) => (
        <div
          className={`evidence-row ${leaf.passed ? 'passed' : 'failed'}`}
          key={`${leaf.path}-${index}`}
          data-testid="evidence-row"
        >
          <span className="evidence-path mono" title={leaf.template}>
            {leaf.path || leaf.template}
          </span>
          <span className="evidence-val mono">实际 {renderValue(leaf.actual)}</span>
          <span className="evidence-val mono">期望 {leaf.op} {renderValue(leaf.expected)}</span>
          <span className={`evidence-flag ${leaf.passed ? 'passed' : 'failed'}`}>
            {leaf.passed ? 'PASS' : leaf.note ?? 'FAIL'}
          </span>
        </div>
      ))}
      {leaves.length === 0 ? (
        <div className="evidence-row failed">
          <span className="evidence-path mono">（无叶子证据，可能短路在更早的分支）</span>
        </div>
      ) : null}
      {(evidence.leaf_results_truncated || leaves.length > maxRows) ? (
        <div className="hint">
          仅展示前 {Math.min(leaves.length, maxRows)} 条失败叶子；共 {evidence.failed_leaves ?? leaves.length} 条失败 /{' '}
          {evidence.evaluated_leaves ?? leaves.length} 条求值。
        </div>
      ) : null}
      {evidence.warnings && evidence.warnings.length > 0 ? (
        <div className="hint">warnings：{evidence.warnings.join('、')}</div>
      ) : null}
    </div>
  );
};
