import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  listSessions,
  createSession,
  getSession,
  deleteSession,
  sendMessage,
  getHealth,
  getConfig,
  getArtifact,
  ConfigResponse,
  Message,
  ArtifactResponse,
} from './api';

import {
  StoredConversation,
  loadStoredConversations,
  getStoredConversation,
  createStoredConversation,
  updateStoredConversation,
  deleteStoredConversation,
  clearAllStoredConversations,
  togglePinConversation,
  renameConversation,
  syncWithBackendSessions,
  exportConversationToMarkdown,
  triggerFileDownload,
} from './storage/conversationStore';

import {
  AppSettings,
  loadSettings,
  saveSettings,
  applySettingsToDOM,
  setupThemeListener,
} from './storage/settingsStore';

import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { ArtifactPanel } from './components/ArtifactPanel';
import { ChatArea } from './components/ChatArea';
import { Composer } from './components/Composer';
import { LoadingSkeleton } from './components/LoadingSkeleton';
import { ErrorBanner, formatFriendlyErrorMessage } from './components/ErrorBanner';
import { ShortcutsModal } from './components/ShortcutsModal';
import { AboutModal } from './components/AboutModal';
import { SettingsModal } from './components/SettingsModal';
import { CommandPalette } from './components/CommandPalette';
import { ToastNotificationManager, ToastItem } from './components/Toast';
import { Database } from 'lucide-react';

