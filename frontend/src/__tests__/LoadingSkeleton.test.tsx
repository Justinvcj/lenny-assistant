import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { LoadingSkeleton } from '../components/LoadingSkeleton';

describe('LoadingSkeleton Component', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders skeleton bubble, initial elapsed timer at 0s, and default stage text', () => {
    const handleCancel = vi.fn();
    render(<LoadingSkeleton onCancel={handleCancel} />);

    expect(screen.getByTestId('loading-skeleton-bubble')).toBeInTheDocument();
    expect(screen.getByTestId('skeleton-stage-text')).toHaveTextContent('Searching transcripts...');
    expect(screen.getByTestId('skeleton-elapsed-timer')).toHaveTextContent('(0s)');
    expect(screen.getByTestId('skeleton-cancel-btn')).toBeInTheDocument();
  });

  it('increments elapsed timer and transitions stage text after 4 seconds', () => {
    const handleCancel = vi.fn();
    render(<LoadingSkeleton onCancel={handleCancel} />);

    expect(screen.getByTestId('skeleton-stage-text')).toHaveTextContent('Searching transcripts...');
    expect(screen.getByTestId('skeleton-elapsed-timer')).toHaveTextContent('(0s)');

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByTestId('skeleton-elapsed-timer')).toHaveTextContent('(2s)');
    expect(screen.getByTestId('skeleton-stage-text')).toHaveTextContent('Searching transcripts...');

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByTestId('skeleton-elapsed-timer')).toHaveTextContent('(4s)');
    expect(screen.getByTestId('skeleton-stage-text')).toHaveTextContent('Synthesizing answer...');
  });

  it('calls onCancel callback when Cancel button is clicked', async () => {
    vi.useRealTimers(); // User event works with real timers
    const user = userEvent.setup();
    const handleCancel = vi.fn();
    render(<LoadingSkeleton onCancel={handleCancel} />);

    const cancelBtn = screen.getByTestId('skeleton-cancel-btn');
    await user.click(cancelBtn);

    expect(handleCancel).toHaveBeenCalledTimes(1);
  });

  it('respects explicit stage prop and elapsedSeconds prop', () => {
    const handleCancel = vi.fn();
    render(
      <LoadingSkeleton
        onCancel={handleCancel}
        stage="Custom stage..."
        elapsedSeconds={12}
      />
    );

    expect(screen.getByTestId('skeleton-stage-text')).toHaveTextContent('Custom stage...');
    expect(screen.getByTestId('skeleton-elapsed-timer')).toHaveTextContent('(12s)');
  });
});
