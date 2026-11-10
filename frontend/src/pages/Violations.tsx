import { useEffect, useState } from 'react';
import { runApi } from '../api/run';
import { EvidencePath } from '../components/business/EvidencePath';
import { NsHeatBar } from '../components/business/NsHeatBar';
import { EmptyState } from '../components/common/EmptyState';
import { SeverityTag } from '../components/common/SeverityTag';
import { StatusPill } from '../components/common/StatusPill';
import { SEVERITIES, SEVERITY_LABELS, VIOLATION_STATUSES, VIOLATION_STATUS_LABELS } from '../constants/enums';
import { useAuthStore } from '../stores/authStore';
import { useViolationStore } from '../stores/violationStore';
import { errorMessage } from '../utils/errorMessage';
import { fmtDateTimeFull, fmtPercent } from '../utils/format';
import type { Severity, ViolationStatus } from '../types/models';

/** 违规清单页：按 severity / namespace 聚合 + evidence 数值 + patch 建议 + 豁免申请。 */
export const ViolationsPage = () => {
  const can = useAuthStore((state) => state.can);
  const user = useAuthStore((state) => state.user);
  const items = useViolationStore((state) => state.items);
  const total = useViolationStore((state) => state.total);
  const summary = useViolationStore((state) => state.summary);
  const detail = useViolationStore((state) => state.detail);
  const advice = useViolationStore((state) => state.advice);
  const loading = useViolationStore((state) => state.loading);
  const error = useViolationStore((state) => state.error);
  const load = useViolationStore((state) => state.load);
  const loadSummary = useViolationStore((state) => state.loadSummary);
  const open = useViolationStore((state) => state.open);
  const close = useViolationStore((state) => state.close);
  const generatePatch = useViolationStore((state) => state.generatePatch);
  const setStatus = useViolationStore((state) => state.setStatus);
  const [runId, setRunId] = useState<string | undefined>(undefined);
  const [severity, setSeverity] = useState<Severity | undefined>(undefined);
  const [statusFilter, setStatusFilter] = useState<ViolationStatus | undefined>(undefined);
  const [quotaOnly, setQuotaOnly] = useState(false);
  const [namespace, setNamespace] = useState<string | undefined>(undefined);
  const [exemptionReason, setExemptionReason] = useState('');
  const [exemptionError, setExemptionError] = useState<string | null>(null);
  const [exemptionOk, setExemptionOk] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const bootstrap = async () => {
      try {
        const runs = await runApi.list(1, 30);
        if (!alive) return;
        const latestDone = runs.items.find((run) => run.status === 'done') ?? runs.items[0];
        const rid = latestDone?.id;
        setRunId(rid);
        await loadSummary(rid);
        await load({ run_id: rid, page: 1 });
      } catch {
        await load({ page: 1 });
      }
    };
    void bootstrap();
    return () => {
      alive = false;
      close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refilter = async (next: {
    severity?: Severity | undefined;
    status?: ViolationStatus | undefined;
    quotaOnly?: boolean;
    namespace?: string | undefined;
  }) => {
    const appliedSeverity = 'severity' in next ? next.severity : severity;
    const appliedStatus = 'status' in next ? next.status : statusFilter;
    const appliedQuota = 'quotaOnly' in next ? next.quotaOnly : quotaOnly;
    const appliedNs = 'namespace' in next ? next.namespace : namespace;
    if ('severity' in next) setSeverity(next.severity);
    if ('status' in next) setStatusFilter(next.status);
    if ('quotaOnly' in next) setQuotaOnly(next.quotaOnly);
    if ('namespace' in next) setNamespace(next.namespace);
    await load({
      run_id: runId,
      page: 1,
      severity: appliedSeverity,
      status: appliedStatus,
      source: appliedQuota ? 'quota' : undefined,
      namespace: appliedNs,
    });
  };

  const onOpen = async (id: string) => {
    setExemptionError(null);
    setExemptionOk(null);
    setExemptionReason('');
    await open(id);
  };

  const onRequestExemption = async () => {
    if (!detail) return;
    setExemptionError(null);
    try {
      const { governanceApi } = await import('../api/governance');
      await governanceApi.request({ violation_id: detail.id, reason: exemptionReason || '业务窗口期申请豁免' });
      setExemptionOk('豁免申请已提交，等待 admin 审批');
      setExemptionReason('');
      await open(detail.id);
    } catch (err) {
      setExemptionError(errorMessage(err));
    }
  };

  const heatItems = (summary?.namespaces ?? []).map((row) => ({
    namespace: row.namespace,
    total: row.total,
    open: row.open,
  }));

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="page-kicker">VIOLATIONS / 04</div>
          <h1 className="page-title">违规清单</h1>
          <div className="page-note">
            同一策略跨命名空间重复命中已按策略聚合；展开任意违规可看到后端求值的字段路径与真实数值。
            当前默认展示最近一次已完成评估。
          </div>
        </div>
        <span className="spacer" />
        <div className="btn-row">
          <button className="btn small" onClick={() => void refilter({ severity: undefined })} data-testid="filter-all">
            全部严重度
          </button>
          {SEVERITIES.map((item) => (
            <button
              key={item}
              className={`btn small${severity === item ? ' primary' : ''}`}
              onClick={() => void refilter({ severity: item })}
              data-testid={`filter-severity-${item}`}
            >
              {SEVERITY_LABELS[item]}
            </button>
          ))}
          <button
            className={`btn small${quotaOnly ? ' primary' : ''}`}
            onClick={() => void refilter({ quotaOnly: !quotaOnly })}
            data-testid="filter-source-quota"
          >
            配额引擎
          </button>
        </div>
      </div>

      <div className="metric-strip" data-testid="violation-metrics">
        <div className="metric">
          <div className="metric-label">本轮违规</div>
          <div className="metric-value">{summary?.total ?? '—'}</div>
        </div>
        {SEVERITIES.map((item) => (
          <div key={item} className={`metric tone-${item === 'critical' ? 'red' : item === 'high' ? 'amber' : item === 'medium' ? 'amber' : 'green'}`}>
            <div className="metric-label">{SEVERITY_LABELS[item]} open</div>
            <div className="metric-value">{summary?.severity_counts[item] ?? '—'}</div>
          </div>
        ))}
        <div className="metric">
          <div className="metric-label">已豁免</div>
          <div className="metric-value">{summary?.status_counts.exception ?? '—'}</div>
        </div>
      </div>

      <div className="split" style={{ marginTop: 14, gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1.55fr)' }}>
        <div className="stack">
          <div className="panel">
            <div className="panel-head">
              <h3 className="panel-title">命名空间违规热度</h3>
              <span className="panel-step">待整改 / 总数</span>
            </div>
            <NsHeatBar items={heatItems} limit={10} />
          </div>
          <div className="panel">
            <div className="panel-head">
              <h3 className="panel-title">超配额热点 · 配额引擎</h3>
              <span className="panel-step">真实聚合</span>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>命名空间 / 维度</th>
                  <th>已用 → 阈值</th>
                  <th>超标</th>
                </tr>
              </thead>
              <tbody>
                {(summary?.quota_hotspots ?? []).map((row) => (
                  <tr
                    key={`${row.namespace}-${row.metric}`}
                    style={{ cursor: 'pointer' }}
                    onClick={() => row.violation_id && void onOpen(row.violation_id)}
                  >
                    <td>
                      <div className="mono tiny" style={{ whiteSpace: 'nowrap' }}>{row.namespace}</div>
                      <div className="hint">{row.metric}</div>
                    </td>
                    <td
                      className="mono tiny"
                      style={{ whiteSpace: 'nowrap' }}
                      title={`阈值来源 ${row.threshold_source}（${row.threshold?.display}）`}
                    >
                      {row.used?.display ?? '—'} → {row.threshold?.display ?? '—'}
                    </td>
                    <td className="mono tiny" style={{ color: 'oklch(0.44 0.16 25)', whiteSpace: 'nowrap' }}>
                      {fmtPercent(row.over_pct)}
                    </td>
                  </tr>
                ))}
                {(summary?.quota_hotspots ?? []).length === 0 ? (
                  <tr>
                    <td colSpan={5} className="hint">本轮没有超配额命名空间</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <h3 className="panel-title">违规明细</h3>
            <span className="panel-step">{loading ? '加载中' : `${total} 条`}</span>
            <span className="spacer" />
            <select
              className="select"
              value={statusFilter ?? ''}
              onChange={(event) => void refilter({ status: (event.target.value || undefined) as ViolationStatus | undefined })}
              data-testid="filter-status"
            >
              <option value="">全部状态</option>
              {VIOLATION_STATUSES.map((item) => (
                <option key={item} value={item}>{VIOLATION_STATUS_LABELS[item]}</option>
              ))}
            </select>
            <select
              className="select"
              value={namespace ?? ''}
              onChange={(event) => void refilter({ namespace: event.target.value || undefined })}
              data-testid="filter-namespace"
            >
              <option value="">全部命名空间</option>
              {(summary?.namespaces ?? []).map((row) => (
                <option key={row.namespace} value={row.namespace}>{row.namespace}</option>
              ))}
            </select>
          </div>
          {error ? <div className="dsl-error">{error}</div> : null}
          <table className="table">
            <thead>
              <tr>
                <th>策略</th>
                <th>资源</th>
                <th>命名空间</th>
                <th>严重度</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={item.id}
                  onClick={() => void onOpen(item.id)}
                  data-testid="violation-row"
                  className={detail?.id === item.id ? 'selected' : ''}
                  style={{ cursor: 'pointer' }}
                >
                  <td className="mono tiny" style={{ whiteSpace: 'nowrap' }}>{item.policy_code ?? item.rule_code}</td>
                  <td>
                    <span className="mono tiny">{item.resource_kind}</span>
                    <div className="hint">{item.resource_name}</div>
                  </td>
                  <td className="mono tiny">{item.namespace}</td>
                  <td><SeverityTag severity={item.severity} /></td>
                  <td>
                    <span className={`tag status-${item.status}`}>{item.status_label}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {items.length === 0 && !loading ? (
            <EmptyState title="当前筛选下没有违规" testId="violations-empty">
              试着点「全部严重度」或切换状态筛选；若刚跑完评估，刷新本页即可看到新结果。
            </EmptyState>
          ) : null}
        </div>
      </div>

      {detail ? (
        <div className="panel" style={{ marginTop: 14 }} data-testid="violation-detail">
          <div className="panel-head">
            <h3 className="panel-title">
              证据链 · {detail.policy_code ?? detail.rule_code}
            </h3>
            <span className="panel-step">
              {detail.resource_kind}/{detail.namespace}/{detail.resource_name}
            </span>
            <span className="spacer" />
            <button className="btn small" onClick={() => close()} data-testid="detail-close">收起</button>
          </div>
          <div className="split-even">
            <div className="stack">
              {detail.policy ? (
                <>
                  <div className="mono tiny">{detail.policy.title}</div>
                  <div className="ast-summary">{detail.policy.dsl_text}</div>
                </>
              ) : (
                <div className="mono tiny">配额引擎合成规则：{detail.rule_title || detail.rule_code}</div>
              )}
              <EvidencePath evidence={detail.evidence} maxRows={12} />
              <div className="btn-row">
                <button
                  className="btn primary small"
                  onClick={() => void generatePatch(detail.id)}
                  disabled={!can('violations:remediation')}
                  data-testid="gen-remediation"
                >
                  生成 patch 建议
                </button>
                <button
                  className="btn small"
                  onClick={() => void setStatus(detail.id, 'fixed')}
                  disabled={!can('violations:update_status') || detail.status === 'fixed'}
                  data-testid="mark-fixed"
                >
                  标记已修复
                </button>
                {detail.exemption ? (
                  <span className="tag status-exception">豁免 · {detail.exemption.status}</span>
                ) : detail.source === 'quota' ? (
                  <span className="hint">配额类违规不支持豁免：应调整 requests/limits 或由平台审批 ResourceQuota</span>
                ) : (
                  <>
                    <input
                      className="input"
                      style={{ minWidth: 220 }}
                      placeholder="豁免理由（owner 可申请）"
                      value={exemptionReason}
                      onChange={(event) => setExemptionReason(event.target.value)}
                      data-testid="exemption-reason"
                    />
                    <button
                      className="btn small"
                      onClick={() => void onRequestExemption()}
                      disabled={!can('exemptions:request')}
                      data-testid="exemption-request"
                      title="提交豁免申请（owner 可申请）"
                    >
                      申请豁免
                    </button>
                  </>
                )}
              </div>
              {exemptionError ? <div className="dsl-error">{exemptionError}</div> : null}
              {exemptionOk ? <div className="dsl-ok">{exemptionOk}</div> : null}
            </div>
            <div className="stack">
              <div className="mono tiny">
                状态 {detail.status_label} · 严重度 {SEVERITY_LABELS[detail.severity]} · 负责团队 {detail.owner_team} ·
                生成于 {fmtDateTimeFull(detail.created_at)}
              </div>
              {advice?.patch_yaml || detail.advice ? (
                <>
                  <div className="mono tiny">
                    patch 建议（effort {advice?.effort_level ?? detail.advice?.effort_level}，待业务团队合入 GitOps）
                  </div>
                  <pre className="patch-view" data-testid="patch-yaml">
                    {advice?.patch_yaml ?? detail.advice?.patch_yaml}
                  </pre>
                </>
              ) : (
                <div className="empty">
                  <strong>还没有 patch 建议</strong>
                  <span>点左侧「生成 patch 建议」，后端会依据该违规的 evidence 生成 Kubernetes patch 片段与影响面。</span>
                </div>
              )}
              {user?.role === 'owner' ? (
                <div className="notice">owner 只能查看自己命名空间的数据；审批豁免请找平台管理员。</div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};
