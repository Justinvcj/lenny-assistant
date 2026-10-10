import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { X, FileCode, Copy, Check, Download, AlertTriangle } from 'lucide-react';
import { ArtifactResponse } from '../api';
import { prepareHtmlArtifact, isArtifactOversized, ARTIFACT_MAX_BYTES } from '../utils/sanitizeArtifact';

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
  const artifactType = (artifact as any)?.type;
  const isHtml = artifactType === 'html' || (artifactType !== 'markdown' && rawContent.includes('<'));

  const isOversized = isArtifactOversized(rawContent);
  const { wrappedHtml } = prepareHtmlArtifact(title, rawContent);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(rawContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.warn('Failed to copy artifact content:', err);
    }
  };

  const handleDownload = () => {
    try {
      const extension = isHtml ? 'html' : 'md';
      const mimeType = isHtml ? 'text/html;charset=utf-8' : 'text/markdown;charset=utf-8';
      const cleanFilename =
        (title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'artifact') +
        `.${extension}`;

      const blob = new Blob([rawContent], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = cleanFilename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.warn('Failed to download artifact:', err);
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

      {/* Mandatory Security Notice (docs/security.md Section 2) */}
      <div className="artifact-notice">
        Sandboxed preview: scripts and external requests are blocked.
      </div>

      {/* Oversized Warning if applicable */}
      {isOversized && (
        <div
          role="alert"
          style={{
            padding: '0.5rem 1rem',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            borderBottom: '1px solid rgba(239, 68, 68, 0.3)',
            color: '#ef4444',
            fontSize: '0.75rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <AlertTriangle size={14} aria-hidden="true" />
          <span>Artifact size exceeds {ARTIFACT_MAX_BYTES.toLocaleString()} bytes limit.</span>
        </div>
      )}

      {!artifact ? (
        <div className="artifact-empty-view">
          <FileCode size={40} style={{ opacity: 0.4, marginBottom: '0.75rem' }} />
          <h3 style={{ margin: '0 0 0.35rem', color: 'var(--text-primary)' }}>
            Artifact Panel
          </h3>
          <p style={{ margin: 0, maxWidth: '280px', lineHeight: 1.5 }}>
            Generated Ship 30 essays, playbooks, and HTML one-pagers will appear here side-by-side.
          </p>
        </div>
      ) : (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          {/* Mode Switcher Tabs & Actions */}
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

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
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

              <button
                type="button"
                onClick={handleDownload}
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
                aria-label="Download artifact"
              >
                <Download size={14} />
                <span>Download</span>
              </button>
            </div>
          </div>

          {/* Tab Content */}
          <div style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
            {activeTab === 'preview' ? (
              isHtml ? (
                <iframe
                  sandbox=""
                  srcDoc={wrappedHtml}
                  title={title}
                  style={{
                    width: '100%',
                    height: '100%',
                    border: 'none',
                    backgroundColor: '#ffffff',
                  }}
                />
              ) : (
                <div
                  className="artifact-markdown-content"
                  style={{
                    padding: '1.25rem',
                    overflow: 'auto',
                    flex: 1,
                    lineHeight: 1.6,
                    color: 'var(--text-primary)',
                  }}
                >
                  <pre style={{ display: 'none' }} aria-hidden="true">
                    {rawContent}
                  </pre>
                  <ReactMarkdown
                    components={{
                      a: ({ href, children, ...props }) => {
                        const safeHref =
                          href && !href.trim().toLowerCase().startsWith('javascript:')
                            ? href
                            : '#';
                        return (
                          <a
                            href={safeHref}
                            target="_blank"
                            rel="noopener noreferrer"
                            {...props}
                          >
                            {children}
                          </a>
                        );
                      },
                    }}
                  >
                    {rawContent}
                  </ReactMarkdown>
                </div>
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
                  overflow: 'auto',
                  flex: 1,
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
