import React, { useState, useEffect, useRef } from 'react';
import {
  Plus,
  Trash2,
  MessageSquare,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  X,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  FileDown,
  Download,
  Keyboard,
  Info,
  ChevronDown,
} from 'lucide-react';
import * as Tooltip from '@radix-ui/react-tooltip';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import * as Dialog from '@radix-ui/react-dialog';
import { SidebarSession, getUserProfile, exportConversationToMarkdown, exportConversationToJson, triggerFileDownload } from '../storage/conversationStore';
import { groupConversations } from '../utils/conversationGrouping';

export interface SidebarProps {
  sessions: SidebarSession[];
  activeSessionId: string | null;
  isOpen: boolean;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  onDeleteSession: (sessionId: string) => Promise<void> | void;
  onRenameSession?: (sessionId: string, newTitle: string) => void;
  onTogglePinSession?: (sessionId: string) => void;
  onClearAllSessions?: () => void;
  onClose?: () => void;
  onOpenSettings?: () => void;
  onOpenShortcuts?: () => void;
  onOpenAbout?: () => void;
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
  isCollapsed = false,
  onToggleCollapse,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  onRenameSession,
  onTogglePinSession,
  onClearAllSessions,
  onClose,
  onOpenSettings,
  onOpenShortcuts,
  onOpenAbout,
}) => {
  const [sessionToDelete, setSessionToDelete] = useState<SidebarSession | null>(null);

  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editTitleValue, setEditTitleValue] = useState<string>('');
  const [isConfirmingClearAll, setIsConfirmingClearAll] = useState<boolean>(false);

  const editInputRef = useRef<HTMLInputElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const userProfile = getUserProfile();

  // Focus rename input when editing begins
  useEffect(() => {
    if (editingSessionId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingSessionId]);

  // Handle Escape key to close modals or cancel rename
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (editingSessionId) {
          setEditingSessionId(null);
        } else if (sessionToDelete) {
          setSessionToDelete(null);
        } else if (isConfirmingClearAll) {
          setIsConfirmingClearAll(false);
        } else if (isOpen && onClose) {
          onClose();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [editingSessionId, sessionToDelete, isConfirmingClearAll, isOpen, onClose]);

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

  const handleSaveRename = (sessionId: string) => {
    const clean = editTitleValue.trim();
    if (clean && onRenameSession) {
      onRenameSession(sessionId, clean);
    }
    setEditingSessionId(null);
  };

  const handleStartRename = (session: SidebarSession) => {
    setEditingSessionId(session.id);
    setEditTitleValue(session.title || 'New Chat');
  };

  const handleExportMarkdown = (session: SidebarSession) => {
    const md = exportConversationToMarkdown(session);
    const filename = `${(session.title || 'chat').replace(/[^a-zA-Z0-9_-]/g, '_')}.md`;
    triggerFileDownload(filename, md, 'text/markdown');
  };

  const handleExportJson = (session: SidebarSession) => {
    const json = exportConversationToJson(session);
    const filename = `${(session.title || 'chat').replace(/[^a-zA-Z0-9_-]/g, '_')}.json`;
    triggerFileDownload(filename, json, 'application/json');
  };


  const grouped = groupConversations(sessions, searchQuery);

  return (
    <>
      <aside
        className={`app-sidebar ${isOpen ? 'open' : ''} ${isCollapsed ? 'collapsed' : ''}`}
        aria-label="Session navigation"
        data-testid="app-sidebar"
      >
        {/* Top Header / New Chat & Search */}
        <div className="sidebar-header">
          {!isCollapsed ? (
            <div className="sidebar-header-expanded">
              <button
                type="button"
                className="btn-new-chat"
                onClick={() => {
                  onNewChat();
                  if (onClose) onClose();
                }}
                aria-label="Start a new chat session"
                data-testid="sidebar-new-chat-btn"
              >
                <div className="btn-new-chat-inner">
                  <Plus size={16} aria-hidden="true" />
                  <span>New Chat</span>
                </div>
                <kbd className="sidebar-shortcut-hint">Ctrl+Shift+O</kbd>
              </button>

              {/* Search chats box */}
              <div className="sidebar-search-box" role="search">
                <Search size={14} className="sidebar-search-icon" aria-hidden="true" />
                <input
                  ref={searchInputRef}
                  type="text"
                  className="sidebar-search-input"
                  placeholder="Search chats..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  aria-label="Search conversations by title or content"
                  data-testid="sidebar-search-input"
                />
                {searchQuery && (
                  <button
                    type="button"
                    className="sidebar-search-clear"
                    onClick={() => setSearchQuery('')}
                    aria-label="Clear search input"
                  >
                    <X size={12} aria-hidden="true" />
                  </button>
                )}
              </div>
            </div>
          ) : (
            <Tooltip.Provider delayDuration={200}>
              <Tooltip.Root>
                <Tooltip.Trigger asChild>
                  <button
                    type="button"
                    className="btn-new-chat-icon"
                    onClick={() => {
                      onNewChat();
                      if (onClose) onClose();
                    }}
                    aria-label="Start a new chat session"
                    data-testid="sidebar-new-chat-btn"
                  >
                    <Plus size={18} aria-hidden="true" />
                  </button>
                </Tooltip.Trigger>
                <Tooltip.Portal>
                  <Tooltip.Content className="tooltip-content" side="right" sideOffset={8}>
                    New Chat (Ctrl+Shift+O)
                    <Tooltip.Arrow className="tooltip-arrow" />
                  </Tooltip.Content>
                </Tooltip.Portal>
              </Tooltip.Root>
            </Tooltip.Provider>
          )}
        </div>

        {/* Conversation List with Date Grouping */}
        <div
          className="session-list"
          role="listbox"
          aria-label="Chat conversations"
          data-testid="session-list"
        >
          {sessions.length === 0 ? (
            !isCollapsed && (
              <div className="sidebar-empty-state">
                No conversations yet
              </div>
            )
          ) : grouped.length === 0 ? (
            !isCollapsed && (
              <div className="sidebar-empty-search">
                <p>No conversations found</p>
                {searchQuery && (
                  <button
                    type="button"
                    className="btn-clear-search-filter"
                    onClick={() => setSearchQuery('')}
                  >
                    Clear search
                  </button>
                )}
              </div>
            )
          ) : (
            grouped.map((group) => (
              <div key={group.key} className="session-group-container">
                {!isCollapsed && (
                  <div className="session-group-header">
                    {group.key === 'pinned' && <Pin size={12} className="group-pin-icon" aria-hidden="true" />}
                    <span>{group.label}</span>
                  </div>
                )}

                <div className="session-group-items">
                  {group.conversations.map((session) => {
                    const isActive = session.id === activeSessionId;
                    const displayTitle = session.title || 'New Chat';
                    const relativeTime = formatRelativeTime(session.created_at);
                    const isEditing = editingSessionId === session.id;

                    if (isCollapsed) {
                      // Collapsed Rail Item
                      return (
                        <Tooltip.Provider key={session.id} delayDuration={150}>
                          <Tooltip.Root>
                            <Tooltip.Trigger asChild>
                              <button
                                type="button"
                                className={`session-rail-btn ${isActive ? 'active' : ''} ${session.pinned ? 'pinned' : ''}`}
                                onClick={() => {
                                  onSelectSession(session.id);
                                  if (onClose) onClose();
                                }}
                                aria-label={`Select chat: ${displayTitle}`}
                                role="option"
                                aria-selected={isActive}
                              >
                                {session.pinned ? (
                                  <Pin size={16} aria-hidden="true" />
                                ) : (
                                  <MessageSquare size={17} aria-hidden="true" />
                                )}
                                {isActive && <span className="rail-active-dot" aria-hidden="true" />}
                              </button>
                            </Tooltip.Trigger>
                            <Tooltip.Portal>
                              <Tooltip.Content className="tooltip-content" side="right" sideOffset={10}>
                                <div style={{ fontWeight: 600 }}>{displayTitle}</div>
                                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                  {relativeTime} {session.pinned && '· Pinned'}
                                </div>
                                <Tooltip.Arrow className="tooltip-arrow" />
                              </Tooltip.Content>
                            </Tooltip.Portal>
                          </Tooltip.Root>
                        </Tooltip.Provider>
                      );
                    }

                    // Expanded Full Item
                    return (
                      <div
                        key={session.id}
                        role="option"
                        tabIndex={0}
                        aria-selected={isActive}
                        aria-label={displayTitle}
                        className={`session-item ${isActive ? 'active' : ''} ${session.pinned ? 'pinned' : ''}`}
                        onClick={() => {
                          if (!isEditing) {
                            onSelectSession(session.id);
                            if (onClose) onClose();
                          }
                        }}
                        onKeyDown={(e) => {
                          if (!isEditing && (e.key === 'Enter' || e.key === ' ')) {
                            e.preventDefault();
                            onSelectSession(session.id);
                            if (onClose) onClose();
                          }
                        }}
                        data-testid={`session-item-${session.id}`}
                      >
                        <div className="session-item-icon" aria-hidden="true">
                          {session.pinned ? (
                            <Pin size={14} className="pinned-badge-icon" />
                          ) : (
                            <MessageSquare size={15} />
                          )}
                        </div>

                        <div className="session-item-content">
                          {isEditing ? (
                            <input
                              ref={editInputRef}
                              type="text"
                              className="session-rename-input"
                              value={editTitleValue}
                              onChange={(e) => setEditTitleValue(e.target.value)}
                              onBlur={() => handleSaveRename(session.id)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                  e.preventDefault();
                                  handleSaveRename(session.id);
                                } else if (e.key === 'Escape') {
                                  e.preventDefault();
                                  setEditingSessionId(null);
                                }
                              }}
                              onClick={(e) => e.stopPropagation()}
                              aria-label="Rename conversation"
                              data-testid="session-rename-input"
                            />
                          ) : (
                            <>
                              <p className="session-item-title" title={displayTitle}>
                                {displayTitle}
                              </p>
                              <span className="session-item-time">{relativeTime}</span>
                            </>
                          )}
                        </div>

                        {!isEditing && (
                          <div className="session-item-actions">
                            {/* Standard delete button for backwards test compatibility */}
                            <button
                              type="button"
                              className="session-delete-btn"
                              onClick={(e) => {
                                e.stopPropagation();
                                setSessionToDelete(session);
                              }}
                              aria-label={`Delete chat: ${displayTitle}`}
                              title="Delete session"
                              data-testid={`delete-session-${session.id}`}
                            >
                              <Trash2 size={14} aria-hidden="true" />
                            </button>

                            {/* Radix DropdownMenu for per-chat "..." action menu */}
                            <DropdownMenu.Root>
                              <DropdownMenu.Trigger asChild>
                                <button
                                  type="button"
                                  className="session-menu-trigger"
                                  onClick={(e) => e.stopPropagation()}
                                  aria-label={`More options for ${displayTitle}`}
                                  data-testid={`session-menu-${session.id}`}
                                >
                                  <MoreHorizontal size={15} aria-hidden="true" />
                                </button>
                              </DropdownMenu.Trigger>

                              <DropdownMenu.Portal>
                                <DropdownMenu.Content
                                  className="dropdown-menu-content"
                                  side="bottom"
                                  align="end"
                                  sideOffset={4}
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <DropdownMenu.Item
                                    className="dropdown-menu-item"
                                    onSelect={() => handleStartRename(session)}
                                  >
                                    <Pencil size={14} aria-hidden="true" />
                                    <span>Rename</span>
                                  </DropdownMenu.Item>

                                  {onTogglePinSession && (
                                    <DropdownMenu.Item
                                      className="dropdown-menu-item"
                                      onSelect={() => onTogglePinSession(session.id)}
                                    >
                                      {session.pinned ? (
                                        <>
                                          <PinOff size={14} aria-hidden="true" />
                                          <span>Unpin from top</span>
                                        </>
                                      ) : (
                                        <>
                                          <Pin size={14} aria-hidden="true" />
                                          <span>Pin to top</span>
                                        </>
                                      )}
                                    </DropdownMenu.Item>
                                  )}

                                  <DropdownMenu.Separator className="dropdown-menu-separator" />

                                  <DropdownMenu.Item
                                    className="dropdown-menu-item"
                                    onSelect={() => handleExportMarkdown(session)}
                                  >
                                    <FileDown size={14} aria-hidden="true" />
                                    <span>Export Markdown (.md)</span>
                                  </DropdownMenu.Item>

                                  <DropdownMenu.Item
                                    className="dropdown-menu-item"
                                    onSelect={() => handleExportJson(session)}
                                  >
                                    <Download size={14} aria-hidden="true" />
                                    <span>Export JSON (.json)</span>
                                  </DropdownMenu.Item>

                                  <DropdownMenu.Separator className="dropdown-menu-separator" />

                                  <DropdownMenu.Item
                                    className="dropdown-menu-item danger"
                                    onSelect={() => setSessionToDelete(session)}
                                  >
                                    <Trash2 size={14} aria-hidden="true" />
                                    <span>Delete</span>
                                  </DropdownMenu.Item>
                                </DropdownMenu.Content>
                              </DropdownMenu.Portal>
                            </DropdownMenu.Root>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Sidebar Footer: Profile Button & Menus + Collapse Toggle */}
        <div className="sidebar-footer">
          {!isCollapsed ? (
            <div className="sidebar-footer-expanded">
              {/* Profile Dropdown Menu */}
              <DropdownMenu.Root>
                <DropdownMenu.Trigger asChild>
                  <button
                    type="button"
                    className="sidebar-user-profile-btn"
                    aria-label={`User profile: ${userProfile.name}`}
                    data-testid="sidebar-profile-btn"
                  >
                    <div className="user-profile-avatar" aria-hidden="true">
                      {userProfile.initials}
                    </div>
                    <div className="user-profile-info">
                      <span className="user-profile-name">{userProfile.name}</span>
                      <span className="user-profile-role">Free Local Tier</span>
                    </div>
                    <ChevronDown size={14} className="user-profile-chevron" aria-hidden="true" />
                  </button>
                </DropdownMenu.Trigger>

                <DropdownMenu.Portal>
                  <DropdownMenu.Content
                    className="dropdown-menu-content user-menu-content"
                    side="top"
                    align="start"
                    sideOffset={8}
                  >
                    <DropdownMenu.Item
                      className="dropdown-menu-item"
                      onSelect={() => onOpenSettings && onOpenSettings()}
                    >
                      <Settings size={15} aria-hidden="true" />
                      <span>Settings</span>
                      <kbd className="menu-shortcut-hint">Ctrl+,</kbd>
                    </DropdownMenu.Item>

                    <DropdownMenu.Item
                      className="dropdown-menu-item"
                      onSelect={() => onOpenShortcuts && onOpenShortcuts()}
                    >
                      <Keyboard size={15} aria-hidden="true" />
                      <span>Keyboard shortcuts</span>
                      <kbd className="menu-shortcut-hint">Ctrl+/</kbd>
                    </DropdownMenu.Item>

                    <DropdownMenu.Item
                      className="dropdown-menu-item"
                      onSelect={() => onOpenAbout && onOpenAbout()}
                    >
                      <Info size={15} aria-hidden="true" />
                      <span>About Lenny Assistant</span>
                    </DropdownMenu.Item>

                    <DropdownMenu.Separator className="dropdown-menu-separator" />

                    <DropdownMenu.Item
                      className="dropdown-menu-item danger"
                      onSelect={() => setIsConfirmingClearAll(true)}
                      data-testid="clear-all-chats-menu-item"
                    >
                      <Trash2 size={15} aria-hidden="true" />
                      <span>Clear all chats</span>
                    </DropdownMenu.Item>
                  </DropdownMenu.Content>
                </DropdownMenu.Portal>
              </DropdownMenu.Root>

              {onToggleCollapse && (
                <button
                  type="button"
                  className="btn-sidebar-collapse-toggle"
                  onClick={onToggleCollapse}
                  aria-label="Collapse sidebar"
                  title="Collapse sidebar (Ctrl+B)"
                  data-testid="sidebar-collapse-toggle-btn"
                >
                  <PanelLeftClose size={16} aria-hidden="true" />
                </button>
              )}
            </div>
          ) : (
            <div className="sidebar-footer-collapsed">
              {/* Profile Avatar in Rail */}
              <Tooltip.Provider delayDuration={200}>
                <Tooltip.Root>
                  <Tooltip.Trigger asChild>
                    <button
                      type="button"
                      className="rail-user-profile-btn"
                      onClick={onOpenSettings}
                      aria-label={`Profile: ${userProfile.name}`}
                    >
                      <div className="user-profile-avatar" aria-hidden="true">
                        {userProfile.initials}
                      </div>
                    </button>
                  </Tooltip.Trigger>
                  <Tooltip.Portal>
                    <Tooltip.Content className="tooltip-content" side="right" sideOffset={8}>
                      {userProfile.name} (Settings)
                      <Tooltip.Arrow className="tooltip-arrow" />
                    </Tooltip.Content>
                  </Tooltip.Portal>
                </Tooltip.Root>
              </Tooltip.Provider>

              {onToggleCollapse && (
                <Tooltip.Provider delayDuration={200}>
                  <Tooltip.Root>
                    <Tooltip.Trigger asChild>
                      <button
                        type="button"
                        className="btn-rail-footer-action"
                        onClick={onToggleCollapse}
                        aria-label="Expand sidebar"
                        title="Expand sidebar (Ctrl+B)"
                        data-testid="sidebar-expand-toggle-btn"
                      >
                        <PanelLeftOpen size={17} aria-hidden="true" />
                      </button>
                    </Tooltip.Trigger>
                    <Tooltip.Portal>
                      <Tooltip.Content className="tooltip-content" side="right" sideOffset={8}>
                        Expand sidebar (Ctrl+B)
                        <Tooltip.Arrow className="tooltip-arrow" />
                      </Tooltip.Content>
                    </Tooltip.Portal>
                  </Tooltip.Root>
                </Tooltip.Provider>
              )}
            </div>
          )}
        </div>
      </aside>

      {/* Accessible Confirmation Modal for Single Chat Deletion */}
      <Dialog.Root open={!!sessionToDelete} onOpenChange={(open) => !open && setSessionToDelete(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="modal-backdrop" />
          <Dialog.Content
            className="dialog-card delete-modal-card"
            aria-describedby="delete-desc"
            data-testid="delete-confirmation-modal"
          >
            <div className="dialog-header">
              <Dialog.Title className="dialog-title">Delete Conversation?</Dialog.Title>
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="dialog-close-btn"
                  aria-label="Close dialog"
                  onClick={() => setSessionToDelete(null)}
                >
                  <X size={18} aria-hidden="true" />
                </button>
              </Dialog.Close>
            </div>

            <p id="delete-desc" className="dialog-description">
              Are you sure you want to delete &ldquo;{sessionToDelete?.title || 'New Chat'}&rdquo;?
              This action cannot be undone.
            </p>

            <div className="dialog-footer">
              <button
                type="button"
                className="btn-dialog-secondary"
                onClick={() => setSessionToDelete(null)}
                disabled={isDeleting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-dialog-danger"
                onClick={confirmDelete}
                disabled={isDeleting}
              >
                {isDeleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* Accessible Confirmation Modal for Clear All Chats */}
      <Dialog.Root open={isConfirmingClearAll} onOpenChange={setIsConfirmingClearAll}>
        <Dialog.Portal>
          <Dialog.Overlay className="modal-backdrop" />
          <Dialog.Content
            className="dialog-card delete-modal-card"
            aria-describedby="clear-all-desc"
            data-testid="clear-all-modal"
          >
            <div className="dialog-header">
              <Dialog.Title className="dialog-title">Clear all conversations?</Dialog.Title>
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="dialog-close-btn"
                  aria-label="Close dialog"
                  onClick={() => setIsConfirmingClearAll(false)}
                >
                  <X size={18} aria-hidden="true" />
                </button>
              </Dialog.Close>
            </div>

            <p id="clear-all-desc" className="dialog-description">
              This will permanently delete all {sessions.length} conversation(s) and their message histories from local storage. This action cannot be undone.
            </p>

            <div className="dialog-footer">
              <button
                type="button"
                className="btn-dialog-secondary"
                onClick={() => setIsConfirmingClearAll(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-dialog-danger"
                onClick={() => {
                  if (onClearAllSessions) {
                    onClearAllSessions();
                  }
                  setIsConfirmingClearAll(false);
                }}
                data-testid="confirm-clear-all-submit-btn"
              >
                Clear all chats
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
};
export default Sidebar;
