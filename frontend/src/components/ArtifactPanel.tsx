import React, { useState } from 'react';
import { X, FileCode, Copy, Check } from 'lucide-react';
import { ArtifactResponse } from '../api';

export interface ArtifactPanelProps {
  isOpen: boolean;
  artifact?:
    | ArtifactResponse
    | {
        id?: string;
        title: string;
        content?: string;
        html?: string;
        type?: string;
      }
    | null;
  onClose: () => void;
}

export const ArtifactPanel: React.FC<ArtifactPanelProps> = ({
  isOpen,
  artifact,
  onClose,
}) => {
  const [activeTab, setActiveTab] = useState<'preview' | 'source'>('preview');
  const [copied, setCopied] = useState<boolean>(false);

  if (!isOpen) {
    return <aside className="artifact-panel hidden" aria-hidden="true" />;
  }

  const rawContent =
    artifact?.content || (artifact as any)?.html || '';
  const title = artifact?.title || 'Generated Artifact';
  const isHtml = (artifact as any)?.type === 'html' || rawContent.includes('<');

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(rawContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.warn('Failed to copy artifact content:', err);
    }
  };

  return (
    <aside
      className="artifact-panel"
      aria-label="Artifact preview panel"
      role="complementary"
    >
      {/* Header */}
      <div className="artifact-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}>
          <FileCode size={18} color="var(--brand-accent)" aria-hidden="true" />
          <h2 className="artifact-title" title={title}>
            {title}
          </h2>
        </div>

        <button
          type="button"
          onClick={onClose}
          className="btn-sidebar-toggle"
          aria-label="Close artifact panel"
        >
          <X size={18} aria-hidden="true" />
        </button>
      </div>

      {/* Mandatory Security Notice (docs/security.md) */}
      <div className="artifact-notice">
        Sandboxed preview: scripts and external requests are blocked.
      </div>

      {!artifact ? (
        <div className="artifact-empty-view">
          <FileCode size={40} style={{ opacity: 0.4, marginBottom: '0.75rem' }} />
          <h3 style={{ margin: '0 0 0.35rem', color: 'var(--text-primary)' }}>
            Artifact Panel (Phase 7)
          </h3>
          <p style={{ margin: 0, maxWidth: '280px', lineHeight: 1.5 }}>
            Generated Ship 30 essays, playbooks, and HTML one-pagers will appear here side-by-side.
          </p>
        </div>
      ) : (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          {/* Mode Switcher Tabs */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0.5rem 1rem',
              borderBottom: '1px solid var(--border-subtle)',
              backgroundColor: 'var(--bg-surface-inset)',
            }}
          >
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setActiveTab('preview')}
                style={{
                  background: activeTab === 'preview' ? 'var(--bg-surface)' : 'transparent',
                  color: activeTab === 'preview' ? 'var(--brand-accent)' : 'var(--text-muted)',
                  border: '1px solid',
                  borderColor: activeTab === 'preview' ? 'var(--border-subtle)' : 'transparent',
                  borderRadius: 'var(--radius-sm)',
                  padding: '0.2rem 0.6rem',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Preview
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('source')}
                style={{
                  background: activeTab === 'source' ? 'var(--bg-surface)' : 'transparent',
                  color: activeTab === 'source' ? 'var(--brand-accent)' : 'var(--text-muted)',
                  border: '1px solid',
                  borderColor: activeTab === 'source' ? 'var(--border-subtle)' : 'transparent',
                  borderRadius: 'var(--radius-sm)',
                  padding: '0.2rem 0.6rem',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Source
              </button>
            </div>

            <button
              type="button"
              onClick={handleCopy}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                background: 'transparent',
                border: 'none',
                color: 'var(--text-muted)',
                fontSize: '0.75rem',
                cursor: 'pointer',
              }}
              aria-label="Copy artifact content"
            >
              {copied ? <Check size={14} color="var(--status-ok)" /> : <Copy size={14} />}
              <span>{copied ? 'Copied' : 'Copy'}</span>
            </button>
          </div>

          {/* Tab Content */}
          <div style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
            {activeTab === 'preview' ? (
              isHtml ? (
                <iframe
                  sandbox=""
                  srcDoc={rawContent}
                  title={title}
                  style={{
                    width: '100%',
                    height: '100%',
                    border: 'none',
                    backgroundColor: '#ffffff',
                  }}
                />
              ) : (
                <pre
                  style={{
                    margin: 0,
                    padding: '1rem',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.85rem',
                    color: 'var(--text-secondary)',
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {rawContent}
                </pre>
              )
            ) : (
              <pre
                style={{
                  margin: 0,
                  padding: '1rem',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.8rem',
                  color: 'var(--text-secondary)',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                }}
              >
                {rawContent}
              </pre>
            )}
          </div>
        </div>
      )}
    </aside>
  );
};

export default ArtifactPanel;
