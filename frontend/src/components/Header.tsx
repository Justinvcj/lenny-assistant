import React from 'react';
import { Menu, X, Plus } from 'lucide-react';

export interface HeaderProps {
  provider?: string | null;
  model?: string | null;
  healthStatus?: 'ok' | 'degraded' | 'offline' | string;
  isSidebarOpen?: boolean;
  onToggleSidebar: () => void;
  onNewChat?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  provider = 'ollama',
  model = 'qwen2.5:7b',
  healthStatus = 'ok',
  isSidebarOpen = false,
  onToggleSidebar,
  onNewChat,
}) => {
  const isOk = healthStatus === 'ok';
  const isDegraded = healthStatus === 'degraded';
  const dotClass = isOk ? 'ok' : isDegraded ? 'degraded' : 'offline';
  const statusLabel = isOk ? 'online' : isDegraded ? 'degraded' : 'offline';
  const visualStatusText = isOk ? 'OK' : isDegraded ? 'Degraded' : 'Offline';

  const modelText = provider && model ? `${provider} · ${model}` : 'Ollama · qwen2.5:7b';

  return (
    <header className="app-header" role="banner">
      <div className="header-brand">
        <button
          type="button"
          className="btn-sidebar-toggle"
          onClick={onToggleSidebar}
          aria-label={isSidebarOpen ? 'Close sidebar navigation' : 'Open sidebar navigation'}
          aria-expanded={isSidebarOpen}
        >
          {isSidebarOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
        </button>

        <div>
          <h1 className="header-title">Lenny Growth Assistant</h1>
          <span className="header-subtitle">Grounded AI over Lenny's Podcast</span>
        </div>
      </div>

      <div className="header-status-cluster" role="region" aria-label="System status">
        {onNewChat && (
          <button
            type="button"
            className="btn-header-new-chat"
            onClick={onNewChat}
            aria-label="New conversation"
            title="New chat"
          >
            <Plus size={15} aria-hidden="true" />
            <span className="header-new-chat-text">New</span>
          </button>
        )}

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
