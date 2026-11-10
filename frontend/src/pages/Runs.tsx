import { useEffect } from 'react';
import { EmptyState } from '../components/common/EmptyState';
import { StatusPill } from '../components/common/StatusPill';
import { usePolling } from '../hooks/usePolling';
import { useAuthStore } from '../stores/authStore';
import { useBundleStore } from '../stores/bundleStore';
import { useRunStore } from '../stores/runStore';
import { fmtDateTime, fmtDuration } from '../utils/format';
import type { Run } from '../types/models';

const RUN_TONE = (status: Run['status']): 'green' | 'amber' | 'red' =>
  status === 'running' ? 'amber' : status === 'done' ? 'green' : 'red';

/** 评估运行页：发起真实评估（worker 执行），轮询状态并展示规则通过率。 */
export const RunsPage = () => {
  const can = useAuthStore((state) => state.can);
  const runs = useRunStore((state) => state.runs);
  const active = useRunStore((state) => state.active);
  const detail = useRunStore((state) => state.detail);
  const loading = useRunStore((state) => state.loading);
  const creating = useRunStore((state) => state.creating);
  const error = useRunStore((state) => state.error);
  const loadRuns = useRunStore((state) => state.loadRuns);
  const select = useRunStore((state) => state.select);
  const create = useRunStore((state) => state.create);
  const refreshActive = useRunStore((state) => state.refreshActive);
  const bundles = useBundleStore((state) => state.bundles);
  const loadBundles = useBundleStore((state) => state.loadBundles);

  useEffect(() => {
    void loadRuns();
    void loadBundles();
  }, [loadRuns, loadBundles]);

  const isRunning = active?.status === 'running';
  usePolling(() => {
    void refreshActive();
  }, Boolean(isRunning), 1500);

  const onCreate = async () => {
    const bundleId = bundles[0]?.id;
    if (!bundleId) return;
    await create(bundleId);
    await loadRuns();
  };

  const totalViolations = detail
    ? detail.severity_counts.critical + detail.severity_counts.high + detail.severity_counts.medium + detail.severity_counts.low
    : 0;
  const passedRules = detail?.rules.filter((rule) => rule.status === 'pass').length ?? 0;

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="page-kicker">EVALUATION RUNS / 03</div>
          <h1 className="page-title">评估运行</h1>
          <div className="page-note">
            一次评估 = 启用的 DSL 策略（真实求值）+ 配额引擎（资源规约聚合）。Celery worker
            执行，前端只轮询状态与展示后端结果。
          </div>
        </div>
        <span className="spacer" />
        <button
          className="btn primary"
          onClick={() => void onCreate()}
          disabled={creating || !can('runs:trigger') || bundles.length === 0}
          data-testid="run-create"
          title={can('runs:trigger') ? '对最新清单包发起全量评估' : '当前角色无 runs:trigger 权限'}
        >
          {creating ? '已提交，等待 worker…' : '发起全量评估'}
        </button>
      </div>

      <div className="metric-strip" data-testid="run-metrics">
        <div className="metric">
          <div className="metric-label">运行总数</div>
          <div className="metric-value">{runs.length}</div>
        </div>
        <div className="metric">
          <div className="metric-label">当前运行状态</div>
          <div className="metric-value" style={{ fontSize: 'var(--step-1)' }} data-testid="run-status-value">
            {active ? active.status_label : '—'}
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">规则通过</div>
          <div className="metric-value">
            {active ? `${active.rules_passed}/${active.rules_evaluated}` : '—'}
          </div>
        </div>
        <div className={`metric tone-red`}>
          <div className="metric-label">违规数</div>
          <div className="metric-value" data-testid="run-violation-count">
            {active ? active.violation_count : '—'}
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">耗时</div>
          <div className="metric-value" style={{ fontSize: 'var(--step-1)' }}>
            {active ? fmtDuration(active.started_at, active.finished_at) : '—'}
          </div>
        </div>
      </div>

      {error ? <div className="dsl-error" style={{ marginTop: 12 }}>{error}</div> : null}

      <div className="split" style={{ marginTop: 14 }}>
        <div className="panel">
          <div className="panel-head">
            <h3 className="panel-title">运行记录</h3>
            <span className="panel-step">{loading ? '加载中' : `${runs.length} 条`}</span>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>状态</th>
                <th>开始</th>
                <th>规则</th>
                <th>违规</th>
                <th>触发人</th>
                <th>run key</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr
                  key={run.id}
                  className={active?.id === run.id ? 'selected' : ''}
                  onClick={() => void select(run)}
                  data-testid="run-row"
                  style={{ cursor: 'pointer' }}
                >
                  <td>
                    <StatusPill
                      tone={RUN_TONE(run.status)}
                      label={run.status_label}
                      pulse={run.status === 'running'}
                    />
                  </td>
                  <td className="mono tiny">{fmtDateTime(run.started_at)}</td>
                  <td className="mono tiny">{run.rules_passed}/{run.rules_evaluated}</td>
                  <td className="mono tiny">{run.violation_count}</td>
                  <td className="mono tiny">{run.triggered_by.split('@')[0]}</td>
                  <td className="mono tiny">{run.run_key ?? run.id.slice(0, 8)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {runs.length === 0 ? <EmptyState title="还没有评估运行" /> : null}
        </div>

        <div className="panel">
          <div className="panel-head">
            <h3 className="panel-title">规则通过率</h3>
            <span className="panel-step">pass / fail</span>
          </div>
          {detail && active ? (
            <div className="stack">
              <div className="mono tiny">
                {active.status_label} · 文档 {active.docs_evaluated} · 违规 {active.violation_count} · 严重度{' '}
                {detail.severity_counts.critical}/{detail.severity_counts.high}/{detail.severity_counts.medium}/
                {detail.severity_counts.low}
              </div>
              <div className="pass-bar" data-testid="rule-pass-bar">
                {detail.rules.map((rule) => (
                  <span
                    key={rule.code}
                    className="pass-seg"
                    title={`${rule.code} · ${rule.status}`}
                    style={{
                      width: `${100 / Math.max(1, detail.rules.length)}%`,
                      background: rule.status === 'pass' ? 'var(--signal-green)' : 'var(--signal-red)',
                    }}
                  />
                ))}
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>规则</th>
                    <th>严重度</th>
                    <th>命中</th>
                    <th>结论</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.rules.map((rule) => (
                    <tr key={rule.code}>
                      <td>
                        <span className="mono tiny">{rule.code}</span>
                        <div className="hint">{rule.title}</div>
                      </td>
                      <td className="mono tiny">{rule.severity}</td>
                      <td className="mono tiny">{rule.violation_count}</td>
                      <td>
                        <StatusPill
                          tone={rule.status === 'pass' ? 'green' : 'red'}
                          label={rule.status === 'pass' ? '通过' : '命中'}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {active.status === 'failed' ? (
                <div className="notice">运行失败：{active.error_message}</div>
              ) : null}
            </div>
          ) : (
            <EmptyState title="选择一次运行查看规则通过率" />
          )}
        </div>
      </div>
    </div>
  );
};
