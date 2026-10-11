import React, { useState, useEffect } from 'react';
import { Loader2, X } from 'lucide-react';

export interface LoadingSkeletonProps {
  onCancel: () => void;
  stage?: string;
  startTime?: number;
  elapsedSeconds?: number;
  className?: string;
}

export const LoadingSkeleton: React.FC<LoadingSkeletonProps> = ({
  onCancel,
  stage,
  startTime,
  elapsedSeconds: propElapsedSeconds,
  className = '',
}) => {
  const [internalElapsed, setInternalElapsed] = useState<number>(() => {
    if (propElapsedSeconds !== undefined) return propElapsedSeconds;
    return startTime ? Math.max(0, Math.floor((Date.now() - startTime) / 1000)) : 0;
  });

  useEffect(() => {
    if (propElapsedSeconds !== undefined) {
      setInternalElapsed(propElapsedSeconds);
      return;
    }

    const origin = startTime || Date.now();
    const updateTimer = () => {
      setInternalElapsed(Math.max(0, Math.floor((Date.now() - origin) / 1000)));
    };

    updateTimer();
    const timerInterval = setInterval(updateTimer, 1000);
    return () => clearInterval(timerInterval);
  }, [startTime, propElapsedSeconds]);

  const elapsed = propElapsedSeconds !== undefined ? propElapsedSeconds : internalElapsed;
  const currentStage = stage || (() => {
    if (elapsed < 4) return 'Searching transcripts...';
    if (elapsed < 15) return 'Synthesizing answer...';
    if (elapsed < 35) return 'Structuring outline & key points...';
    if (elapsed < 70) return 'Drafting grounded sections & citations...';
    if (elapsed < 110) return 'Validating length & Ship 30 rules...';
    return 'Polishing and formatting output...';
  })();

  return (
    <div
      className={`message-item ${className}`}
      data-testid="loading-skeleton-container"
    >
      <div
        className="message-assistant loading-skeleton"
        role="status"
        aria-live="polite"
        aria-busy="true"
        aria-label="Generating grounded response"
        data-testid="loading-skeleton-bubble"
      >
        <div className="skeleton-bar" style={{ width: '92%' }} data-testid="skeleton-bar-1" />
        <div className="skeleton-bar" style={{ width: '78%' }} data-testid="skeleton-bar-2" />
        <div className="skeleton-bar" style={{ width: '60%' }} data-testid="skeleton-bar-3" />

        <div className="skeleton-footer">
          <div className="skeleton-stage" data-testid="skeleton-stage">
            <Loader2
              size={14}
              className="animate-spin"
              aria-hidden="true"
              style={{ animation: 'spin 1s linear infinite' }}
            />
            <span data-testid="skeleton-stage-text">{currentStage}</span>
            <span
              className="skeleton-timer"
              data-testid="skeleton-elapsed-timer"
              style={{
                fontFamily: 'var(--font-mono)',
                color: 'var(--brand-accent)',
                fontWeight: 600,
                fontSize: '0.8rem',
              }}
            >
              ({elapsed}s)
            </span>
          </div>

          <button
            type="button"
            className="btn-cancel"
            onClick={onCancel}
            aria-label="Cancel generating answer"
            data-testid="skeleton-cancel-btn"
          >
            <X
              size={13}
              aria-hidden="true"
              style={{ marginRight: '4px', verticalAlign: 'text-top' }}
            />
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

export default LoadingSkeleton;
