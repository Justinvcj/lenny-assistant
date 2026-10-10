import React, { useRef, useEffect } from 'react';
import { Message } from '../api';
import { MessageItem } from './MessageItem';
import { EmptyState } from './EmptyState';

export interface ChatAreaProps {
  messages: Message[];
  isLoading?: boolean;
  activeArtifactId?: string;
  onOpenArtifact?: (artifact: any) => void;
  onSelectStarterQuestion?: (question: string) => void;
  onCitationClick?: (citationNumber: number) => void;
  loadingNode?: React.ReactNode;
  errorNode?: React.ReactNode;
  children?: React.ReactNode;
}

export const ChatArea: React.FC<ChatAreaProps> = ({
  messages,
  isLoading = false,
  loadingNode,
  errorNode,
  onOpenArtifact,
  onSelectStarterQuestion,
  onCitationClick,
  children,
}) => {
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const prefersReducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;

    bottomRef.current?.scrollIntoView({
      behavior: prefersReducedMotion ? 'auto' : 'smooth',
      block: 'end',
    });
  }, [messages.length, isLoading, !!errorNode]);

  const isEmpty = messages.length === 0 && !isLoading;

  return (
    <main className="chat-viewport" role="main" aria-label="Conversation viewport">
      <div className="chat-scroll-area" ref={scrollAreaRef}>
        <div className="chat-container">
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
              {messages.map((message) => (
                <MessageItem
                  key={message.id}
                  message={message}
                  onCitationClick={onCitationClick}
                  onOpenArtifact={onOpenArtifact}
                />
              ))}

              {isLoading && loadingNode}

              <div ref={bottomRef} style={{ height: '1px' }} aria-hidden="true" />
            </div>
          )}
        </div>
      </div>

      {children}
    </main>
  );
};

export default ChatArea;
