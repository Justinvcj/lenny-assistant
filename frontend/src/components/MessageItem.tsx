import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import { AlertTriangle, Clock } from 'lucide-react';
import { Message, EXACT_REFUSAL_MESSAGE } from '../api';
import { CitationChips } from './CitationChips';
import { RefusalCard } from './RefusalCard';

export const formatLatency = (latencyMs?: number | null): string => {
  if (latencyMs === undefined || latencyMs === null || isNaN(latencyMs)) {
    return '';
  }
  return `${(latencyMs / 1000).toFixed(1)}s`;
};

export interface MessageItemProps {
  message: Message;
  onCitationClick?: (citationNumber: number) => void;
}

export const MessageItem: React.FC<MessageItemProps> = ({
  message,
  onCitationClick,
}) => {
  const isUser = message.role === 'user';
  const isRefusal = !isUser && message.content.trim() === EXACT_REFUSAL_MESSAGE;

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

  return (
    <div className="message-item">
      <div className="message-assistant" role="article" aria-label="Assistant Response">
        {/* Meta badges: Degraded mode & Latency */}
        {(message.degraded || formattedLatency) && (
          <div className="message-meta">
            {message.degraded && (
              <span
                className="badge-degraded"
                title="Answered in degraded fallback mode without agent runtime"
              >
                <AlertTriangle size={12} style={{ marginRight: '4px' }} aria-hidden="true" />
                Degraded
              </span>
            )}
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
                      onClick={() => onCitationClick && onCitationClick(citationNum)}
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
            onCitationSelect={onCitationClick}
          />
        )}
      </div>
    </div>
  );
};

export default MessageItem;
