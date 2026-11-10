import type { ValidateResult } from '../../types/models';

interface Props {
  value: string;
  onChange: (value: string) => void;
  onValidate: () => void;
  validating: boolean;
  validateResult: ValidateResult | null;
  onDryRun: () => void;
  dryRunning: boolean;
  storedSummary?: string | null;
  canSave: boolean;
  canDryRun: boolean;
  saving: boolean;
  dirty: boolean;
  onSave: () => void;
}

/** 策略 DSL 编辑器：实时调用后端手写解析器，失败展示行号/列号/期望 token。
 *  策略页与试运行结果共用本组件。 */
export const DslEditor = ({
  value,
  onChange,
  onValidate,
  validating,
  validateResult,
  onDryRun,
  dryRunning,
  storedSummary,
  canSave,
  canDryRun,
  saving,
  dirty,
  onSave,
}: Props) => {
  const error = validateResult && !validateResult.ok ? validateResult.error : null;
  const ok = validateResult?.ok;
  return (
    <div className="stack">
      <div className="field">
        <label className="field-label" htmlFor="dsl-input">
          策略 DSL（手写词法 + 递归下降解析；禁用 eval/exec）
        </label>
        <textarea
          id="dsl-input"
          className="textarea"
          data-testid="dsl-input"
          spellCheck={false}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          rows={5}
        />
      </div>
      <div className="btn-row">
        <button className="btn" onClick={onValidate} disabled={validating} data-testid="dsl-validate">
          {validating ? '解析中…' : '校验 DSL'}
        </button>
        <button
          className="btn primary"
          onClick={onDryRun}
          disabled={dryRunning || !canDryRun}
          data-testid="dsl-dryrun"
          title={canDryRun ? '对选中清单包试运行（不落库）' : '当前角色不可试运行'}
        >
          {dryRunning ? '试运行中…' : '试运行'}
        </button>
        <span className="spacer" />
        <button
          className="btn"
          onClick={onSave}
          disabled={saving || !canSave || !dirty}
          data-testid="dsl-save"
          title={canSave ? '保存并 bump 版本' : '当前角色无策略写权限'}
        >
          {saving ? '保存中…' : '保存策略'}
        </button>
      </div>

      {error ? (
        <div className="dsl-error" data-testid="dsl-error">
          <div>
            第 {error.line} 行第 {error.column} 列：{error.message}
          </div>
          {error.expected.length > 0 ? <div>期望 token：{error.expected.join(' / ')}</div> : null}
          {error.snippet ? <div style={{ marginTop: 6, whiteSpace: 'pre' }}>{error.snippet}</div> : null}
        </div>
      ) : null}
      {ok ? (
        <div className="dsl-ok" data-testid="dsl-ok">
          解析通过 · 谓词 {validateResult?.predicate_count} 个 · 路径 {validateResult?.path_count} 条 · 嵌套深度{' '}
          {validateResult?.max_depth}
        </div>
      ) : null}
      {ok && validateResult?.summary ? (
        <div className="ast-summary" data-testid="dsl-summary">
          AST · {validateResult.summary}
        </div>
      ) : null}
      {!ok && storedSummary ? (
        <div className="ast-summary" data-testid="dsl-summary">
          已落库 AST 摘要 · {storedSummary}
        </div>
      ) : null}
    </div>
  );
};
