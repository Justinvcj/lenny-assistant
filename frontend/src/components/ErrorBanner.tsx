import React from 'react';
import { AlertCircle, X, RotateCcw } from 'lucide-react';
import { ApiError } from '../api';

export interface ErrorBannerProps {
  error?: ApiError | Error | string | null;
  message?: string;
  requestId?: string | null;
  onRetry?: () => void;
  onDismiss?: () => void;
  className?: string;
}

export function formatFriendlyErrorMessage(
  error: ApiError | Error | string | null | undefined
): { message: string; requestId: string | null } {
  if (!error) {
    return { message: 'An unknown error occurred.', requestId: null };
  }

  if (typeof error === 'string') {
    return { message: error, requestId: null };
  }

  let extractedRequestId: string | null = null;
  let code = '';
  let statusCode = 0;

  if (error instanceof ApiError) {
    extractedRequestId = error.requestId || null;
    code = error.code || '';
    statusCode = error.statusCode || 0;
  }

  if (code === 'llm_unavailable' || statusCode === 502) {
    return {
      message: 'Ollama local LLM is unavailable. Please verify Ollama is running with qwen2.5:7b.',
      requestId: extractedRequestId,
    };
  }

  if (code === 'agent_timeout' || statusCode === 504) {
    return {
      message: 'Generation timed out. The local model took too long to complete the answer.',
      requestId: extractedRequestId,
    };
  }

  if (code === 'session_not_found' || statusCode === 404) {
    return {
      message: 'The chat session was not found or has expired.',
      requestId: extractedRequestId,
    };
  }

  if (code === 'validation_error' || statusCode === 422) {
    return {
      message: 'Message validation error: content exceeds the 4,000 character limit.',
      requestId: extractedRequestId,
    };
  }

  if (error.name === 'AbortError' || error.message?.includes('aborted')) {
    return {
      message: 'The request was cancelled by the user.',
      requestId: extractedRequestId,
    };
  }

  if (
    error.message?.includes('Failed to fetch') ||
    error.message?.includes('NetworkError') ||
    error.message?.includes('ECONNREFUSED')
  ) {
    return {
      message: 'Unable to reach the backend server at http://localhost:8000. Please check your connection.',
      requestId: extractedRequestId,
    };
  }

  return {
    message: error.message || 'An unexpected error occurred while communicating with the assistant.',
    requestId: extractedRequestId,
  };
}

export const ErrorBanner: React.FC<ErrorBannerProps> = ({
  error,
  message: explicitMessage,
  requestId: explicitRequestId,
  onRetry,
  onDismiss,
  className = '',
}) => {
  if (!error && !explicitMessage) return null;

  let displayMessage = explicitMessage;
  let resolvedRequestId = explicitRequestId || null;

  if (error) {
    const formatted = formatFriendlyErrorMessage(error);
    if (!displayMessage) {
      displayMessage = formatted.message;
    }
    if (!resolvedRequestId) {
      resolvedRequestId = formatted.requestId;
    }
  }

  return (
    <div
      className={`error-banner ${className}`}
      role="alert"
      aria-live="assertive"
      data-testid="error-banner"
    >
      <div className="error-banner-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <AlertCircle size={18} aria-hidden="true" style={{ flexShrink: 0, color: '#f87171' }} />
          <span className="error-banner-message" data-testid="error-message">
            {displayMessage}
          </span>
        </div>

        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss error notice"
            style={{
              background: 'transparent',
              border: 'none',
              color: '#fca5a5',
              cursor: 'pointer',
              padding: '0.2rem',
              borderRadius: '4px',
              display: 'flex',
              alignItems: 'center',
            }}
            data-testid="error-dismiss-btn"
          >
            <X size={16} aria-hidden="true" />
          </button>
        )}
      </div>

      {resolvedRequestId && (
        <div className="request-id" data-testid="error-request-id">
          Request ID: {resolvedRequestId}
        </div>
      )}

      {onRetry && (
        <button
          type="button"
          className="btn-retry"
          onClick={onRetry}
          data-testid="error-retry-btn"
        >
          <RotateCcw size={13} aria-hidden="true" style={{ marginRight: '4px', verticalAlign: 'text-top' }} />
          Retry
        </button>
      )}
    </div>
  );
};

export default ErrorBanner;
