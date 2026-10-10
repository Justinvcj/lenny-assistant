import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ArrowUp } from 'lucide-react';

export interface ComposerProps {
  onSend?: (content: string) => void | Promise<void>;
  onSendMessage?: (content: string) => void | Promise<void>;
  inflight?: boolean;
  disabled?: boolean;
  isSending?: boolean;
  placeholder?: string;
  maxLength?: number;
  quickActions?: string[];
  onQuickAction?: (actionText: string) => void;
  initialValue?: string;
  autoFocus?: boolean;
}

const DEFAULT_QUICK_ACTIONS = [
  'Turn that into a Ship 30 essay',
  'Make a one-pager (HTML)',
];

export const Composer: React.FC<ComposerProps> = ({
  onSend,
  onSendMessage,
  inflight = false,
  disabled = false,
  isSending = false,
  placeholder = 'Ask a question about product, growth, or strategy... (Shift+Enter for newline)',
  maxLength = 4000,
  quickActions = DEFAULT_QUICK_ACTIONS,
  onQuickAction,
  initialValue = '',
  autoFocus = false,
}) => {
  const [content, setContent] = useState<string>(initialValue);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSendAction = onSend || onSendMessage;
  const isPending = inflight || isSending;

  useEffect(() => {
    if (initialValue !== undefined) {
      setContent(initialValue);
    }
  }, [initialValue]);

  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    const scrollHeight = textarea.scrollHeight;
    const targetHeight = Math.min(Math.max(scrollHeight, 52), 160);
    textarea.style.height = `${targetHeight}px`;
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [content, adjustHeight]);

  useEffect(() => {
    if (autoFocus && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [autoFocus]);

  const trimmed = content.trim();
  const isOverLimit = content.length > maxLength;
  const canSubmit = !isPending && !disabled && trimmed.length > 0 && !isOverLimit;

  const getCounterClass = (): string => {
    if (content.length >= maxLength) {
      return 'char-counter limit';
    }
    if (content.length > 3500) {
      return 'char-counter warning';
    }
    return 'char-counter';
  };

  const handleSubmit = () => {
    if (!canSubmit || !handleSendAction) return;
    const messageToSend = trimmed;
    setContent('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    handleSendAction(messageToSend);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing) return;

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleChipClick = (action: string) => {
    if (isPending || disabled) return;
    if (onQuickAction) {
      onQuickAction(action);
    } else if (handleSendAction) {
      handleSendAction(action);
    }
  };

  return (
    <div className="composer-dock" data-testid="composer-dock">
      <div className="composer-box">
        <textarea
          ref={textareaRef}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={isPending || disabled}
          className="composer-textarea"
          rows={1}
          aria-label="Message Lenny Growth Assistant"
          aria-invalid={isOverLimit}
          data-testid="composer-textarea"
        />

        <div className="composer-controls">
          <span
            className={getCounterClass()}
            data-testid="char-counter"
            aria-live="polite"
          >
            {content.length.toLocaleString()} / {maxLength.toLocaleString()}
          </span>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="btn-send"
            aria-label="Send message"
            data-testid="composer-send-btn"
          >
            <ArrowUp size={18} aria-hidden="true" />
          </button>
        </div>
      </div>

      {quickActions && quickActions.length > 0 && (
        <div className="quick-actions" role="group" aria-label="Quick action suggestions">
          {quickActions.map((action) => (
            <button
              key={action}
              type="button"
              className="quick-action-chip"
              disabled={isPending || disabled}
              onClick={() => handleChipClick(action)}
              data-testid={`quick-action-${action.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
            >
              {action}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default Composer;
