import React, { useEffect, useState } from 'react';
import { Command } from 'cmdk';
import * as Dialog from '@radix-ui/react-dialog';
import {
  MessageSquarePlus,
  PanelLeft,
  Settings,
  SunMoon,
  Keyboard,
  Download,
  Search,
} from 'lucide-react';
import { SidebarSession } from '../storage/conversationStore';
import { AppSettings, updateSettings } from '../storage/settingsStore';

export interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  conversations: SidebarSession[];
  activeSessionId: string | null;
  settings: AppSettings;
  onSettingsChange: (settings: AppSettings) => void;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onToggleSidebar: () => void;
  onOpenSettings: () => void;
  onOpenShortcuts: () => void;
  onExportCurrentChat?: () => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  open,
  onOpenChange,
  conversations,
  activeSessionId,
  settings,
  onSettingsChange,
  onSelectSession,
  onNewChat,
  onToggleSidebar,
  onOpenSettings,
  onOpenShortcuts,
  onExportCurrentChat,
}) => {
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    if (!open) {
      setSearchQuery('');
    }
  }, [open]);

  const handleToggleTheme = () => {
    const nextTheme = settings.theme === 'dark' ? 'light' : 'dark';
    const updated = updateSettings({ theme: nextTheme });
    onSettingsChange(updated);
    onOpenChange(false);
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay command-palette-overlay" />
        <Dialog.Content
          className="command-palette-content"
          aria-describedby="command-palette-description"
        >
          <Dialog.Title className="sr-only">Command Palette</Dialog.Title>
          <Dialog.Description id="command-palette-description" className="sr-only">
            Fast keyboard navigation across chats, tools, and actions
          </Dialog.Description>

          <Command className="cmdk-root" label="Quick commands and chat search">
            <div className="cmdk-header">
              <Search size={16} className="cmdk-search-icon" aria-hidden="true" />
              <Command.Input
                value={searchQuery}
                onValueChange={setSearchQuery}
                placeholder="Type a command or search conversations..."
                className="cmdk-input"
                autoFocus
              />
              <kbd className="cmdk-kbd-esc">ESC</kbd>
            </div>

            <Command.List className="cmdk-list">
              <Command.Empty className="cmdk-empty">
                No matching commands or conversations found.
              </Command.Empty>

              {/* Quick Actions Group */}
              <Command.Group heading="Actions" className="cmdk-group">
                <Command.Item
                  className="cmdk-item"
                  onSelect={() => {
                    onNewChat();
                    onOpenChange(false);
                  }}
                >
                  <MessageSquarePlus size={16} className="cmdk-item-icon" aria-hidden="true" />
                  <span>New Chat</span>
                  <div className="cmdk-item-shortcut">Ctrl+Shift+O</div>
                </Command.Item>

                <Command.Item
                  className="cmdk-item"
                  onSelect={() => {
                    onToggleSidebar();
                    onOpenChange(false);
                  }}
                >
                  <PanelLeft size={16} className="cmdk-item-icon" aria-hidden="true" />
                  <span>Toggle Sidebar</span>
                  <div className="cmdk-item-shortcut">Ctrl+B</div>
                </Command.Item>

                <Command.Item
                  className="cmdk-item"
                  onSelect={handleToggleTheme}
                >
                  <SunMoon size={16} className="cmdk-item-icon" aria-hidden="true" />
                  <span>Toggle Theme ({settings.theme === 'dark' ? 'Switch to Light' : 'Switch to Dark'})</span>
                </Command.Item>

                <Command.Item
                  className="cmdk-item"
                  onSelect={() => {
                    onOpenSettings();
                    onOpenChange(false);
                  }}
                >
                  <Settings size={16} className="cmdk-item-icon" aria-hidden="true" />
                  <span>Preferences & Settings</span>
                </Command.Item>

                <Command.Item
                  className="cmdk-item"
                  onSelect={() => {
                    onOpenShortcuts();
                    onOpenChange(false);
                  }}
                >
                  <Keyboard size={16} className="cmdk-item-icon" aria-hidden="true" />
                  <span>Keyboard Shortcuts</span>
                  <div className="cmdk-item-shortcut">Ctrl+/</div>
                </Command.Item>

                {activeSessionId && onExportCurrentChat && (
                  <Command.Item
                    className="cmdk-item"
                    onSelect={() => {
                      onExportCurrentChat();
                      onOpenChange(false);
                    }}
                  >
                    <Download size={16} className="cmdk-item-icon" aria-hidden="true" />
                    <span>Export Current Conversation</span>
                  </Command.Item>
                )}
              </Command.Group>

              {/* Conversations Group */}
              {conversations.length > 0 && (
                <Command.Group heading="Recent Conversations" className="cmdk-group">
                  {conversations.map((conv) => (
                    <Command.Item
                      key={conv.id}
                      value={`${conv.title} ${conv.id}`}
                      className={`cmdk-item ${conv.id === activeSessionId ? 'selected-chat' : ''}`}
                      onSelect={() => {
                        onSelectSession(conv.id);
                        onOpenChange(false);
                      }}
                    >
                      <span className="cmdk-chat-bullet" aria-hidden="true">
                        {conv.pinned ? '📌' : '💬'}
                      </span>
                      <span className="cmdk-chat-title">{conv.title || 'Conversation'}</span>
                      {conv.id === activeSessionId && (
                        <span className="cmdk-active-badge">Active</span>
                      )}
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
            </Command.List>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};

export default CommandPalette;
