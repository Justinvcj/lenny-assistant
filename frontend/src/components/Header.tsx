import React from 'react';
import { Menu, X, Plus, Sparkles, Share2, Settings } from 'lucide-react';
import * as Tooltip from '@radix-ui/react-tooltip';

export interface HeaderProps {
  provider?: string | null;
  model?: string | null;
  healthStatus?: 'ok' | 'degraded' | 'offline' | string;
  isSidebarOpen?: boolean;
  isSidebarCollapsed?: boolean;
  onToggleSidebar: () => void;
  onNewChat?: () => void;
  chatTitle?: string;
  onOpenSettings?: () => void;
  onShareExport?: () => void;
  isMobile?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  provider = 'ollama',
  model = 'qwen2.5:7b',
  healthStatus = 'ok',
  isSidebarOpen = false,
  isSidebarCollapsed = false,
  onToggleSidebar,
  onNewChat,
  chatTitle = 'New Chat',
  onOpenSettings,
  onShareExport,
  isMobile = false,
}) => {
  const isOk = healthStatus === 'ok';
  const isDegraded = healthStatus === 'degraded';
  const dotClass = isOk ? 'ok' : isDegraded ? 'degraded' : 'offline';
  const statusLabel = isOk ? 'online' : isDegraded ? 'degraded' : 'offline';
  const visualStatusText = isOk ? 'OK' : isDegraded ? 'Degraded' : 'Offline';

  const modelText = provider && model ? `${provider} · ${model}` : 'Ollama · qwen2.5:7b';

  return (
    <header className="app-header" role="banner">
      {/* Left: Sidebar Toggle & Brand */}
      <div className="header-brand">
        <Tooltip.Provider delayDuration={300}>
          <Tooltip.Root>
            <Tooltip.Trigger asChild>
              <button
                type="button"
                className="btn-sidebar-toggle"
                onClick={onToggleSidebar}
                aria-label={isSidebarOpen ? 'Close sidebar navigation' : 'Open sidebar navigation'}
                aria-expanded={isSidebarOpen}
                data-testid="sidebar-toggle-btn"
              >
                {isSidebarOpen ? (
                  <X size={20} aria-hidden="true" />
                ) : (
                  <Menu size={20} aria-hidden="true" />
                )}
              </button>
            </Tooltip.Trigger>
            <Tooltip.Portal>
              <Tooltip.Content className="tooltip-content" side="bottom" sideOffset={6}>
                {isMobile
                  ? isSidebarOpen
                    ? 'Close sidebar navigation'
                    : 'Open sidebar navigation'
                  : isSidebarCollapsed
                  ? 'Expand sidebar (Ctrl+B)'
                  : 'Collapse sidebar (Ctrl+B)'}
                <Tooltip.Arrow className="tooltip-arrow" />
              </Tooltip.Content>
            </Tooltip.Portal>
          </Tooltip.Root>
        </Tooltip.Provider>

        <div className="brand-icon-wrapper" aria-hidden="true">
          <Sparkles size={18} />
        </div>

        <div>
          <h1 className="header-title">Lenny Growth Assistant</h1>
          <span className="header-subtitle">Grounded AI over Lenny's Podcast</span>
        </div>
      </div>

      {/* Center: Current Chat Title */}
      <div className="header-chat-title-group" aria-label="Current conversation">
        <span
          className="header-chat-title"
          title={chatTitle}
          data-title={chatTitle}
          data-testid="header-chat-title"
        />
      </div>

      {/* Right: Actions, Diagnostics & Badges */}
      <div className="header-status-cluster" role="region" aria-label="System status">
        {onNewChat && (
          <button
            type="button"
            className="btn-header-new-chat"
            onClick={onNewChat}
            aria-label="New conversation"
            title="New chat"
            data-testid="header-new-chat-btn"
          >
            <Plus size={15} aria-hidden="true" />
            <span className="header-new-chat-text">New</span>
          </button>
        )}

        {/* Share/Export Action */}
        <Tooltip.Provider delayDuration={300}>
          <Tooltip.Root>
            <Tooltip.Trigger asChild>
              <button
                type="button"
                className="btn-header-icon-action"
                onClick={onShareExport}
                aria-label="Share or export conversation"
                title="Share / Export"
                data-testid="header-share-btn"
              >
                <Share2 size={16} aria-hidden="true" />
              </button>
            </Tooltip.Trigger>
            <Tooltip.Portal>
              <Tooltip.Content className="tooltip-content" side="bottom" sideOffset={6}>
                Share or export conversation
                <Tooltip.Arrow className="tooltip-arrow" />
              </Tooltip.Content>
            </Tooltip.Portal>
          </Tooltip.Root>
        </Tooltip.Provider>

        {/* Settings Action */}
        <Tooltip.Provider delayDuration={300}>
          <Tooltip.Root>
            <Tooltip.Trigger asChild>
              <button
                type="button"
                className="btn-header-icon-action"
                onClick={onOpenSettings}
                aria-label="Open settings"
                title="Settings"
                data-testid="header-settings-btn"
              >
                <Settings size={16} aria-hidden="true" />
              </button>
            </Tooltip.Trigger>
            <Tooltip.Portal>
              <Tooltip.Content className="tooltip-content" side="bottom" sideOffset={6}>
                Settings
                <Tooltip.Arrow className="tooltip-arrow" />
              </Tooltip.Content>
            </Tooltip.Portal>
          </Tooltip.Root>
        </Tooltip.Provider>

        {/* Health Dot Badge */}
        <div
          className="health-status-badge"
          role="status"
          aria-label={`Connection status: ${statusLabel}`}
        >
          <span
            className={`status-dot ${dotClass}`}
            aria-hidden="true"
          />
          <span className="status-label">{visualStatusText}</span>
          <span className="sr-only">{statusLabel}</span>
        </div>

        {/* Model Badge */}
        <div
          className="model-badge"
          role="status"
          aria-label={`Active model: ${modelText}`}
        >
          {modelText}
        </div>
      </div>
    </header>
  );
};

export default Header;
