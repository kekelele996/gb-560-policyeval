import { useEffect } from 'react';
import { EmptyState } from '../components/common/EmptyState';
import { SeverityTag } from '../components/common/SeverityTag';
import { StatusPill } from '../components/common/StatusPill';
import { EXEMPTION_STATUSES, SEVERITIES, SEVERITY_LABELS } from '../constants/enums';
import { useAuthStore } from '../stores/authStore';
import { useExemptionStore } from '../stores/exemptionStore';
import { fmtDateTime } from '../utils/format';
import { NsHeatBar } from '../components/business/NsHeatBar';

/** 豁免与合规报告页：admin 审批豁免，导出 Markdown 合规报告。 */
export const ExemptionsPage = () => {
  const can = useAuthStore((state) => state.can);
  const items = useExemptionStore((state) => state.items);
  const report = useExemptionStore((state) => state.report);
  const loading = useExemptionStore((state) => state.loading);
  const acting = useExemptionStore((state) => state.acting);
  const error = useExemptionStore((state) => state.error);
  const load = useExemptionStore((state) => state.load);
  const loadReport = useExemptionStore((state) => state.loadReport);
  const decide = useExemptionStore((state) => state.decide);
  const exportReport = useExemptionStore((state) => state.exportReport);

  useEffect(() => {
    void load();
    void loadReport();
  }, [load, loadReport]);

  const counts = {
    pending: items.filter((item) => item.status === 'pending').length,
    approved: items.filter((item) => item.status === 'approved').length,
    expired: items.filter((item) => item.status === 'expired').length,
  };

  const heatItems = (report?.namespaces ?? []).map((row) => ({
    namespace: row.namespace,
    total: row.total,
    open: row.open,
  }));

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="page-kicker">EXEMPTIONS & COMPLIANCE / 05</div>
          <h1 className="page-title">豁免与合规报告</h1>
          <div className="page-note">
            豁免必须由业务 owner 申请、平台管理员审批，评估时自动把命中违规标为 exception；过期后恢复
            open。合规分 = 规则通过率（不按违规条数加权，避免用豁免洗分）。
          </div>
        </div>
        <span className="spacer" />
        <button className="btn ghost" onClick={() => void exportReport()} data-testid="export-report">
          导出 Markdown 报告
        </button>
      </div>

      <div className="metric-strip" data-testid="exemption-metrics">
        <div className="metric">
          <div className="metric-label">合规分</div>
          <div className="metric-value" data-testid="compliance-score" style={{ color: 'var(--signal-green)' }}>
            {report?.compliance_score ?? '—'}
            <small>/100</small>
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">待审批豁免</div>
          <div className="metric-value" style={{ color: 'var(--signal-amber)' }}>{counts.pending}</div>
        </div>
        <div className="metric">
          <div className="metric-label">已通过</div>
          <div className="metric-value">{counts.approved}</div>
        </div>
        <div className="metric">
          <div className="metric-label">已过期</div>
          <div className="metric-value">{counts.expired}</div>
        </div>
        <div className="metric">
          <div className="metric-label">待整改违规</div>
          <div className="metric-value">{report?.totals.open ?? '—'}</div>
        </div>
      </div>

      {error ? <div className="dsl-error" style={{ marginTop: 12 }}>{error}</div> : null}

      <div className="split" style={{ marginTop: 14, gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1.4fr)' }}>
        <div className="stack">
          <div className="panel">
            <div className="panel-head">
              <h3 className="panel-title">合规报告 · {report?.run.bundle_name ?? '—'}</h3>
              <span className="panel-step">最近一次已完成评估</span>
            </div>
            {report ? (
              <div className="stack">
                <div className="mono tiny">
                  运行 {report.run.id.slice(0, 8)} · 文档 {report.run.docs_evaluated} · 规则通过{' '}
                  {report.run.rules_passed}/{report.run.rules_evaluated} · 违规 {report.run.violation_count} · 生成于{' '}
                  {fmtDateTime(report.run.finished_at)}
                </div>
                <div className="hint">合规分口径：{report.score_formula}（不按违规条数加权）</div>
                <table className="table" data-testid="report-severity">
                  <thead>
                    <tr>
                      <th>严重度</th>
                      <th>条数</th>
                    </tr>
                  </thead>
                  <tbody>
                    {SEVERITIES.map((severity) => (
                      <tr key={severity}>
                        <td><SeverityTag severity={severity} /></td>
                        <td className="mono tiny">{report.severity[severity].count}</td>
                      </tr>
                    ))}
                    <tr>
                      <td className="mono tiny">合计</td>
                      <td className="mono tiny">{report.totals.violations}</td>
                    </tr>
                  </tbody>
                </table>
                <div className="mono tiny">
                  状态：待整改 {report.totals.open} · 已豁免 {report.totals.exception} · 已修复 {report.totals.fixed}
                </div>
                <div className="panel-head" style={{ marginTop: 6 }}>
                  <h3 className="panel-title">命名空间分布</h3>
                </div>
                <NsHeatBar items={heatItems} limit={8} testId="report-ns-heat" />
                {report.quota_hotspots.length > 0 ? (
                  <div className="notice">
                    超配额热点：
                    {report.quota_hotspots
                      .map((item) => {
                        const value = (raw: unknown): string => {
                          if (typeof raw === 'string') return raw;
                          if (raw && typeof raw === 'object' && 'display' in raw) {
                            return String((raw as { display: string }).display);
                          }
                          return '—';
                        };
                        return `${item.namespace} ${item.metric} ${value(item.used)}→${value(item.threshold)}`;
                      })
                      .join('；')}
                  </div>
                ) : null}
              </div>
            ) : (
              <EmptyState title="还没有已完成的评估运行" testId="report-empty" />
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <h3 className="panel-title">豁免清单</h3>
            <span className="panel-step">{loading ? '加载中' : `${items.length} 条`}</span>
            <span className="spacer" />
            {can('exemptions:approve') ? <span className="tag neutral">admin 可审批</span> : <span className="tag neutral">只读</span>}
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>策略</th>
                <th>命名空间 / 资源</th>
                <th>理由</th>
                <th>状态</th>
                <th>审批</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} data-testid="exemption-row">
                  <td>
                    <span className="mono tiny">{item.policy_code ?? '—'}</span>
                    {item.severity ? <SeverityTag severity={item.severity} withLabel={false} /> : null}
                  </td>
                  <td>
                    <div className="mono tiny">{item.namespace}</div>
                    <div className="hint">{item.resource_name}</div>
                  </td>
                  <td className="tiny" style={{ maxWidth: 190, overflow: 'hidden' }}>
                    <span title={item.reason}>{item.reason}</span>
                  </td>
                  <td>
                    <span className={`tag status-${item.status === 'approved' ? 'fixed' : item.status === 'expired' ? 'exception' : 'open'}`}>
                      {item.status_label}
                    </span>
                    <div className="hint">到期 {fmtDateTime(item.expires_at)}</div>
                  </td>
                  <td>
                    {can('exemptions:approve') && item.status === 'pending' ? (
                      <div className="btn-row">
                        <button
                          className="btn small primary"
                          disabled={acting}
                          onClick={() => void decide(item.id, 'approve', '平台审批通过')}
                          data-testid="exemption-approve"
                        >
                          通过
                        </button>
                        <button
                          className="btn small danger"
                          disabled={acting}
                          onClick={() => void decide(item.id, 'reject', '证据不足')}
                          data-testid="exemption-reject"
                        >
                          驳回
                        </button>
                      </div>
                    ) : (
                      <span className="hint" title={item.approved_by || ''}>
                        {item.approved_by ? item.approved_by.split('@')[0] : '—'}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {items.length === 0 && !loading ? (
            <EmptyState title="没有豁免申请" testId="exemptions-empty">
              业务 owner 在违规详情页提交豁免申请后，会出现在这里等待 admin 审批。
            </EmptyState>
          ) : null}
          <div className="hint" style={{ marginTop: 8 }}>
            审批动作写入 audit_log（action=exemptions.decide），并同步更新对应违规状态。
          </div>
        </div>
      </div>
    </div>
  );
};
