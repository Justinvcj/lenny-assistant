import React from 'react';
import { Sparkles } from 'lucide-react';

export const STARTER_QUESTIONS = [
  'How do I know if I have PMF?',
  'What drives early retention?',
  'How should founders give away Legos?',
] as const;

export interface EmptyStateProps {
  onSelectStarterQuestion?: (question: string) => void;
  onSelectQuestion?: (question: string) => void;
  title?: string;
  description?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  onSelectStarterQuestion,
  onSelectQuestion,
  title = 'Lenny Growth Assistant',
  description = "Ask questions about product management, growth, retention, and leadership grounded directly in Lenny's Podcast transcripts.",
}) => {
  const handleSelect = (question: string) => {
    if (onSelectStarterQuestion) {
      onSelectStarterQuestion(question);
    } else if (onSelectQuestion) {
      onSelectQuestion(question);
    }
  };

  return (
    <section className="empty-state" aria-labelledby="empty-state-heading">
      <div
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '48px',
          height: '48px',
          borderRadius: '50%',
          backgroundColor: 'var(--brand-accent-bg)',
          color: 'var(--brand-accent)',
          marginBottom: '1rem',
        }}
      >
        <Sparkles size={24} aria-hidden="true" />
      </div>
      <h2 id="empty-state-heading" className="empty-state-title">
        {title}
      </h2>
      <p className="empty-state-desc">{description}</p>

      <div
        className="starter-questions-grid"
        role="group"
        aria-label="Starter questions"
      >
        {STARTER_QUESTIONS.map((question, index) => (
          <button
            key={index}
            type="button"
            className="starter-chip"
            onClick={() => handleSelect(question)}
            aria-label={`Ask question: ${question}`}
          >
            {question}
          </button>
        ))}
      </div>
    </section>
  );
};

export default EmptyState;
