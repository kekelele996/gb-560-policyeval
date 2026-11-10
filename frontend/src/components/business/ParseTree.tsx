import type { BundleDoc } from '../../types/models';

interface Props {
  groups: { namespace: string; docs: BundleDoc[]; doc_count: number }[];
  activeKey: string | null;
  onSelect: (doc: BundleDoc) => void;
  testId?: string;
}

/** 清单解析树：bundles 页主视图（kind/name/namespace 三级信息）。 */
export const ParseTree = ({ groups, activeKey, onSelect, testId }: Props) => (
  <div className="tree" data-testid={testId ?? 'bundle-tree'}>
    {groups.map((group) => (
      <div className="tree-group" key={group.namespace}>
        <div className="tree-group-head">
          <span>{group.namespace || '(cluster)'}</span>
          <span>{group.doc_count} docs</span>
        </div>
        {group.docs.map((doc) => {
          const key = `${doc.kind}/${doc.namespace}/${doc.name}`;
          return (
            <div
              key={key}
              className={`tree-doc${activeKey === key ? ' active' : ''}`}
              onClick={() => onSelect(doc)}
              data-testid="doc-item"
            >
              <span className="tree-kind">{doc.kind}</span>
              <span className="tree-name">{doc.name}</span>
              <span className="tree-ns">{doc.namespace}</span>
            </div>
          );
        })}
      </div>
    ))}
  </div>
);
