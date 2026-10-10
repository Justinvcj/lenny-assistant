import React from 'react';
import { AlertCircle, Lightbulb } from 'lucide-react';
import { EXACT_REFUSAL_MESSAGE } from '../api';

export const DEFAULT_REPHRASING_TIPS = [
  'Ask about core product management topics (PMF, retention, roadmap, pricing).',
  'Ask about specific podcast guests (e.g. Shreyas Doshi, Elena Verna, Brian Chesky).',
  'Try broader or alternative keywords related to tech leadership and team culture.',
] as const;

export interface RefusalCardProps {
  message?: string;
  tips?: string[];
  onTipClick?: (tip: string) => void;
}

export const RefusalCard: React.FC<RefusalCardProps> = ({
  message = EXACT_REFUSAL_MESSAGE,
  tips = DEFAULT_REPHRASING_TIPS as unknown as string[],
  onTipClick,
}) => {
  return (
    <div
      className="refusal-card"
      role="region"
      aria-label="Assistant Refusal Notice"
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.5rem' }}>
        <AlertCircle size={18} style={{ color: 'var(--text-muted)', flexShrink: 0 }} aria-hidden="true" />
        <p className="refusal-statement">{message}</p>
      </div>

      <div className="refusal-tips">
        <div className="refusal-tips-title" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <Lightbulb size={14} aria-hidden="true" />
          <span>Tips for better results:</span>
        </div>
        <ul className="refusal-tips-list">
          {tips.map((tip, index) => (
            <li
              key={index}
              style={{ cursor: onTipClick ? 'pointer' : 'default' }}
              onClick={() => onTipClick && onTipClick(tip)}
            >
              {tip}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

export default RefusalCard;
