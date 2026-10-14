import React from 'react';
import { Sparkles, Compass, Repeat, Layers, Tag } from 'lucide-react';

export const STARTER_QUESTIONS = [
  'How do I know if I have PMF?',
  'What drives early retention?',
  'How should founders give away Legos?',
  'What are the best frameworks for pricing?',
] as const;

export interface EmptyStateProps {
  onSelectStarterQuestion?: (question: string) => void;
  onSelectQuestion?: (question: string) => void;
  title?: string;
  description?: string;
}

interface StarterCardConfig {
  question: string;
  title: string;
  desc: string;
  icon: React.ReactNode;
}

const STARTER_CARDS: StarterCardConfig[] = [
  {
    question: 'How do I know if I have PMF?',
    title: 'Recognizing Product-Market Fit',
    desc: 'Signals, retention curves, and milestones for genuine market pull',
    icon: <Compass size={18} aria-hidden="true" />,
  },
  {
    question: 'What drives early retention?',
    title: 'Unlocking Early Retention',
    desc: 'Cohort analysis, activation habits, and compounding engagement loops',
    icon: <Repeat size={18} aria-hidden="true" />,
  },
  {
    question: 'How should founders give away Legos?',
    title: 'Giving Away Legos',
    desc: 'Scaling organizational leadership, delegation, and role evolution',
    icon: <Layers size={18} aria-hidden="true" />,
  },
  {
    question: 'What are the best frameworks for pricing?',
    title: 'Pricing & Packaging Strategy',
    desc: 'Value metrics, monetization tiers, and willingness-to-pay experiments',
    icon: <Tag size={18} aria-hidden="true" />,
  },
];

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
      {/* High-end Pill Badge */}
      <div className="hero-pill-badge" data-testid="hero-pill-badge">
        <Sparkles size={14} aria-hidden="true" />
        <span>{title}</span>
      </div>

      {/* Signature Headline pairing Sans + Instrument Serif Italic */}
      <h2 id="empty-state-heading" className="empty-state-title">
        <span className="sr-only">{title} — </span>
        Grow <em className="serif-accent">smarter</em> with Lenny's transcripts
      </h2>

      <p className="empty-state-desc">{description}</p>

      {/* 2x2 Suggested Prompt Cards Grid */}
      <div
        className="starter-questions-grid"
        role="group"
        aria-label="Starter questions"
      >
        {STARTER_CARDS.map((card, index) => (
          <button
            key={index}
            type="button"
            className="starter-chip"
            onClick={() => handleSelect(card.question)}
            aria-label={`Ask question: ${card.question}`}
          >
            <div className="starter-chip-icon">
              {card.icon}
            </div>
            <span className="starter-chip-title">{card.title}</span>
            <span className="starter-chip-desc">{card.desc}</span>
          </button>
        ))}
      </div>

      {/* Contextual Action Hints */}
      <div className="empty-state-hints">
        <span className="empty-hint-label">💡 Suggested prompts:</span>
        <button
          type="button"
          className="empty-hint-chip"
          onClick={() => handleSelect('Turn that into a Ship 30 essay')}
          aria-label="Suggest: Turn that into a Ship 30 essay"
        >
          "Turn that into a Ship 30 essay"
        </button>
        <span className="empty-hint-separator">·</span>
        <button
          type="button"
          className="empty-hint-chip"
          onClick={() => handleSelect('Make a one-pager (HTML)')}
          aria-label="Suggest: Make a one-pager (HTML)"
        >
          "Make a one-pager (HTML)"
        </button>
      </div>
    </section>
  );
};

export default EmptyState;
