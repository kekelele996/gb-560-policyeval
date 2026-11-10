import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { errorMessage } from '../utils/errorMessage';
import { useAuthStore } from '../stores/authStore';
import { tokenStore } from '../api/client';

const ACCOUNTS = [
  { role: '平台管理员 admin', email: 'admin@policyeval.demo', scope: '全部命名空间 + 豁免审批' },
  { role: '策略工程师 engineer', email: 'engineer@policyeval.demo', scope: '导入 / 写策略 / 跑评估' },
  { role: '业务 owner', email: 'owner@policyeval.demo', scope: '仅 lc-payments、lc-ml-serving' },
];

/** 登录页：左侧客户与工作流背景，右侧值班登录。 */
export const LoginPage = () => {
  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login);
  const user = useAuthStore((state) => state.user);
  const [email, setEmail] = useState('engineer@policyeval.demo');
  const [password, setPassword] = useState('Demo@2026');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (tokenStore.get() && user) navigate('/bundles', { replace: true });
  }, [user, navigate]);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate('/bundles', { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-wrap">
      <section className="login-brand">
        <div>
          <div className="brand-mark" style={{ width: 34, height: 34, fontSize: 12 }}>PV</div>
          <div className="page-kicker" style={{ marginTop: 22 }}>Lanchuan Bank · Cloud Native Platform</div>
          <h1 className="login-title">
            把 220 个命名空间的合规，
            <br />
            从 Confluence wiki 变成可机读的策略。
          </h1>
          <p className="login-sub">
            澜川银行云原生平台部承载 3 个生产集群、220 个命名空间、60 个业务系统，同时满足等保 2.0
            与 CIS Benchmark。过去策略是一份人读的 wiki，季度抽查 20 个 ns，同一违规跨命名空间重复 40
            次，审计前一个月突击整改。
          </p>
          <p className="login-sub" style={{ marginTop: 10 }}>
            现在：GitOps 导出的 YAML 清单 → 手写 DSL 解析与求值 → 配额真实聚合 → 违规 evidence 与
            patch 建议 → owner 豁免审批与合规报告。
          </p>
        </div>
        <div className="login-facts">
          <div>
            <div className="login-fact-value">3</div>
            <div className="login-fact-label">生产集群</div>
          </div>
          <div>
            <div className="login-fact-value">220</div>
            <div className="login-fact-label">命名空间</div>
          </div>
          <div>
            <div className="login-fact-value">60</div>
            <div className="login-fact-label">业务系统</div>
          </div>
        </div>
      </section>

      <section className="login-form-wrap">
        <form className="login-form" onSubmit={onSubmit}>
          <div>
            <div className="page-kicker">值班登录 / SHIFT LOGIN</div>
            <h2 style={{ margin: '6px 0 4px', fontSize: 'var(--step-2)' }}>policyeval 管制台</h2>
            <div className="dark-hint">使用演示账号登录；所有数据为仓库内合成 K8s 清单。</div>
          </div>
          <div className="field">
            <label className="field-label" htmlFor="email">值班邮箱</label>
            <input
              id="email"
              className="input"
              data-testid="login-email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="password">口令</label>
            <input
              id="password"
              className="input"
              data-testid="login-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />
          </div>
          {error ? (
            <div className="form-error" data-testid="login-error">
              {error}
            </div>
          ) : null}
          <button className="btn primary" type="submit" disabled={submitting} data-testid="login-submit">
            {submitting ? '登录中…' : '进入管制台'}
          </button>
          <div className="login-accounts">
            <span style={{ letterSpacing: '0.16em' }}>演示账号 / Demo@2026</span>
            {ACCOUNTS.map((item) => (
              <span key={item.email}>
                {item.email} — {item.role}（{item.scope}）
              </span>
            ))}
          </div>
        </form>
      </section>
    </div>
  );
};
