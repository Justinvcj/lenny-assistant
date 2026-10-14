import React from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { AlertTriangle, X } from 'lucide-react';

export interface ClearChatsModalProps {
  isOpen: boolean;
  onConfirm: () => void;
  onClose: () => void;
  isClearing?: boolean;
}

export const ClearChatsModal: React.FC<ClearChatsModalProps> = ({
  isOpen,
  onConfirm,
  onClose,
  isClearing = false,
}) => {
  return (
    <Dialog.Root open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-backdrop" />
        <Dialog.Content
          className="dialog-card clear-chats-modal-card"
          aria-describedby="clear-desc"
          data-testid="clear-chats-modal"
        >
          <div className="dialog-header">
            <div className="dialog-title-group">
              <div className="dialog-icon-badge danger" aria-hidden="true">
                <AlertTriangle size={18} />
              </div>
              <Dialog.Title className="dialog-title">Clear all conversations?</Dialog.Title>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                className="dialog-close-btn"
                aria-label="Close dialog"
                onClick={onClose}
              >
                <X size={18} aria-hidden="true" />
              </button>
            </Dialog.Close>
          </div>

          <p id="clear-desc" className="dialog-description">
            This will permanently remove all conversations and message history from this browser. This action cannot be undone.
          </p>

          <div className="dialog-footer">
            <button
              type="button"
              className="btn-dialog-secondary"
              onClick={onClose}
              disabled={isClearing}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn-dialog-danger"
              onClick={onConfirm}
              disabled={isClearing}
              data-testid="confirm-clear-all-btn"
            >
              {isClearing ? 'Clearing...' : 'Clear All Chats'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
