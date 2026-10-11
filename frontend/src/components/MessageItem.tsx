import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import { AlertTriangle, Clock, FileCode } from 'lucide-react';
import { Message, EXACT_REFUSAL_MESSAGE } from '../api';
import { CitationChips } from './CitationChips';
import { RefusalCard } from './RefusalCard';

export const formatLatency = (latencyMs?: number | null): string => {
  if (latencyMs === undefined || latencyMs === null || isNaN(latencyMs)) {
    return '';
  }
  return `${(latencyMs / 1000).toFixed(1)}s`;
};

export const isRefusalContent = (content: string): boolean => {
  if (!content) return false;
  return content.trim().replace(/\.$/, '') === EXACT_REFUSAL_MESSAGE.replace(/\.$/, '');
};

export interface MessageItemProps {
  message: Message;
  onCitationClick?: (citationNumber: number) => void;
  onOpenArtifact?: (artifact: any) => void;
}

export const MessageItem: React.FC<MessageItemProps> = ({
  message,
  onCitationClick,
  onOpenArtifact,
}) => {
  const isUser = message.role === 'user';
  const isRefusal = !isUser && isRefusalContent(message.content);
  const [activeCitation, setActiveCitation] = React.useState<number | null>(null);

  const handleInlineCitationClick = React.useCallback((citationNum: number) => {
    setActiveCitation(null);
    setTimeout(() => {
      setActiveCitation(citationNum);
    }, 0);
    if (onCitationClick) {
      onCitationClick(citationNum);
    }
  }, [onCitationClick]);

  // Transform [S1] -> [S1](#source-1) for inline interactive chip rendering
  const processedContent = useMemo(() => {
    if (isUser || isRefusal) return message.content;
    return message.content.replace(/\[S(\d+)\]/g, '[S$1](#source-$1)');
  }, [message.content, isUser, isRefusal]);

  // User Message
  if (isUser) {
    return (
      <div className="message-item">
        <div className="message-user" role="article" aria-label="User Message">
          <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{message.content}</p>
        </div>
      </div>
    );
  }

  // Assistant Refusal Card
  if (isRefusal) {
    return (
      <div className="message-item">
        <div className="message-assistant" role="article" aria-label="Assistant Refusal">
          <RefusalCard message={message.content} />
        </div>
      </div>
    );
  }

  // Assistant Answer
  const formattedLatency = formatLatency(message.latency_ms);

  const degradedReason = useMemo(() => {
    if (!message.degraded || !message.tool_trace) return null;
    for (const trace of message.tool_trace) {
      if (trace && trace.degraded_reason) {
        return String(trace.degraded_reason);
      }
    }
    return null;
  }, [message.degraded, message.tool_trace]);

  return (
    <div className="message-item">
      <div className="message-assistant" role="article" aria-label="Assistant Response">
        {/* Meta badges: Degraded mode, Warnings & Latency */}
        {(message.degraded || formattedLatency || (message.warnings && message.warnings.length > 0)) && (
          <div className="message-meta">
            {message.degraded && (
              <span
                className="badge-degraded"
                title={degradedReason ? `Degraded: ${degradedReason}` : "Answered in degraded fallback mode without agent runtime"}
              >
                <AlertTriangle size={12} style={{ marginRight: '4px' }} aria-hidden="true" />
                Degraded
              </span>
            )}
            {message.warnings && message.warnings.map((w, idx) => (
              <span
                key={idx}
                className="badge-warning"
                data-testid="unsupported-name-warning"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  fontSize: '0.75rem',
                  color: '#b45309',
                  backgroundColor: '#fef3c7',
                  border: '1px solid #fde68a',
                  padding: '2px 8px',
                  borderRadius: '12px',
                  fontWeight: 500,
                  gap: '4px',
                }}
                title={w}
              >
                <AlertTriangle size={12} aria-hidden="true" />
                {w}
              </span>
            ))}
            {formattedLatency && (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  fontSize: '0.75rem',
                  color: 'var(--text-muted)',
                  gap: '3px',
                }}
                title={`Generation latency: ${message.latency_ms}ms`}
              >
                <Clock size={12} aria-hidden="true" />
                {formattedLatency}
              </span>
            )}
          </div>
        )}

        {/* Safe Markdown Content */}
        <div className="message-body">
          <ReactMarkdown
            components={{
              a: ({ href, children, ...props }) => {
                // Inline citation link handler
                if (href && href.startsWith('#source-')) {
                  const citationNum = parseInt(href.replace('#source-', ''), 10);
                  return (
                    <button
                      type="button"
                      className="citation-chip"
                      onClick={() => handleInlineCitationClick(citationNum)}
                      aria-label={`Jump to source S${citationNum}`}
                    >
                      {children}
                    </button>
                  );
                }

                // Security check for external link protocols
                const safeHref = href && !href.trim().toLowerCase().startsWith('javascript:')
                  ? href
                  : '#';

                return (
                  <a
                    href={safeHref}
                    target="_blank"
                    rel="noopener noreferrer"
                    {...props}
                  >
                    {children}
                  </a>
                );
              },
            }}
          >
            {processedContent}
          </ReactMarkdown>
        </div>

        {/* Grounded Citations Accordion */}
        {message.citations && message.citations.length > 0 && (
          <CitationChips
            citations={message.citations}
            messageId={message.id}
            activeCitationNumber={activeCitation}
            onCitationSelect={onCitationClick}
          />
        )}

        {/* Associated Artifact Link Button */}
        {(message.artifact || (message.artifacts && message.artifacts.length > 0)) && (() => {
          const art = message.artifact || message.artifacts![0];
          const artTitle = art.title || 'Generated Artifact';
          return (
            <div style={{ marginTop: '0.75rem' }}>
              <button
                type="button"
                className="btn-open-artifact"
                onClick={() => onOpenArtifact?.(art)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.35rem 0.75rem',
                  backgroundColor: 'var(--bg-surface-inset)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--brand-accent)',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
                aria-label={`Open artifact: ${artTitle}`}
              >
                <FileCode size={14} aria-hidden="true" />
                <span>Open artifact: {artTitle}</span>
              </button>
            </div>
          );
        })()}
      </div>
    </div>
  );
};

export default MessageItem;
