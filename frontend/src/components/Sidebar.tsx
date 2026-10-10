import React, { useState, useEffect } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Session } from '../api';

export interface SidebarProps {
  sessions: Session[];
  activeSessionId: string | null;
  isOpen: boolean;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  onDeleteSession: (sessionId: string) => Promise<void> | void;
  onClose?: () => void;
}

export function formatRelativeTime(dateString: string): string {
  try {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    if (isNaN(diffMs) || diffMs < 0) return 'Just now';

    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHours = Math.floor(diffMin / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffSec < 60) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  } catch {
    return '';
  }
}

export const Sidebar: React.FC<SidebarProps> = ({
  sessions,
  activeSessionId,
  isOpen,
  onSelectSession,
  onNewChat,
  onDeleteSession,
}) => {
  const [sessionToDelete, setSessionToDelete] = useState<Session | null>(null);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);

  // Close modal on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && sessionToDelete) {
        setSessionToDelete(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [sessionToDelete]);

  const confirmDelete = async () => {
    if (!sessionToDelete) return;
    setIsDeleting(true);
    try {
      await onDeleteSession(sessionToDelete.id);
      setSessionToDelete(null);
    } finally {
      setIsDeleting(false);
    }
  };

  // Ensure sessions are sorted newest first
  const sortedSessions = [...sessions].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  return (
    <>
      <aside
        className={`app-sidebar ${isOpen ? 'open' : ''}`}
        aria-label="Session navigation"
      >
        <div className="sidebar-header">
          <button
            type="button"
            className="btn-new-chat"
            onClick={onNewChat}
            aria-label="Start a new chat session"
          >
            <Plus size={16} aria-hidden="true" />
            <span>New Chat</span>
          </button>
        </div>

        <div
          className="session-list"
          role="listbox"
          aria-label="Chat conversations"
        >
          {sortedSessions.length === 0 ? (
            <div
              style={{
                padding: '1.5rem 1rem',
                textAlign: 'center',
                color: 'var(--text-muted)',
                fontSize: '0.85rem',
              }}
            >
              No conversations yet
            </div>
          ) : (
            sortedSessions.map((session) => {
              const isActive = session.id === activeSessionId;
              const displayTitle = session.title || 'New Chat';
              const relativeTime = formatRelativeTime(session.created_at);

              return (
                <div
                  key={session.id}
                  role="option"
                  tabIndex={0}
                  aria-selected={isActive}
                  className={`session-item ${isActive ? 'active' : ''}`}
                  onClick={() => onSelectSession(session.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onSelectSession(session.id);
                    }
                  }}
                >
                  <div className="session-item-content">
                    <p className="session-item-title" title={displayTitle}>
                      {displayTitle}
                    </p>
                    <span className="session-item-time">{relativeTime}</span>
                  </div>

                  <button
                    type="button"
                    className="session-delete-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSessionToDelete(session);
                    }}
                    aria-label={`Delete chat: ${displayTitle}`}
                    title="Delete session"
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </aside>

      {/* Accessible Confirmation Modal */}
      {sessionToDelete && (
        <div
          className="modal-overlay"
          onClick={() => setSessionToDelete(null)}
          role="presentation"
        >
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-dialog-title"
            aria-describedby="delete-dialog-desc"
            onClick={(e) => e.stopPropagation()}
          >
            <h2
              id="delete-dialog-title"
              style={{
                margin: '0 0 0.5rem',
                fontSize: '1.1rem',
                color: 'var(--text-primary)',
              }}
            >
              Delete Conversation?
            </h2>
            <p
              id="delete-dialog-desc"
              style={{
                margin: '0',
                fontSize: '0.875rem',
                color: 'var(--text-secondary)',
                lineHeight: 1.5,
              }}
            >
              Are you sure you want to delete &ldquo;
              {sessionToDelete.title || 'New Chat'}&rdquo;? All messages and citations will be permanently removed.
            </p>

            <div className="modal-actions">
              <button
                type="button"
                className="btn-cancel"
                onClick={() => setSessionToDelete(null)}
                disabled={isDeleting}
                style={{
                  color: 'var(--text-secondary)',
                  borderColor: 'var(--border-subtle)',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-cancel"
                onClick={confirmDelete}
                disabled={isDeleting}
                style={{
                  backgroundColor: 'var(--status-error)',
                  color: '#ffffff',
                }}
              >
                {isDeleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default Sidebar;
