import React from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X, Keyboard } from 'lucide-react';

export interface ShortcutsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface ShortcutItem {
  keys: string[];
  description: string;
}

const SHORTCUTS: ShortcutItem[] = [
  { keys: ['Ctrl', 'Shift', 'O'], description: 'Start a new chat' },
  { keys: ['Ctrl', 'B'], description: 'Toggle sidebar collapsed / expanded' },
  { keys: ['Ctrl', 'K'], description: 'Open command palette / search chats' },
  { keys: ['Ctrl', '/'], description: 'Show keyboard shortcuts' },
  { keys: ['Enter'], description: 'Send message in composer' },
  { keys: ['Shift', 'Enter'], description: 'Insert new line in composer' },
  { keys: ['Esc'], description: 'Close dialogs, menus, or mobile drawer' },
];

export const ShortcutsModal: React.FC<ShortcutsModalProps> = ({ isOpen, onClose }) => {
  return (
    <Dialog.Root open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-backdrop" />
        <Dialog.Content
          className="dialog-card shortcuts-modal-card"
          aria-describedby="shortcuts-desc"
          data-testid="shortcuts-modal"
        >
          <div className="dialog-header">
            <div className="dialog-title-group">
              <div className="dialog-icon-badge" aria-hidden="true">
                <Keyboard size={18} />
              </div>
              <Dialog.Title className="dialog-title">Keyboard Shortcuts</Dialog.Title>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                className="dialog-close-btn"
                aria-label="Close keyboard shortcuts"
                onClick={onClose}
              >
                <X size={18} aria-hidden="true" />
              </button>
            </Dialog.Close>
          </div>

          <p id="shortcuts-desc" className="dialog-description">
            Quickly navigate and control Lenny Growth Assistant using these shortcuts.
          </p>

          <div className="shortcuts-table" role="table" aria-label="Available shortcuts">
            {SHORTCUTS.map((item, idx) => (
              <div key={idx} className="shortcut-row" role="row">
                <span className="shortcut-desc" role="cell">
                  {item.description}
                </span>
                <span className="shortcut-keys" role="cell">
                  {item.keys.map((k, kIdx) => (
                    <React.Fragment key={kIdx}>
                      <kbd className="kbd-badge">{k}</kbd>
                      {kIdx < item.keys.length - 1 && <span className="kbd-plus">+</span>}
                    </React.Fragment>
                  ))}
                </span>
              </div>
            ))}
          </div>

          <div className="dialog-footer">
            <button
              type="button"
              className="btn-dialog-secondary"
              onClick={onClose}
            >
              Got it
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
