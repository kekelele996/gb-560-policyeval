import type { ReactNode } from 'react';

type Tone = 'green' | 'amber' | 'red' | 'grey' | 'neutral';

interface Props {
  tone: Tone;
  label: ReactNode;
  pulse?: boolean;
  title?: string;
  testId?: string;
}

/** 信号灯状态徽标：三色信号灯只用于状态，不做装饰。 */
export const StatusPill = ({ tone, label, pulse = false, title, testId }: Props) => (
  <span
    className="mono tiny"
    title={title}
    data-testid={testId}
    style={{ display: 'inline-flex', alignItems: 'center', gap: 6, letterSpacing: '0.06em', whiteSpace: 'nowrap' }}
  >
    <span className={`signal ${tone}${pulse ? ' running' : ''}`} />
    {label}
  </span>
);