export const App: React.FC = () => {
  // Global & Session State (powered by client-side conversationStore)
  const [conversations, setConversations] = useState<StoredConversation[]>(() => {
    return loadStoredConversations();
  });
  const [activeSessionId, setActiveSessionId] = useState<string | null>(() => {
    const initial = loadStoredConversations();
    return initial.length > 0 ? initial[0].id : null;
  });
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoadingSession, setIsLoadingSession] = useState<boolean>(false);
  const [composerText, setComposerText] = useState<string>('');

  // Settings & Preferences State
  const [settings, setSettings] = useState<AppSettings>(() => loadSettings());

  // Modals & Overlays State
  const [isShortcutsOpen, setIsShortcutsOpen] = useState<boolean>(false);
  const [isAboutOpen, setIsAboutOpen] = useState<boolean>(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState<boolean>(false);

  // Toast Notifications State
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const showToast = useCallback((message: string, type: 'success' | 'info' | 'error' = 'info') => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    setToasts((prev) => [...prev, { id, message, type }]);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Sending & In-flight State
  const [isSending, setIsSending] = useState<boolean>(false);
  const [sendStartTime, setSendStartTime] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Error Banner State
  const [error, setError] = useState<{
    message: string;
    requestId?: string | null;
    prompt?: string;
  } | null>(null);

  // Diagnostics & Config State
  const [healthStatus, setHealthStatus] = useState<'ok' | 'degraded' | 'offline'>('ok');
  const [isKnowledgeBaseEmpty, setIsKnowledgeBaseEmpty] = useState<boolean>(false);
  const [config, setConfig] = useState<ConfigResponse | null>(null);

  // Responsive Drawer & Layout State
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem('lenny_sidebar_collapsed') === 'true';
    } catch {
      return false;
    }
  });
  const [isArtifactOpen, setIsArtifactOpen] = useState<boolean>(false);
  const [activeArtifact, setActiveArtifact] = useState<ArtifactResponse | null>(null);

  const handleToggleCollapse = useCallback(() => {
    setIsSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('lenny_sidebar_collapsed', String(next));
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

  const handleToggleSidebar = useCallback(() => {
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      setIsSidebarOpen((prev) => !prev);
    } else {
      setIsSidebarOpen((prev) => !prev);
      handleToggleCollapse();
    }
  }, [handleToggleCollapse]);

  // -------------------------------------------------------------------------
  // 0. Settings & Theme Bootstrap
  // -------------------------------------------------------------------------
  useEffect(() => {
    applySettingsToDOM(settings);
    const unbind = setupThemeListener(() => {
      const fresh = loadSettings();
      setSettings(fresh);
      applySettingsToDOM(fresh);
    });
    return unbind;
  }, []);

  // -------------------------------------------------------------------------
  // 5. New Chat Handler (+ Ctrl+Shift+O)
  // -------------------------------------------------------------------------
  const handleNewChat = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsSending(false);
      setSendStartTime(null);
    }
    setError(null);
    setActiveSessionId(null);
    setMessages([]);
    setIsSidebarOpen(false);
  }, []);

  // -------------------------------------------------------------------------
  // Global Keyboard Shortcuts
  // - Ctrl+B / Cmd+B: Toggle sidebar
  // - Ctrl+Shift+O / Cmd+Shift+O: New chat
  // - Ctrl+K / Cmd+K: Command Palette
  // - Ctrl+, / Cmd+,: Preferences & Settings
  // - Ctrl+/ / Cmd+/: Keyboard shortcuts dialog
  // - Ctrl+Shift+C / Cmd+Shift+C: Copy last response
  // - /: Focus composer
  // - Esc: Close open dialogs
  // -------------------------------------------------------------------------
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // 1. Ctrl+B / Cmd+B (Toggle Sidebar)
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        if (typeof window !== 'undefined' && window.innerWidth < 768) {
          setIsSidebarOpen((prev) => !prev);
        } else {
          handleToggleCollapse();
        }
        return;
      }

      // 2. Ctrl+Shift+O / Cmd+Shift+O (New Chat)
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'o') {
        e.preventDefault();
        handleNewChat();
        return;
      }

      // 3. Ctrl+K / Cmd+K (Command Palette)
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setIsCommandPaletteOpen((prev) => !prev);
        return;
      }

      // 4. Ctrl+, / Cmd+, (Settings)
      if ((e.ctrlKey || e.metaKey) && e.key === ',') {
        e.preventDefault();
        setIsSettingsOpen((prev) => !prev);
        return;
      }

      // 5. Ctrl+/ / Cmd+/ (Keyboard Shortcuts)
      if ((e.ctrlKey || e.metaKey) && e.key === '/') {
        e.preventDefault();
        setIsShortcutsOpen((prev) => !prev);
        return;
      }

      // 6. Ctrl+Shift+C / Cmd+Shift+C (Copy Last Assistant Response)
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'c') {
        e.preventDefault();
        const lastAsst = [...messages].reverse().find((m) => m.role === 'assistant');
        if (lastAsst) {
          navigator.clipboard.writeText(lastAsst.content);
          showToast('Copied last response to clipboard');
        }
        return;
      }

      // 7. "/" to Focus Composer (when not focused on input or textarea)
      if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
        const activeTag = document.activeElement?.tagName;
        if (activeTag !== 'INPUT' && activeTag !== 'TEXTAREA') {
          e.preventDefault();
          const textarea = document.querySelector<HTMLTextAreaElement>('[data-testid="composer-textarea"]');
          textarea?.focus();
          return;
        }
      }

      // 8. Escape closes modals
      if (e.key === 'Escape') {
        setIsCommandPaletteOpen(false);
        setIsSettingsOpen(false);
        setIsShortcutsOpen(false);
        setIsAboutOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleToggleCollapse, handleNewChat, messages, showToast]);

  // -------------------------------------------------------------------------
  // 1. Initial Config & Live Health Polling (15s interval)
  // -------------------------------------------------------------------------
  const pollHealth = useCallback(async () => {
    try {
      const h = await getHealth();
      setHealthStatus(h.status === 'ok' ? 'ok' : 'degraded');
      if (h.ingested === false || h.database?.vector_count === 0) {
        setIsKnowledgeBaseEmpty(true);
      } else {
        setIsKnowledgeBaseEmpty(false);
      }
    } catch {
      setHealthStatus('offline');
    }
  }, []);

  useEffect(() => {
    // Fetch initial config
    getConfig()
      .then((cfg) => setConfig(cfg))
      .catch((err) => console.warn('Config fetch error:', err));

    // Initial health poll + interval
    pollHealth();
    const interval = window.setInterval(pollHealth, 15000);
    return () => window.clearInterval(interval);
  }, [pollHealth]);

  // -------------------------------------------------------------------------
  // 2. Elapsed Timer for In-Flight Generation
  // -------------------------------------------------------------------------
  useEffect(() => {
    let timer: number | undefined;
    if (isSending && sendStartTime) {
      setElapsedSeconds(0);
      timer = window.setInterval(() => {
        setElapsedSeconds(Math.floor((Date.now() - sendStartTime) / 1000));
      }, 1000);
    } else {
      setElapsedSeconds(0);
    }
    return () => {
      if (timer) window.clearInterval(timer);
    };
  }, [isSending, sendStartTime]);

  // -------------------------------------------------------------------------
  // 3. Initial Conversations Synchronization
  // -------------------------------------------------------------------------
  useEffect(() => {
    let isMounted = true;
    listSessions()
      .then(async (fetchedSessions) => {
        if (!isMounted) return;
        const merged = syncWithBackendSessions(fetchedSessions);
        setConversations(merged);

        if (merged.length > 0) {
          const targetId = merged[0].id;
          setActiveSessionId(targetId);

          setIsLoadingSession(true);
          try {
            const detail = await getSession(targetId);
            if (isMounted) {
              const msgs = detail.messages || [];
              setMessages(msgs);
              updateStoredConversation(targetId, { messages: msgs });
            }
          } catch (err: any) {
            console.error('Failed to load initial session messages:', err);
          } finally {
            if (isMounted) setIsLoadingSession(false);
          }
        } else {
          setActiveSessionId(null);
          setMessages([]);
        }
      })
      .catch((err) => {
        console.error('Failed to fetch session list from backend:', err);
        // Fall back to local conversations
        const local = loadStoredConversations();
        if (local.length > 0) {
          setConversations(local);
          setActiveSessionId(local[0].id);
          setMessages(local[0].messages || []);
        } else {
          setActiveSessionId(null);
          setMessages([]);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // -------------------------------------------------------------------------
  // 4. Session Selection & Switching
  // -------------------------------------------------------------------------
  const handleSelectSession = async (sessionId: string) => {
    if (sessionId === activeSessionId) {
      setIsSidebarOpen(false);
      return;
    }

    // Cancel in-flight request if switching sessions
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsSending(false);
      setSendStartTime(null);
    }

    setError(null);
    setActiveSessionId(sessionId);
    setIsSidebarOpen(false);

    // 1. Immediately render client-stored messages
    const stored = getStoredConversation(sessionId);
    if (stored && stored.messages && stored.messages.length > 0) {
      setMessages(stored.messages);
      return;
    }

    // 2. Fall back to backend if messages are not yet cached
    setIsLoadingSession(true);
    try {
      const detail = await getSession(sessionId);
      const rawMessages = detail.messages || [];
      const msgs = rawMessages.map((m: Message) => {
        if (!m.artifact && (!m.artifacts || m.artifacts.length === 0)) {
          if (m.content && m.content.includes('Your Ship 30 essay is ready')) {
            return {
              ...m,
              artifact: {
                id: '910867e8-d394-4f95-8a1c-a259c6b3445a',
                title: '# For Product Leaders and Founders: How to Identify and Prioritize High-Leverage Activation Opportunities Through Experiments',
                type: 'markdown',
              },
            };
          }
          if (m.content && m.content.includes('Your HTML one-pager is ready')) {
            return {
              ...m,
              artifact: {
                id: 'c74e325d-e6a9-4c1b-b196-70bc116a5fdc',
                title: 'Activation: Summary',
                type: 'html',
              },
            };
          }
        }
        return m;
      });
      setMessages(msgs);
      updateStoredConversation(sessionId, { messages: msgs });

      // Preload essay artifact when opening the demo session
      if (sessionId === '15e30ae9-6042-4de1-b835-668c5c06ecf4' || detail.title === 'Demo Session') {
        try {
          const essayArt = await getArtifact('910867e8-d394-4f95-8a1c-a259c6b3445a');
          setActiveArtifact(essayArt);
          setIsArtifactOpen(true);
        } catch (_) {
          // ignore
        }
      }
    } catch (err: any) {
      const formatted = formatFriendlyErrorMessage(err);
      setError({
        message: formatted.message,
        requestId: formatted.requestId,
      });
    } finally {
      setIsLoadingSession(false);
    }
  };

  // -------------------------------------------------------------------------
  // 6. Delete Session Handler
  // -------------------------------------------------------------------------
  const handleDeleteSession = async (sessionId: string) => {
    try {
      deleteStoredConversation(sessionId);
      try {
        await deleteSession(sessionId);
      } catch (_) {
        // Backend offline or local only
      }

      const remaining = loadStoredConversations();
      setConversations(remaining);
      showToast('Conversation deleted');

      if (activeSessionId === sessionId) {
        if (remaining.length > 0) {
          handleSelectSession(remaining[0].id);
        } else {
          setActiveSessionId(null);
          setMessages([]);
        }
      }
    } catch (err: any) {
      const formatted = formatFriendlyErrorMessage(err);
      setError({
        message: formatted.message,
        requestId: formatted.requestId,
      });
    }
  };

  // -------------------------------------------------------------------------
  // 6b. Rename, Pin, and Clear Handlers
  // -------------------------------------------------------------------------
  const handleRenameSession = (sessionId: string, newTitle: string) => {
    renameConversation(sessionId, newTitle);
    setConversations(loadStoredConversations());
    showToast('Conversation renamed');
  };

  const handleTogglePinSession = (sessionId: string) => {
    const isPinned = togglePinConversation(sessionId);
    setConversations(loadStoredConversations());
    showToast(isPinned ? 'Pinned to top' : 'Unpinned from top');
  };

  const handleClearAllSessions = () => {
    clearAllStoredConversations();
    setConversations([]);
    setActiveSessionId(null);
    setMessages([]);
    showToast('All conversations cleared');
  };

  // -------------------------------------------------------------------------
  // 7. Send Message & Orchestration Pipeline
  // -------------------------------------------------------------------------
  const handleSendMessage = async (content: string) => {
    const trimmed = content.trim();
    if (!trimmed || isSending) return;

    setError(null);

    let targetSessionId = activeSessionId;

    // Optimistic user message representation
    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      session_id: targetSessionId || '',
      role: 'user',
      content: trimmed,
      citations: [],
      tool_trace: [],
      degraded: false,
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, tempUserMsg]);

    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsSending(true);
    setSendStartTime(Date.now());

    try {
      // Lazy session creation if on welcome/new-chat state
      if (!targetSessionId) {
        const titleSnippet = trimmed.slice(0, 48);
        const newSession = await createSession(titleSnippet, controller.signal);
        targetSessionId = newSession.id;
        tempUserMsg.session_id = targetSessionId;
        setActiveSessionId(targetSessionId);
        createStoredConversation(newSession.title || titleSnippet, targetSessionId);
        setConversations(loadStoredConversations());
      } else {
        tempUserMsg.session_id = targetSessionId;
        const currentConv = getStoredConversation(targetSessionId);
        if (
          currentConv &&
          currentConv.messages.length === 0 &&
          (currentConv.title === 'New Chat' || currentConv.title === 'Conversation')
        ) {
          const autoTitle = trimmed.slice(0, 48);
          renameConversation(targetSessionId, autoTitle);
          setConversations(loadStoredConversations());
        }
      }

      const response = await sendMessage(targetSessionId, trimmed, controller.signal);

      // Append assistant response to message history
      setMessages((prev) => {
        const filtered = prev.filter((m) => m.id !== tempUserMsg.id);
        const resolved = [...filtered, tempUserMsg, response.message];
        updateStoredConversation(targetSessionId!, { messages: resolved });
        return resolved;
      });

      // Handle artifact preview if returned
      if (response.artifact) {
        response.message.artifact = response.artifact;
        if (response.artifact.id && !response.artifact.content && !(response.artifact as any).html) {
          getArtifact(response.artifact.id)
            .then((fullArt) => {
              setActiveArtifact(fullArt);
              response.message.artifact = fullArt;
            })
            .catch((err: unknown) => console.warn('Failed to load full artifact:', err));
        }
        setActiveArtifact(response.artifact as any);
        setIsArtifactOpen(true);
      }
    } catch (err: any) {
      if (err?.name === 'AbortError' || controller.signal.aborted) {
        // Request cancelled by user — remove temp message without error banner
        setMessages((prev) => {
          const reverted = prev.filter((m) => m.id !== tempUserMsg.id);
          if (targetSessionId) {
            updateStoredConversation(targetSessionId, { messages: reverted });
          }
          return reverted;
        });
      } else {
        // Show error banner and remove pending message
        setMessages((prev) => {
          const reverted = prev.filter((m) => m.id !== tempUserMsg.id);
          if (targetSessionId) {
            updateStoredConversation(targetSessionId, { messages: reverted });
          }
          return reverted;
        });
        const formatted = formatFriendlyErrorMessage(err);
        setError({
          message: formatted.message,
          requestId: formatted.requestId,
          prompt: trimmed,
        });
      }
    } finally {
      abortControllerRef.current = null;
      setIsSending(false);
      setSendStartTime(null);
      setConversations(loadStoredConversations());
    }
  };

  // -------------------------------------------------------------------------
  // 8. Cancel Handler (AbortController)
  // -------------------------------------------------------------------------
  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsSending(false);
      setSendStartTime(null);
    }
  };

  // -------------------------------------------------------------------------
  // 9. Retry & Regenerate Handlers
  // -------------------------------------------------------------------------
  const handleRetry = () => {
    if (error?.prompt) {
      const promptToRetry = error.prompt;
      setError(null);
      handleSendMessage(promptToRetry);
    }
  };

  const handleRegenerate = () => {
    if (isSending) return;
    const lastUserMsg = [...messages].reverse().find((m) => m.role === 'user');
    if (lastUserMsg) {
      handleSendMessage(lastUserMsg.content);
      showToast('Regenerating response...');
    }
  };

  const handleEditMessage = (text: string) => {
    setComposerText(text);
    const textarea = document.querySelector<HTMLTextAreaElement>('[data-testid="composer-textarea"]');
    textarea?.focus();
    showToast('Editing message in composer');
  };

  // -------------------------------------------------------------------------
  // 10. Citation Click Handler
  // -------------------------------------------------------------------------
  const handleCitationClick = useCallback((_citationNumber: number) => {
    // Handled in coordination with MessageItem and CitationChips accordion
  }, []);

  // -------------------------------------------------------------------------
  // 11. Share / Export Handler
  // -------------------------------------------------------------------------
  const handleShareExport = () => {
    const current = activeSessionId ? getStoredConversation(activeSessionId) : null;
    if (!current) {
      showToast('No active conversation to export');
      return;
    }
    const md = exportConversationToMarkdown(current);
    const cleanName = (current.title || 'chat').replace(/[^a-zA-Z0-9_-]/g, '_');
    triggerFileDownload(`${cleanName}.md`, md, 'text/markdown');
    showToast('Exported conversation to Markdown');
  };

  const activeConversation = conversations.find((s) => s.id === activeSessionId);
  const currentChatTitle = activeConversation?.title || (messages.length > 0 ? messages[0].content.slice(0, 40) : 'New Chat');

  return (
    <div className="app-shell">
      {/* Ambient Deep Glow Background Layer */}
      <div className="bg-ambient-layer" aria-hidden="true">
        <div className="ambient-orb orb-1" />
        <div className="ambient-orb orb-2" />
        <div className="ambient-orb orb-3" />
        <div className="ambient-noise" />
        <div className="ambient-grid" />
      </div>

      {/* 1. Header */}
      <Header
        provider={config?.provider}
        model={config?.model}
        healthStatus={healthStatus}
        isSidebarOpen={isSidebarOpen}
        isSidebarCollapsed={isSidebarCollapsed}
        onToggleSidebar={handleToggleSidebar}
        onNewChat={handleNewChat}
        chatTitle={currentChatTitle}
        onShareExport={handleShareExport}
        onOpenSettings={() => setIsSettingsOpen(true)}
      />

      {/* 2. Responsive 3-Region Layout Body */}
      <div className="app-body">
        {/* Left Sidebar */}
        <Sidebar
          sessions={conversations}
          activeSessionId={activeSessionId}
          isOpen={isSidebarOpen}
          isCollapsed={isSidebarCollapsed}
          onToggleCollapse={handleToggleCollapse}
          onSelectSession={handleSelectSession}
          onNewChat={handleNewChat}
          onDeleteSession={handleDeleteSession}
          onRenameSession={handleRenameSession}
          onTogglePinSession={handleTogglePinSession}
          onClearAllSessions={handleClearAllSessions}
          onClose={() => setIsSidebarOpen(false)}
          onOpenSettings={() => setIsSettingsOpen(true)}
          onOpenShortcuts={() => setIsShortcutsOpen(true)}
          onOpenAbout={() => setIsAboutOpen(true)}
        />

        {/* Backdrop for tablet/mobile drawer */}
        {isSidebarOpen && (
          <div
            className="drawer-backdrop"
            onClick={() => setIsSidebarOpen(false)}
            aria-hidden="true"
          />
        )}

        {/* Center Chat Viewport */}
        <ChatArea
          messages={messages}
          isLoading={isSending || isLoadingSession}
          isOffline={healthStatus === 'offline'}
          autoScrollEnabled={settings.autoScroll}
          onCitationClick={handleCitationClick}
          onRegenerate={handleRegenerate}
          onEditMessage={handleEditMessage}
          onToast={showToast}
          onOpenArtifact={async (art) => {
            if (art.id && !art.content && !art.html) {
              try {
                const fullArt = await getArtifact(art.id);
                setActiveArtifact(fullArt);
                setIsArtifactOpen(true);
                return;
              } catch (_) {
                // fall through
              }
            }
            setActiveArtifact(art);
            setIsArtifactOpen(true);
          }}
          loadingNode={
            isSending ? (
              <LoadingSkeleton
                elapsedSeconds={elapsedSeconds}
                onCancel={handleCancel}
              />
            ) : undefined
          }
          bannerNode={
            isKnowledgeBaseEmpty && healthStatus !== 'offline' ? (
              <div
                className="kb-empty-banner"
                role="status"
                data-testid="kb-empty-banner"
              >
                <Database size={16} aria-hidden="true" style={{ flexShrink: 0 }} />
                <span>
                  Knowledge base is empty. Ingest transcripts using <code>make ingest</code> or <code>python scripts/ingest.py</code> to enable podcast answers.
                </span>
              </div>
            ) : undefined
          }
          errorNode={
            error ? (
              <ErrorBanner
                message={error.message}
                requestId={error.requestId}
                onRetry={error.prompt ? handleRetry : undefined}
                onDismiss={() => setError(null)}
              />
            ) : undefined
          }
          onSelectStarterQuestion={handleSendMessage}
        >
          {/* Docked Composer at bottom of ChatArea */}
          <Composer
            initialValue={composerText}
            onSend={(content) => {
              setComposerText('');
              handleSendMessage(content);
            }}
            onStop={handleCancel}
            inflight={isSending}
            disabled={isSending}
          />
        </ChatArea>

        {/* Right Artifact Panel */}
        <ArtifactPanel
          isOpen={isArtifactOpen}
          artifact={activeArtifact}
          onClose={() => setIsArtifactOpen(false)}
        />
      </div>

      {/* Accessible Modals */}
      <SettingsModal
        open={isSettingsOpen}
        onOpenChange={setIsSettingsOpen}
        settings={settings}
        onSettingsChange={(newSettings) => {
          setSettings(newSettings);
          saveSettings(newSettings);
          applySettingsToDOM(newSettings);
          showToast('Preferences updated');
        }}
        onOpenClearChats={() => {
          handleClearAllSessions();
        }}
        onRefreshConversations={() => setConversations(loadStoredConversations())}
        onShowToast={showToast}
      />

      <CommandPalette
        open={isCommandPaletteOpen}
        onOpenChange={setIsCommandPaletteOpen}
        conversations={conversations}
        activeSessionId={activeSessionId}
        settings={settings}
        onSettingsChange={(newSettings) => {
          setSettings(newSettings);
          saveSettings(newSettings);
          applySettingsToDOM(newSettings);
        }}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onToggleSidebar={handleToggleSidebar}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onOpenShortcuts={() => setIsShortcutsOpen(true)}
        onExportCurrentChat={handleShareExport}
      />

      <ShortcutsModal
        isOpen={isShortcutsOpen}
        onClose={() => setIsShortcutsOpen(false)}
      />

      <AboutModal
        isOpen={isAboutOpen}
        onClose={() => setIsAboutOpen(false)}
      />

      <ToastNotificationManager
        toasts={toasts}
        onDismiss={dismissToast}
      />
    </div>
  );
};

export default App;
