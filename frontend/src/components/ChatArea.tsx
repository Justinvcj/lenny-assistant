import React, { useRef, useEffect, useState, useCallback } from 'react';
import { ArrowDown, WifiOff } from 'lucide-react';
import { Message } from '../api';
import { MessageItem } from './MessageItem';
import { EmptyState } from './EmptyState';

export interface ChatAreaProps {
  messages: Message[];
  isLoading?: boolean;
  isOffline?: boolean;
  autoScrollEnabled?: boolean;
  activeArtifactId?: string;
  onOpenArtifact?: (artifact: any) => void;
  onSelectStarterQuestion?: (question: string) => void;
  onCitationClick?: (citationNumber: number) => void;
  onRegenerate?: () => void;
  onEditMessage?: (content: string) => void;
  onToast?: (message: string) => void;
  loadingNode?: React.ReactNode;
  errorNode?: React.ReactNode;
  bannerNode?: React.ReactNode;
  children?: React.ReactNode;
}

export const ChatArea: React.FC<ChatAreaProps> = ({
  messages,
  isLoading = false,
  isOffline = false,
  autoScrollEnabled = true,
  loadingNode,
  errorNode,
  bannerNode,
  onOpenArtifact,
  onSelectStarterQuestion,
  onCitationClick,
  onRegenerate,
  onEditMessage,
  onToast,
  children,
}) => {
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [isScrolledUp, setIsScrolledUp] = useState<boolean>(false);

  const scrollToBottom = useCallback((smooth = true) => {
    const prefersReducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;

    bottomRef.current?.scrollIntoView({
      behavior: smooth && !prefersReducedMotion ? 'smooth' : 'auto',
      block: 'end',
    });
    setIsScrolledUp(false);
  }, []);

  const handleScroll = () => {
    const el = scrollAreaRef.current;
    if (!el) return;
    const scrollBottomOffset = el.scrollHeight - el.scrollTop - el.clientHeight;
    // If user scrolled up more than 120px from bottom, consider them detached from auto-scroll
    setIsScrolledUp(scrollBottomOffset > 120);
  };

  useEffect(() => {
    if (autoScrollEnabled && !isScrolledUp) {
      scrollToBottom();
    }
  }, [messages.length, isLoading, !!errorNode, !!bannerNode, autoScrollEnabled, isScrolledUp, scrollToBottom]);

  const isEmpty = messages.length === 0 && !isLoading;

  // Find index of the most recent assistant message for regenerate action
  const lastAssistantIdx = messages.map((m) => m.role).lastIndexOf('assistant');

  return (
    <main className="chat-viewport" role="main" aria-label="Conversation viewport">
      <div
        className="chat-scroll-area"
        ref={scrollAreaRef}
        onScroll={handleScroll}
      >
        <div className="chat-container">
          {/* Offline Banner */}
          {isOffline && (
            <div className="network-offline-banner" role="alert" data-testid="offline-banner">
              <WifiOff size={15} aria-hidden="true" />
              <span>Offline: Cannot connect to backend server. Retrying connection automatically...</span>
            </div>
          )}

          {bannerNode}
          {errorNode}

          {isEmpty ? (
            <EmptyState onSelectStarterQuestion={onSelectStarterQuestion} />
          ) : (
            <div
              className="message-list"
              role="log"
              aria-live="polite"
              aria-atomic="false"
              aria-relevant="additions"
            >
              {messages.map((message, idx) => (
                <MessageItem
                  key={message.id}
                  message={message}
                  onCitationClick={onCitationClick}
                  onOpenArtifact={onOpenArtifact}
                  onRegenerate={idx === lastAssistantIdx ? onRegenerate : undefined}
                  onEdit={onEditMessage}
                  onToast={onToast}
                />
              ))}

              {isLoading && loadingNode}

              <div ref={bottomRef} style={{ height: '1px' }} aria-hidden="true" />
            </div>
          )}
        </div>
      </div>

      {/* Floating Scroll to Bottom Button */}
      {isScrolledUp && !isEmpty && (
        <button
          type="button"
          className="btn-scroll-bottom"
          onClick={() => scrollToBottom(true)}
          aria-label="Scroll to bottom"
          title="Scroll to bottom"
        >
          <ArrowDown size={14} aria-hidden="true" />
          <span>New messages</span>
        </button>
      )}

      {children}
    </main>
  );
};

export default ChatArea;
