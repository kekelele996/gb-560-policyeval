import { SEVERITY_LABELS } from '../../constants/enums';
import type { Severity } from '../../types/models';

interface Props {
  severity: Severity;
  count?: number;
  withLabel?: boolean;
}

/** 严重度标签：违规清单与合规报告共用（同一业务组件被两个页面引用）。 */
export const SeverityTag = ({ severity, count, withLabel = true }: Props) => (
  <span className={`tag sev-${severity}`} data-testid={`severity-${severity}`}>
    {withLabel ? SEVERITY_LABELS[severity] : severity.toUpperCase()}
    {typeof count === 'number' ? ` · ${count}` : ''}
  </span>
);
