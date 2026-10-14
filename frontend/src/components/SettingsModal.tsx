import React, { useState, useRef } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import * as Tabs from '@radix-ui/react-tabs';
import * as Switch from '@radix-ui/react-switch';
import {
  X,
  Sliders,
  MessageSquare,
  HardDrive,
  Info,
  Moon,
  Sun,
  Laptop,
  Download,
  Upload,
  Trash2,
  Check,
  ExternalLink,
} from 'lucide-react';
import {
  AppSettings,
  AccentColor,
  FontSize,
  ChatDensity,
  saveSettings,
} from '../storage/settingsStore';
import {
  exportAllConversationsToJson,
  importConversationsFromJson,
  triggerFileDownload,
  saveUserProfile,
} from '../storage/conversationStore';

export interface SettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  settings: AppSettings;
  onSettingsChange: (settings: AppSettings) => void;
  onOpenClearChats?: () => void;
  onRefreshConversations?: () => void;
  onShowToast?: (message: string) => void;
}

const ACCENT_OPTIONS: { id: AccentColor; label: string; bg: string }[] = [
  { id: 'indigo', label: 'Obsidian Violet', bg: 'linear-gradient(135deg, #7C5CFF, #4F8CFF)' },
  { id: 'cyan', label: 'Electric Cyan', bg: 'linear-gradient(135deg, #06B6D4, #3B82F6)' },
  { id: 'emerald', label: 'Emerald Mint', bg: 'linear-gradient(135deg, #10B981, #059669)' },
  { id: 'amber', label: 'Sunset Amber', bg: 'linear-gradient(135deg, #F59E0B, #D97706)' },
  { id: 'rose', label: 'Rose Pink', bg: 'linear-gradient(135deg, #F43F5E, #E11D48)' },
];

