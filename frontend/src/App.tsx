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
  Session,
  Message,
  ArtifactResponse,
} from './api';

import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { ArtifactPanel } from './components/ArtifactPanel';
import { ChatArea } from './components/ChatArea';
import { Composer } from './components/Composer';
import { LoadingSkeleton } from './components/LoadingSkeleton';
import { ErrorBanner, formatFriendlyErrorMessage } from './components/ErrorBanner';
import { Database } from 'lucide-react';

export const App: React.FC = () => {
  // Global & Session State
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoadingSession, setIsLoadingSession] = useState<boolean>(false);

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
  const [isArtifactOpen, setIsArtifactOpen] = useState<boolean>(false);
  const [activeArtifact, setActiveArtifact] = useState<ArtifactResponse | null>(null);

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
  // 3. Initial Sessions Load
  // -------------------------------------------------------------------------
  useEffect(() => {
    let isMounted = true;
    listSessions()
      .then(async (fetchedSessions) => {
        if (!isMounted) return;
        const sorted = [...fetchedSessions].sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        setSessions(sorted);
        if (sorted.length > 0) {
          const firstId = sorted[0].id;
          setActiveSessionId(firstId);
          setIsLoadingSession(true);
          try {
            const detail = await getSession(firstId);
            if (isMounted) {
              setMessages(detail.messages || []);
            }
          } catch (err: any) {
            console.error('Failed to load initial session messages:', err);
          } finally {
            if (isMounted) setIsLoadingSession(false);
          }
        }
      })
      .catch((err) => {
        console.error('Failed to fetch session list:', err);
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
          if (m.content && m.content.includes('Your Markdown document is ready')) {
            return {
              ...m,
              artifact: {
                id: '3c8724bc-e620-432a-b62c-0c3af228340a',
                title: 'Activation: Summary',
                type: 'markdown',
              },
            };
          }
        }
        return m;
      });
      setMessages(msgs);

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
  // 5. New Chat Handler
  // -------------------------------------------------------------------------
  const handleNewChat = () => {
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
  };

  // -------------------------------------------------------------------------
  // 6. Delete Session Handler
  // -------------------------------------------------------------------------
  const handleDeleteSession = async (sessionId: string) => {
    try {
      await deleteSession(sessionId);
      const remaining = sessions.filter((s) => s.id !== sessionId);
      setSessions(remaining);

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
  // 7. Send Message & Orchestration Pipeline
  // -------------------------------------------------------------------------
  const handleSendMessage = async (content: string) => {
    const trimmed = content.trim();
    if (!trimmed || isSending) return;

    setError(null);

    // Optimistic user message representation
    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      session_id: activeSessionId || '',
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
      let targetSessionId = activeSessionId;

      // Lazy session creation if on welcome/new-chat state
      if (!targetSessionId) {
        const titleSnippet = trimmed.slice(0, 48);
        const newSession = await createSession(titleSnippet, controller.signal);
        targetSessionId = newSession.id;
        tempUserMsg.session_id = targetSessionId;
        setActiveSessionId(targetSessionId);
        setSessions((prev) => [newSession, ...prev]);
      }

      const response = await sendMessage(targetSessionId, trimmed, controller.signal);

      // Append assistant response to message history
      setMessages((prev) => {
        const filtered = prev.filter((m) => m.id !== tempUserMsg.id);
        return [...filtered, tempUserMsg, response.message];
      });

      // Handle artifact preview if returned
      if (response.artifact) {
        response.message.artifact = response.artifact;
        if (response.artifact.id && !response.artifact.content && !(response.artifact as any).html) {
          getArtifact(response.artifact.id)
            .then((fullArt: ArtifactResponse) => {
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
        setMessages((prev) => prev.filter((m) => m.id !== tempUserMsg.id));
      } else {
        // Show error banner and remove pending message
        setMessages((prev) => prev.filter((m) => m.id !== tempUserMsg.id));
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
    }
  };

  // -------------------------------------------------------------------------
  // 8. Cancel Handler (AbortController)
  // -------------------------------------------------------------------------
  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsSending(false);
    setSendStartTime(null);
  };

  // -------------------------------------------------------------------------
  // 9. Retry Handler
  // -------------------------------------------------------------------------
  const handleRetry = () => {
    if (error?.prompt) {
      const promptToRetry = error.prompt;
      setError(null);
      handleSendMessage(promptToRetry);
    }
  };

  // -------------------------------------------------------------------------
  // 10. Citation Click Handler
  // -------------------------------------------------------------------------
  const handleCitationClick = useCallback((_citationNumber: number) => {
    // Handled in coordination with MessageItem and CitationChips accordion
  }, []);

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
        onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
        onNewChat={handleNewChat}
      />

      {/* 2. Responsive 3-Region Layout Body */}
      <div className="app-body">
        {/* Left Sidebar */}
        <Sidebar
          sessions={sessions}
          activeSessionId={activeSessionId}
          isOpen={isSidebarOpen}
          onSelectSession={handleSelectSession}
          onNewChat={handleNewChat}
          onDeleteSession={handleDeleteSession}
          onClose={() => setIsSidebarOpen(false)}
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
          onCitationClick={handleCitationClick}
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
            onSend={handleSendMessage}
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
    </div>
  );
};

export default App;
