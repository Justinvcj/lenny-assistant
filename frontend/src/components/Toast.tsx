import React from 'react';
import * as ToastPrimitive from '@radix-ui/react-toast';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

export interface ToastItem {
  id: string;
  message: string;
  type?: 'success' | 'info' | 'error';
}

export interface ToastProps {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}

export const ToastNotificationManager: React.FC<ToastProps> = ({ toasts, onDismiss }) => {
  return (
    <ToastPrimitive.Provider swipeDirection="right" duration={3500}>
      {toasts.map((t) => (
        <ToastPrimitive.Root
          key={t.id}
          className={`toast-root toast-${t.type || 'info'}`}
          onOpenChange={(open) => {
            if (!open) onDismiss(t.id);
          }}
        >
          <div className="toast-icon-wrapper" aria-hidden="true">
            {t.type === 'error' ? (
              <AlertCircle size={16} />
            ) : t.type === 'success' ? (
              <CheckCircle2 size={16} />
            ) : (
              <Info size={16} />
            )}
          </div>
          <div className="toast-content">
            <ToastPrimitive.Description className="toast-description">
              {t.message}
            </ToastPrimitive.Description>
          </div>
          <ToastPrimitive.Close className="toast-close" aria-label="Close notification">
            <X size={14} aria-hidden="true" />
          </ToastPrimitive.Close>
        </ToastPrimitive.Root>
      ))}
      <ToastPrimitive.Viewport className="toast-viewport" />
    </ToastPrimitive.Provider>
  );
};

export default ToastNotificationManager;
