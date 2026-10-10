import React, { useState, useRef, useEffect, useCallback } from 'react';
import { BookOpen, ChevronDown } from 'lucide-react';
import { CitationItem } from '../api';

export interface CitationChipProps {
  citationNumber: number;
  label?: string;
  isActive?: boolean;
  onClick: (citationNumber: number) => void;
  guest?: string | null;
  title?: string;
}

export const CitationChip: React.FC<CitationChipProps> = ({
  citationNumber,
  label,
  isActive = false,
  onClick,
  guest,
  title,
}) => {
  const displayText = label || `[S${citationNumber}]`;
  const accessibleLabel = guest && title 
    ? `Source S${citationNumber}: ${guest} — ${title}` 
    : `Source S${citationNumber}`;

  return (
    <button
      type="button"
      className={`citation-chip ${isActive ? 'active' : ''}`}
      onClick={() => onClick(citationNumber)}
      aria-label={accessibleLabel}
      title={accessibleLabel}
    >
      {displayText}
    </button>
  );
};

export interface CitationChipsProps {
  citations: CitationItem[];
  messageId?: string;
  onCitationSelect?: (citationNumber: number) => void;
  initialExpanded?: boolean;
  activeCitationNumber?: number | null;
}

export const CitationChips: React.FC<CitationChipsProps> = ({
  citations,
  messageId = 'msg',
  onCitationSelect,
  initialExpanded = false,
  activeCitationNumber,
}) => {
  const [isExpanded, setIsExpanded] = useState(initialExpanded);
  const [highlightedId, setHighlightedId] = useState<number | null>(null);
  const highlightTimeoutRef = useRef<number | null>(null);

  if (!citations || citations.length === 0) {
    return null;
  }

  const handleChipClick = useCallback((citationNumber: number) => {
    setIsExpanded(true);
    setHighlightedId(citationNumber);

    if (onCitationSelect) {
      onCitationSelect(citationNumber);
    }

    setTimeout(() => {
      const elementId = `source-item-${messageId}-${citationNumber}`;
      const element = document.getElementById(elementId);
      if (element) {
        const prefersReducedMotion =
          typeof window !== 'undefined' &&
          window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;

        element.scrollIntoView({
          behavior: prefersReducedMotion ? 'auto' : 'smooth',
          block: 'nearest',
        });
        element.focus?.();
      }
    }, 50);

    if (highlightTimeoutRef.current) {
      window.clearTimeout(highlightTimeoutRef.current);
    }
    highlightTimeoutRef.current = window.setTimeout(() => {
      setHighlightedId(null);
    }, 3000);
  }, [messageId, onCitationSelect]);

  useEffect(() => {
    if (activeCitationNumber !== undefined && activeCitationNumber !== null) {
      handleChipClick(activeCitationNumber);
    }
  }, [activeCitationNumber, handleChipClick]);

  useEffect(() => {
    return () => {
      if (highlightTimeoutRef.current) {
        window.clearTimeout(highlightTimeoutRef.current);
      }
    };
  }, []);

  const accordionId = `sources-accordion-${messageId}`;
  const headerId = `sources-header-${messageId}`;

  return (
    <div className="sources-accordion" role="region" aria-label="Grounded transcript sources">
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: '0.4rem',
          marginBottom: '0.65rem',
        }}
      >
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>
          Sources:
        </span>
        {citations.map((c) => (
          <CitationChip
            key={`chip-${c.n}`}
            citationNumber={c.n}
            isActive={highlightedId === c.n}
            onClick={handleChipClick}
            guest={c.guest}
            title={c.title}
          />
        ))}
      </div>

      <button
        id={headerId}
        type="button"
        className="sources-header"
        onClick={() => setIsExpanded((prev) => !prev)}
        aria-expanded={isExpanded}
        aria-controls={accordionId}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <BookOpen size={16} aria-hidden="true" style={{ color: 'var(--brand-accent)' }} />
          <span>Sources ({citations.length})</span>
        </span>
        <ChevronDown
          size={16}
          className={`sources-chevron ${isExpanded ? 'expanded' : ''}`}
          aria-hidden="true"
        />
      </button>

      {isExpanded && (
        <div id={accordionId} className="sources-content" role="region" aria-labelledby={headerId}>
          {citations.map((c) => {
            const isHighlighted = highlightedId === c.n;
            const guestName = c.guest?.trim() || 'Lenny Rachitsky';

            return (
              <div
                key={`source-${c.n}`}
                id={`source-item-${messageId}-${c.n}`}
                className={`source-item ${isHighlighted ? 'highlighted' : ''}`}
                tabIndex={-1}
              >
                <div className="source-item-header">
                  <span className="citation-chip">[S{c.n}]</span>
                  <span className="source-item-guest">{guestName}</span>
                  <span className="source-item-title">— {c.title}</span>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.7rem',
                      color: 'var(--text-muted)',
                      marginLeft: 'auto',
                    }}
                  >
                    {c.doc_slug}
                  </span>
                </div>
                <div className="source-passage-box">
                  {c.passage}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default CitationChips;
