import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { ErrorBanner } from '../components/ErrorBanner';
import { ApiError } from '../api';

describe('ErrorBanner Component', () => {
  it('renders user-friendly message for 502 llm_unavailable and displays X-Request-ID', () => {
    const apiError = new ApiError(
      'llm_unavailable',
      'Ollama is down',
      502,
      'req-502-uuid'
    );

    render(<ErrorBanner error={apiError} />);

    expect(
      screen.getByText(/Ollama local LLM is unavailable. Please verify Ollama is running with qwen2.5:7b./i)
    ).toBeInTheDocument();
    expect(screen.getByText('Request ID: req-502-uuid')).toBeInTheDocument();
  });

  it('renders Retry button and fires onRetry handler', async () => {
    const user = userEvent.setup();
    const handleRetry = vi.fn();

    render(
      <ErrorBanner
        message="Something went wrong"
        requestId="req-123"
        onRetry={handleRetry}
      />
    );

    const retryBtn = screen.getByRole('button', { name: /Retry/i });
    await user.click(retryBtn);

    expect(handleRetry).toHaveBeenCalledTimes(1);
  });

  it('renders dismiss button and fires onDismiss handler', async () => {
    const user = userEvent.setup();
    const handleDismiss = vi.fn();

    render(
      <ErrorBanner
        message="Notice error"
        onDismiss={handleDismiss}
      />
    );

    const dismissBtn = screen.getByRole('button', { name: /Dismiss error notice/i });
    await user.click(dismissBtn);

    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });
});
