import { fmtCount } from '../../utils/format';

export interface NsHeatItem {
  namespace: string;
  total: number;
  open: number;
  over?: number;
}

interface Props {
  items: NsHeatItem[];
  limit?: number;
  testId?: string;
}

/** 命名空间热度条：违规页的聚合视图与合规报告共用。 */
export const NsHeatBar = ({ items, limit = 10, testId }: Props) => {
  const rows = [...items].sort((a, b) => b.open - a.open).slice(0, limit);
  const max = Math.max(1, ...rows.map((row) => row.open));
  return (
    <div className="heat-list" data-testid={testId ?? 'ns-heat'}>
      {rows.map((row) => {
        const tone = row.over ? 'over' : row.open > 0 ? 'warn' : '';
        return (
          <div className="heat-row" key={row.namespace} data-testid="ns-heat-row">
            <span className="heat-name" title={row.namespace}>
              {row.namespace}
            </span>
            <span className="heat-track">
              <span
                className={`heat-fill ${tone}`}
                style={{ width: `${Math.max(3, Math.round((row.open / max) * 100))}%` }}
              />
            </span>
            <span className="heat-val" title="待整改 / 总数">
              {fmtCount(row.open)}/{fmtCount(row.total)}
            </span>
          </div>
        );
      })}
    </div>
  );
};