export const SettingsModal: React.FC<SettingsModalProps> = ({
  open,
  onOpenChange,
  settings,
  onSettingsChange,
  onOpenClearChats,
  onRefreshConversations,
  onShowToast,
}) => {
  const [localSettings, setLocalSettings] = useState<AppSettings>(settings);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sync state when modal opens
  React.useEffect(() => {
    setLocalSettings(settings);
  }, [settings, open]);

  const updateField = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => {
    const updated = { ...localSettings, [key]: value };
    setLocalSettings(updated);
    saveSettings(updated);
    onSettingsChange(updated);

    if (key === 'displayName' && typeof value === 'string') {
      saveUserProfile(value);
    }
  };

  const handleExportAll = () => {
    const jsonStr = exportAllConversationsToJson();
    const dateStr = new Date().toISOString().slice(0, 10);
    triggerFileDownload(`lenny-conversations-${dateStr}.json`, jsonStr, 'application/json');
    onShowToast?.('Exported all conversations to JSON');
  };

  const handleImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      if (!content) return;
      const res = importConversationsFromJson(content);
      if (res.imported > 0) {
        onRefreshConversations?.();
        onShowToast?.(`Successfully imported ${res.imported} conversations`);
      } else {
        onShowToast?.('No valid conversations found in file');
      }
      if (fileInputRef.current) fileInputRef.current.value = '';
    };
    reader.readAsText(file);
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          className="dialog-content settings-modal-content"
          aria-describedby="settings-dialog-description"
        >
          <div className="settings-modal-header">
            <Dialog.Title className="settings-modal-title">Settings</Dialog.Title>
            <Dialog.Close asChild>
              <button
                type="button"
                className="btn-modal-close"
                aria-label="Close settings"
              >
                <X size={16} aria-hidden="true" />
              </button>
            </Dialog.Close>
          </div>
          <Dialog.Description id="settings-dialog-description" className="sr-only">
            Customize appearance, chat controls, and conversation data.
          </Dialog.Description>

          <Tabs.Root defaultValue="general" className="settings-tabs-root" orientation="vertical">
            <Tabs.List className="settings-tabs-list" aria-label="Settings categories">
              <Tabs.Trigger value="general" className="settings-tab-trigger">
                <Sliders size={16} aria-hidden="true" />
                <span>General</span>
              </Tabs.Trigger>
              <Tabs.Trigger value="chat" className="settings-tab-trigger">
                <MessageSquare size={16} aria-hidden="true" />
                <span>Chat</span>
              </Tabs.Trigger>
              <Tabs.Trigger value="data" className="settings-tab-trigger">
                <HardDrive size={16} aria-hidden="true" />
                <span>Data</span>
              </Tabs.Trigger>
              <Tabs.Trigger value="about" className="settings-tab-trigger">
                <Info size={16} aria-hidden="true" />
                <span>About</span>
              </Tabs.Trigger>
            </Tabs.List>

            <div className="settings-tab-content-container">
              {/* General Tab */}
              <Tabs.Content value="general" className="settings-tab-content">
                <div className="settings-section">
                  <h3 className="settings-section-title">Theme</h3>
                  <div className="theme-toggle-group">
                    <button
                      type="button"
                      className={`theme-pill ${localSettings.theme === 'dark' ? 'active' : ''}`}
                      onClick={() => updateField('theme', 'dark')}
                    >
                      <Moon size={14} aria-hidden="true" />
                      <span>Dark</span>
                    </button>
                    <button
                      type="button"
                      className={`theme-pill ${localSettings.theme === 'light' ? 'active' : ''}`}
                      onClick={() => updateField('theme', 'light')}
                    >
                      <Sun size={14} aria-hidden="true" />
                      <span>Light</span>
                    </button>
                    <button
                      type="button"
                      className={`theme-pill ${localSettings.theme === 'system' ? 'active' : ''}`}
                      onClick={() => updateField('theme', 'system')}
                    >
                      <Laptop size={14} aria-hidden="true" />
                      <span>System</span>
                    </button>
                  </div>
                </div>

                <div className="settings-section">
                  <h3 className="settings-section-title">Accent Color</h3>
                  <div className="accent-color-grid">
                    {ACCENT_OPTIONS.map((opt) => (
                      <button
                        key={opt.id}
                        type="button"
                        className={`accent-option-btn ${localSettings.accentColor === opt.id ? 'active' : ''}`}
                        onClick={() => updateField('accentColor', opt.id)}
                        aria-label={`Select ${opt.label} accent`}
                      >
                        <span
                          className="accent-swatch"
                          style={{ background: opt.bg }}
                        />
                        <span className="accent-label">{opt.label}</span>
                        {localSettings.accentColor === opt.id && (
                          <Check size={14} className="accent-check" aria-hidden="true" />
                        )}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="settings-section">
                  <h3 className="settings-section-title">Font Size</h3>
                  <div className="theme-toggle-group">
                    {(['sm', 'md', 'lg'] as FontSize[]).map((size) => (
                      <button
                        key={size}
                        type="button"
                        className={`theme-pill ${localSettings.fontSize === size ? 'active' : ''}`}
                        onClick={() => updateField('fontSize', size)}
                      >
                        <span>{size === 'sm' ? 'Small' : size === 'md' ? 'Default' : 'Large'}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="settings-section">
                  <div className="settings-row-between">
                    <div>
                      <h3 className="settings-section-title" style={{ marginBottom: '2px' }}>
                        Send with Enter
                      </h3>
                      <p className="settings-section-subtitle">
                        Press Enter to submit prompt, Shift+Enter for newline
                      </p>
                    </div>
                    <Switch.Root
                      className="switch-root"
                      checked={localSettings.sendWithEnter}
                      onCheckedChange={(val) => updateField('sendWithEnter', val)}
                      id="switch-enter"
                    >
                      <Switch.Thumb className="switch-thumb" />
                    </Switch.Root>
                  </div>
                </div>

                <div className="settings-section">
                  <h3 className="settings-section-title">Display Name</h3>
                  <p className="settings-section-subtitle">
                    Stored locally in your browser for this workspace
                  </p>
                  <input
                    type="text"
                    className="settings-text-input"
                    value={localSettings.displayName}
                    onChange={(e) => updateField('displayName', e.target.value)}
                    maxLength={32}
                    placeholder="e.g. Alex"
                  />
                </div>
              </Tabs.Content>

              {/* Chat Tab */}
              <Tabs.Content value="chat" className="settings-tab-content">
                <div className="settings-section">
                  <div className="settings-row-between">
                    <div>
                      <h3 className="settings-section-title" style={{ marginBottom: '2px' }}>
                        Display Grounded Sources
                      </h3>
                      <p className="settings-section-subtitle">
                        Show interactive citation chips and passage accordion under answers
                      </p>
                    </div>
                    <Switch.Root
                      className="switch-root"
                      checked={localSettings.showSources}
                      onCheckedChange={(val) => updateField('showSources', val)}
                    >
                      <Switch.Thumb className="switch-thumb" />
                    </Switch.Root>
                  </div>
                </div>

                <div className="settings-section">
                  <div className="settings-row-between">
                    <div>
                      <h3 className="settings-section-title" style={{ marginBottom: '2px' }}>
                        Auto-scroll to Bottom
                      </h3>
                      <p className="settings-section-subtitle">
                        Automatically keep viewport pinned to newly streamed tokens
                      </p>
                    </div>
                    <Switch.Root
                      className="switch-root"
                      checked={localSettings.autoScroll}
                      onCheckedChange={(val) => updateField('autoScroll', val)}
                    >
                      <Switch.Thumb className="switch-thumb" />
                    </Switch.Root>
                  </div>
                </div>

                <div className="settings-section">
                  <h3 className="settings-section-title">Layout Density</h3>
                  <div className="theme-toggle-group">
                    {(['comfortable', 'compact'] as ChatDensity[]).map((d) => (
                      <button
                        key={d}
                        type="button"
                        className={`theme-pill ${localSettings.density === d ? 'active' : ''}`}
                        onClick={() => updateField('density', d)}
                      >
                        <span>{d === 'comfortable' ? 'Comfortable' : 'Compact'}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </Tabs.Content>

              {/* Data Tab */}
              <Tabs.Content value="data" className="settings-tab-content">
                <div className="settings-section">
                  <h3 className="settings-section-title">Export All Conversations</h3>
                  <p className="settings-section-subtitle">
                    Download full chat histories, timestamps, and citations in JSON format
                  </p>
                  <button
                    type="button"
                    className="btn-settings-action"
                    onClick={handleExportAll}
                  >
                    <Download size={14} aria-hidden="true" />
                    <span>Export JSON</span>
                  </button>
                </div>

                <div className="settings-section">
                  <h3 className="settings-section-title">Import Conversations</h3>
                  <p className="settings-section-subtitle">
                    Merge previously exported chat backup JSON files into local storage
                  </p>
                  <input
                    type="file"
                    ref={fileInputRef}
                    accept=".json,application/json"
                    style={{ display: 'none' }}
                    onChange={handleImportFile}
                  />
                  <button
                    type="button"
                    className="btn-settings-action"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Upload size={14} aria-hidden="true" />
                    <span>Import JSON</span>
                  </button>
                </div>

                <div className="settings-section danger-zone">
                  <h3 className="settings-section-title" style={{ color: 'var(--status-error)' }}>
                    Clear All Chats
                  </h3>
                  <p className="settings-section-subtitle">
                    Permanently delete all conversations from your browser's local storage
                  </p>
                  <button
                    type="button"
                    className="btn-settings-danger"
                    onClick={() => {
                      onOpenChange(false);
                      onOpenClearChats?.();
                    }}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                    <span>Clear All Conversations</span>
                  </button>
                </div>
              </Tabs.Content>

              {/* About Tab */}
              <Tabs.Content value="about" className="settings-tab-content">
                <div className="settings-section">
                  <div className="about-hero-box">
                    <div className="about-icon-badge" aria-hidden="true">
                      ✦
                    </div>
                    <div>
                      <h3 className="about-app-title">Lenny Growth Assistant</h3>
                      <p className="about-app-version">v0.1.0 · Production Take-Home Edition</p>
                    </div>
                  </div>
                  <p className="about-description">
                    A world-class product intelligence assistant grounded directly in 250+
                    episodes of Lenny's Podcast. Powered by an enterprise RAG pipeline featuring
                    FastAPI, PostgreSQL with pgvector, Ollama / Qwen LLM, and modern React.
                  </p>
                </div>

                <div className="settings-section">
                  <h3 className="settings-section-title">Architecture Pipeline</h3>
                  <div className="arch-flow-diagram">
                    <div className="arch-node">React Client</div>
                    <div className="arch-arrow">→</div>
                    <div className="arch-node">FastAPI Gateway</div>
                    <div className="arch-arrow">→</div>
                    <div className="arch-node">pgvector (HNSW)</div>
                    <div className="arch-arrow">→</div>
                    <div className="arch-node">LLM (qwen2.5:7b)</div>
                  </div>
                </div>

                <div className="settings-section">
                  <a
                    href="https://github.com"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-settings-action"
                    style={{ textDecoration: 'none' }}
                  >
                    <span>View Project Repository</span>
                    <ExternalLink size={14} aria-hidden="true" />
                  </a>
                </div>
              </Tabs.Content>
            </div>
          </Tabs.Root>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};

export default SettingsModal;
