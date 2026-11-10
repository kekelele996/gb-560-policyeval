import type { ReactNode } from 'react';

interface Props {
  title: string;
  children?: ReactNode;
  testId?: string;
}

/** 空状态教学：告诉使用者下一步该做什么，而不是一句"暂无数据"。 */
export const EmptyState = ({ title, children, testId }: Props) => (
  <div className="empty" data-testid={testId ?? 'empty-state'}>
    <strong>{title}</strong>
    {children}
  </div>
);
