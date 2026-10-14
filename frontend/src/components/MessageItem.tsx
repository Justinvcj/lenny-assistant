import React, { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { AlertTriangle, FileCode } from 'lucide-react';
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

const CodeBlock: React.FC<{ language?: string; code: string }> = ({ language, code }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.warn('Failed to copy code snippet:', err);
    }
  };

  return (
    <div className="code-block-wrapper">
      <div className="code-block-header">
        <span className="code-block-lang">{language || 'code'}</span>
        <button
          type="button"
          className="code-copy-btn"
          onClick={handleCopy}
          aria-label="Copy code snippet"
        >
          <span className="code-copy-icon" aria-hidden="true">{copied ? '✓' : '⧉'}</span>
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
};

export interface MessageItemProps {
  message: Message;
  onCitationClick?: (citationNumber: number) => void;
  onOpenArtifact?: (artifact: any) => void;
  onRegenerate?: () => void;
  onEdit?: (content: string) => void;
  onToast?: (msg: string) => void;
}

export const MessageItem: React.FC<MessageItemProps> = ({
  message,
  onCitationClick,
  onOpenArtifact,
  onRegenerate,
  onEdit,
  onToast,
}) => {
  const isUser = message.role === 'user';
  const isRefusal = !isUser && isRefusalContent(message.content);
  const [activeCitation, setActiveCitation] = useState<number | null>(null);
  const [copiedMessage, setCopiedMessage] = useState(false);
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(() => {
    if (typeof window === 'undefined' || !window.localStorage) return null;
    return (window.localStorage.getItem(`lenny_fb_${message.id}`) as any) || null;
  });

  const handleInlineCitationClick = React.useCallback((citationNum: number) => {
    setActiveCitation(null);
    setTimeout(() => {
      setActiveCitation(citationNum);
    }, 0);
    if (onCitationClick) {
      onCitationClick(citationNum);
    }
  }, [onCitationClick]);

  const handleCopyMessage = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopiedMessage(true);
      onToast?.('Copied message to clipboard');
      setTimeout(() => setCopiedMessage(false), 2000);
    } catch (err) {
      console.warn('Failed to copy message:', err);
    }
  };

  const handleFeedback = (type: 'up' | 'down') => {
    const next = feedback === type ? null : type;
    setFeedback(next);
    if (typeof window !== 'undefined' && window.localStorage) {
      if (next) {
        window.localStorage.setItem(`lenny_fb_${message.id}`, next);
      } else {
        window.localStorage.removeItem(`lenny_fb_${message.id}`);
      }
    }
    if (next === 'up') onToast?.('Feedback saved: Helpful response');
    if (next === 'down') onToast?.('Feedback saved: Needs improvement');
  };

  // Transform [S1] -> [S1](#source-1) for inline interactive chip rendering
  const processedContent = useMemo(() => {
    if (isUser || isRefusal) return message.content;
    return message.content.replace(/\[S(\d+)\]/g, '[S$1](#source-$1)');
  }, [message.content, isUser, isRefusal]);

  // User Message
  if (isUser) {
    return (
      <div className="message-item user-message-wrapper">
        <div className="message-user" role="article" aria-label="User Message">
          <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{message.content}</p>
          <div className="user-message-actions">
            <button
              type="button"
              className="btn-user-action"
              onClick={handleCopyMessage}
              aria-label="Copy prompt text"
              title="Copy prompt"
            >
              <span aria-hidden="true" style={{ fontSize: '12px' }}>⧉</span>
            </button>
            {onEdit && (
              <button
                type="button"
                className="btn-user-action"
                onClick={() => onEdit(message.content)}
                aria-label="Edit message"
                title="Edit message"
              >
                <span aria-hidden="true" style={{ fontSize: '12px' }}>✎</span>
              </button>
            )}
          </div>
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
        {/* Assistant Header: Avatar, Name & Action Bar */}
        <div className="assistant-header-row">
          <div className="assistant-identity">
            <div className="assistant-avatar" aria-hidden="true">
              <span className="avatar-sparkle">✦</span>
            </div>
            <span className="assistant-name">Lenny Assistant</span>

            {/* Meta badges: Degraded mode, Warnings & Latency */}
            {message.degraded && (
              <span
                className="badge-degraded"
                title={degradedReason ? `Degraded: ${degradedReason}` : "Answered in degraded fallback mode without agent runtime"}
              >
                <AlertTriangle size={11} style={{ marginRight: '3px' }} aria-hidden="true" />
                Degraded
              </span>
            )}
            {message.warnings && message.warnings.map((w, idx) => (
              <span
                key={idx}
                className="badge-warning"
                data-testid="unsupported-name-warning"
                title={w}
              >
                <AlertTriangle size={11} aria-hidden="true" />
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
                <span className="latency-icon" aria-hidden="true">⏱</span>
                {formattedLatency}
              </span>
            )}
          </div>

          <div className="message-action-bar">
            <button
              type="button"
              className="btn-msg-action"
              onClick={handleCopyMessage}
              aria-label="Copy message text"
              title="Copy answer"
            >
              <span className="btn-msg-icon" aria-hidden="true">{copiedMessage ? '✓' : '⧉'}</span>
              <span>{copiedMessage ? 'Copied' : 'Copy'}</span>
            </button>

            {onRegenerate && (
              <button
                type="button"
                className="btn-msg-action"
                onClick={onRegenerate}
                aria-label="Regenerate response"
                title="Regenerate answer"
              >
                <span aria-hidden="true" style={{ fontSize: '13px' }}>↻</span>
                <span>Regenerate</span>
              </button>
            )}

            <button
              type="button"
              className={`btn-msg-action-icon ${feedback === 'up' ? 'active-feedback' : ''}`}
              onClick={() => handleFeedback('up')}
              aria-label="Thumbs up good response"
              title="Good response"
            >
              <span aria-hidden="true" style={{ fontSize: '13px' }}>👍</span>
            </button>

            <button
              type="button"
              className={`btn-msg-action-icon ${feedback === 'down' ? 'active-feedback' : ''}`}
              onClick={() => handleFeedback('down')}
              aria-label="Thumbs down poor response"
              title="Poor response"
            >
              <span aria-hidden="true" style={{ fontSize: '13px' }}>👎</span>
            </button>
          </div>
        </div>

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
              code: ({ inline, className, children, ...props }: any) => {
                const match = /language-(\w+)/.exec(className || '');
                const codeString = String(children).replace(/\n$/, '');
                if (!inline && (match || codeString.includes('\n'))) {
                  return <CodeBlock language={match ? match[1] : ''} code={codeString} />;
                }
                return (
                  <code className={className} {...props}>
                    {children}
                  </code>
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
