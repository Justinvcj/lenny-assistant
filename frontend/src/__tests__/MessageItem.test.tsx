import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { MessageItem } from '../components/MessageItem';
import { Message, EXACT_REFUSAL_MESSAGE } from '../api';

describe('MessageItem Component', () => {
  it('renders user message bubble aligned to the right', () => {
    const userMsg: Message = {
      id: 'm1',
      session_id: 's1',
      role: 'user',
      content: 'How do I know if I have PMF?',
      citations: [],
      tool_trace: [],
      degraded: false,
      created_at: '2026-10-10T12:00:00Z',
    };

    const { container } = render(<MessageItem message={userMsg} />);
    expect(screen.getByText('How do I know if I have PMF?')).toBeInTheDocument();
    expect(container.querySelector('.message-user')).toBeInTheDocument();
  });

  it('renders assistant response with markdown, latency tag, and citations', () => {
    const assistantMsg: Message = {
      id: 'm2',
      session_id: 's1',
      role: 'assistant',
      content: 'PMF is defined by **exponential pull** and customer retention [S1]. For more details visit [Lenny Newsletter](https://lennysnewsletter.com).',
      citations: [
        {
          n: 1,
          chunk_id: 'c1',
          doc_slug: 'podcast-shreyas',
          title: 'PMF Principles',
          guest: 'Shreyas Doshi',
          passage: 'Exponential pull is the truest indicator.',
        },
      ],
      tool_trace: [],
      degraded: false,
      latency_ms: 2400,
      created_at: '2026-10-10T12:00:05Z',
    };

    render(<MessageItem message={assistantMsg} />);

    expect(screen.getByText(/2.4s/i)).toBeInTheDocument();
    expect(screen.getByText('exponential pull')).toBeInTheDocument();

    // Link security: target="_blank" and rel="noopener noreferrer"
    const link = screen.getByRole('link', { name: 'Lenny Newsletter' });
    expect(link).toHaveAttribute('href', 'https://lennysnewsletter.com');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');

    // Citations
    expect(screen.getByRole('button', { name: /Sources \(1\)/i })).toBeInTheDocument();
  });

  it('renders degraded badge when degraded is true', () => {
    const degradedMsg: Message = {
      id: 'm3',
      session_id: 's1',
      role: 'assistant',
      content: 'Answered via fallback provider.',
      citations: [],
      tool_trace: [],
      degraded: true,
      created_at: '2026-10-10T12:00:05Z',
    };

    render(<MessageItem message={degradedMsg} />);
    expect(screen.getByText('Degraded')).toBeInTheDocument();
  });

  it('routes to RefusalCard when content matches EXACT_REFUSAL_MESSAGE', () => {
    const refusalMsg: Message = {
      id: 'm4',
      session_id: 's1',
      role: 'assistant',
      content: EXACT_REFUSAL_MESSAGE,
      citations: [],
      tool_trace: [],
      degraded: false,
      created_at: '2026-10-10T12:00:05Z',
    };

    const { container } = render(<MessageItem message={refusalMsg} />);
    expect(screen.getByText(EXACT_REFUSAL_MESSAGE)).toBeInTheDocument();
    expect(screen.getByText(/Tips for better results:/i)).toBeInTheDocument();
    expect(container.querySelector('.refusal-card')).toBeInTheDocument();
    expect(container.querySelector('.sources-accordion')).toBeNull();
  });

  it('triggers onCitationClick when inline [S#] chip is clicked', async () => {
    const user = userEvent.setup();
    const handleCitationClick = vi.fn();

    const assistantMsg: Message = {
      id: 'm5',
      session_id: 's1',
      role: 'assistant',
      content: 'Here is an insight from [S1] regarding growth.',
      citations: [
        {
          n: 1,
          chunk_id: 'c1',
          doc_slug: 'podcast-elena',
          title: 'PLG',
          guest: 'Elena Verna',
          passage: 'PLG passage.',
        },
      ],
      tool_trace: [],
      degraded: false,
      created_at: '2026-10-10T12:00:05Z',
    };

    render(<MessageItem message={assistantMsg} onCitationClick={handleCitationClick} />);

    const inlineChip = screen.getByRole('button', { name: /Jump to source S1/i });
    await user.click(inlineChip);

    expect(handleCitationClick).toHaveBeenCalledWith(1);
  });
});
