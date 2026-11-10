import { useEffect, useState, type ReactNode } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { governanceApi } from '../../api/governance';
import { ROLE_LABELS, SEVERITY_LABELS } from '../../constants/enums';
import { useAuthStore } from '../../stores/authStore';
import type { MetaSummary } from '../../types/models';
import { fmtDateTime } from '../../utils/format';
import { StatusPill } from '../common/StatusPill';

const NAV = [
  { to: '/bundles', label: '清单包解析', key: 'bundles' },
  { to: '/policies', label: '策略编辑器', key: 'policies' },
  { to: '/runs', label: '评估运行', key: 'runs' },
  { to: '/violations', label: '违规清单', key: 'violations' },
  { to: '/exemptions', label: '豁免与报告', key: 'exemptions' },
];

/** 「调度管制台」外壳：左命名空间/席位导航 240px · 中主工作区 · 右状态灯与计数。 */
export const ControlShell = ({ children }: { children: ReactNode }) => {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const navigate = useNavigate();
  const location = useLocation();
  const [meta, setMeta] = useState<MetaSummary | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const summary = await governanceApi.summary();
        if (alive) setMeta(summary);
      } catch {
        /* 右侧状态灯失败不影响主工作区 */
      }
    };
    void load();
    const timer = window.setInterval(load, 20000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [location.pathname]);

  const hint = (key: string): string => {
    if (!meta) return '';
    if (key === 'bundles') return String(meta.bundle.doc_count);
    if (key === 'policies') return `${meta.policies.enabled}/${meta.policies.total}`;
    if (key === 'runs') return String(meta.runs.total);
    if (key === 'violations') return String(meta.open_violations.total);
    if (key === 'exemptions') return String(meta.exemptions.pending);
    return '';
  };

  const latest = meta?.runs.latest;
  const runTone = latest?.status === 'running' ? 'amber' : latest?.status === 'failed' ? 'red' : 'green';
  const criticalOpen = meta?.open_violations.severity.critical ?? 0;
  const quotaTone = criticalOpen > 0 ? 'red' : (meta?.open_violations.total ?? 0) > 0 ? 'amber' : 'green';
  const clusterTone = 'green';

  const activeKey = NAV.find((item) => location.pathname.startsWith(item.to))?.key ?? 'bundles';

  return (
    <div className="shell" data-testid="shell">
      <div className="brand">
        <span className="brand-mark">PV</span>
        <div>
          <div className="brand-name">policyeval</div>
          <div className="brand-tag">澜川银行 · 云原生平台部</div>
        </div>
      </div>

      <div className="topbar">
        <span className="topbar-title">容器与 K8s 策略合规评估台</span>
        <span className="topbar-sub">CIS Benchmark / 等保 2.0 · 调度管制台</span>
        <span className="topbar-spacer" />
        <div className="topbar-actor">
          <StatusPill
            tone="grey"
            label={`${user ? ROLE_LABELS[user.role] : '未登录'}`}
            title="当前角色"
          />
          <span className="mono tiny muted">{user?.email ?? ''}</span>
          <button
            className="btn ghost small"
            onClick={() => {
              logout();
              navigate('/login', { replace: true });
            }}
            data-testid="logout"
          >
            退出
          </button>
        </div>
      </div>

      <div className="rail-top">
        <span className={`signal ${clusterTone}`} />
        <span>lanchuan-prod-cn-shanghai</span>
        <span style={{ marginLeft: 'auto' }}>{meta?.bundle.k8s_version ?? 'v1.29'}</span>
      </div>

      <nav className="nav">
        <div className="nav-label">管制席位</div>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            data-testid={`nav-${item.key}`}
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
          >
            <span>{item.label}</span>
            <span className="nav-hint">{hint(item.key)}</span>
          </NavLink>
        ))}
        <div className="nav-foot">
          <span>
            清单包 <span className="mono">{meta?.bundle.name ?? '—'}</span>
          </span>
          <span>
            文档 <span className="mono">{meta?.bundle.doc_count ?? '—'}</span> · 命名空间{' '}
            <span className="mono">{meta?.bundle.namespace_count ?? '—'}</span>
          </span>
          <span>
            策略 <span className="mono">{meta?.policies.total ?? '—'}</span>（解析失败{' '}
            <span className="mono">{meta?.policies.broken ?? '—'}</span>）
          </span>
        </div>
      </nav>

      <main className="main">{children}</main>

      <aside className="rail">
        <div className="panel-dark">
          <div className="panel-head">
            <h3 className="panel-title">席位信号</h3>
            <span className="panel-step">实时</span>
          </div>
          <div className="stack">
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <StatusPill tone={clusterTone} label="生产集群" />
              <span className="fresh">3 集群 / 220 ns</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <StatusPill
                tone={quotaTone}
                label="待整改违规"
                pulse={criticalOpen > 0}
              />
              <span className="fresh">critical {criticalOpen}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <StatusPill
                tone={runTone}
                label={latest?.status === 'running' ? '评估运行中' : '最近评估'}
                pulse={latest?.status === 'running'}
                testId="signal-run"
              />
              <span className="fresh mono">
                {latest ? `${latest.rules_passed}/${latest.rules_evaluated} 规则` : '—'}
              </span>
            </div>
          </div>
        </div>

        <div className="panel-dark" style={{ marginTop: 12 }}>
          <div className="panel-head">
            <h3 className="panel-title">待整改计数</h3>
          </div>
          <div className="stack mono tiny">
            {(['critical', 'high', 'medium', 'low'] as const).map((severity) => (
              <div key={severity} style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>{SEVERITY_LABELS[severity]}</span>
                <span>{meta?.open_violations.severity[severity] ?? '—'}</span>
              </div>
            ))}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                borderTop: '1px solid var(--ink-line)',
                paddingTop: 6,
              }}
            >
              <span>待审批豁免</span>
              <span>{meta?.exemptions.pending ?? '—'}</span>
            </div>
          </div>
        </div>

        <div className="panel-dark" style={{ marginTop: 12 }}>
          <div className="panel-head">
            <h3 className="panel-title">违规热点命名空间</h3>
          </div>
          <div className="stack mono tiny">
            {(meta?.open_violations.by_namespace ?? []).slice(0, 6).map((row) => (
              <div key={row.namespace} style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>{row.namespace}</span>
                <span>{row.count}</span>
              </div>
            ))}
            {(meta?.open_violations.by_namespace ?? []).length === 0 ? (
              <span className="muted">本轮没有待整改违规</span>
            ) : null}
          </div>
        </div>

        <div style={{ marginTop: 12 }} className="fresh">
          评估触发人 {latest?.started_at ? fmtDateTime(latest.started_at) : '—'}
        </div>
      </aside>
    </div>
  );
};
