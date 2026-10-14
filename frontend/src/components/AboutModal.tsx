import React from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X, Sparkles, ExternalLink, Cpu, Database, Layout } from 'lucide-react';

export interface AboutModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AboutModal: React.FC<AboutModalProps> = ({ isOpen, onClose }) => {
  return (
    <Dialog.Root open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-backdrop" />
        <Dialog.Content
          className="dialog-card about-modal-card"
          aria-describedby="about-desc"
          data-testid="about-modal"
        >
          <div className="dialog-header">
            <div className="dialog-title-group">
              <div className="dialog-icon-badge" aria-hidden="true">
                <Sparkles size={18} />
              </div>
              <Dialog.Title className="dialog-title">About Lenny Growth Assistant</Dialog.Title>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                className="dialog-close-btn"
                aria-label="Close about dialog"
                onClick={onClose}
              >
                <X size={18} aria-hidden="true" />
              </button>
            </Dialog.Close>
          </div>

          <div id="about-desc" className="about-modal-body">
            <div className="about-version-tag">
              <span className="badge-pill">v0.1.0 (Production Candidate)</span>
            </div>

            <p className="about-text">
              <strong>Lenny Growth Assistant</strong> is a production-grade, grounded AI advisor built over
              transcripts from Lenny Rachitsky’s podcast. It retrieves exact insights, quotes, and frameworks from world-class
              product leaders, founders, and growth experts with strict source citations.
            </p>

            <div className="about-architecture-grid">
              <div className="about-arch-card">
                <div className="about-arch-icon">
                  <Layout size={16} />
                </div>
                <div>
                  <h4>Frontend Experience</h4>
                  <p>React 18 + TypeScript, Radix UI accessible primitives, client-side conversation storage, responsive 3-region layout.</p>
                </div>
              </div>

              <div className="about-arch-card">
                <div className="about-arch-icon">
                  <Cpu size={16} />
                </div>
                <div>
                  <h4>Grounded Agent & RAG</h4>
                  <p>FastAPI backend runtime, semantic chunking, intent routing, and citation verification.</p>
                </div>
              </div>

              <div className="about-arch-card">
                <div className="about-arch-icon">
                  <Database size={16} />
                </div>
                <div>
                  <h4>Vector Knowledge Base</h4>
                  <p>PostgreSQL 16 with pgvector extension storing high-dimensional embeddings from Ollama nomic-embed-text.</p>
                </div>
              </div>
            </div>

            <div className="about-links">
              <a
                href="https://github.com"
                target="_blank"
                rel="noreferrer noopener"
                className="about-link-btn"
              >
                <span>Documentation & Code</span>
                <ExternalLink size={14} aria-hidden="true" />
              </a>
            </div>
          </div>

          <div className="dialog-footer">
            <button
              type="button"
              className="btn-dialog-secondary"
              onClick={onClose}
            >
              Close
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
