import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { Sidebar } from '../components/Sidebar';
import { Session } from '../api';

const mockSessions: Session[] = [
  {
    id: 's-1',
    title: 'PMF Discussion',
    llm_provider: 'ollama',
    llm_model: 'qwen2.5:7b',
    created_at: '2026-10-10T12:00:00Z',
    updated_at: '2026-10-10T12:00:00Z',
  },
  {
    id: 's-2',
    title: 'Retention Metrics',
    llm_provider: 'ollama',
    llm_model: 'qwen2.5:7b',
    created_at: '2026-10-10T10:00:00Z',
    updated_at: '2026-10-10T10:00:00Z',
  },
];

describe('Sidebar Component', () => {
  it('renders New Chat button and session items with active highlight', () => {
    const handleSelect = vi.fn();
    const handleNewChat = vi.fn();
    const handleDelete = vi.fn();

    render(
      <Sidebar
        sessions={mockSessions}
        activeSessionId="s-1"
        isOpen={true}
        onSelectSession={handleSelect}
        onNewChat={handleNewChat}
        onDeleteSession={handleDelete}
      />
    );

    expect(screen.getByRole('button', { name: /Start a new chat session/i })).toBeInTheDocument();
    expect(screen.getByText('PMF Discussion')).toBeInTheDocument();
    expect(screen.getByText('Retention Metrics')).toBeInTheDocument();

    const option1 = screen.getByRole('option', { name: /PMF Discussion/i });
    expect(option1).toHaveAttribute('aria-selected', 'true');
  });

  it('calls onSelectSession when clicking a session', async () => {
    const user = userEvent.setup();
    const handleSelect = vi.fn();

    render(
      <Sidebar
        sessions={mockSessions}
        activeSessionId="s-1"
        isOpen={true}
        onSelectSession={handleSelect}
        onNewChat={vi.fn()}
        onDeleteSession={vi.fn()}
      />
    );

    const option2 = screen.getByRole('option', { name: /Retention Metrics/i });
    await user.click(option2);

    expect(handleSelect).toHaveBeenCalledWith('s-2');
  });

  it('opens confirmation modal and calls onDeleteSession upon confirmation', async () => {
    const user = userEvent.setup();
    const handleDelete = vi.fn();

    render(
      <Sidebar
        sessions={mockSessions}
        activeSessionId="s-1"
        isOpen={true}
        onSelectSession={vi.fn()}
        onNewChat={vi.fn()}
        onDeleteSession={handleDelete}
      />
    );

    const deleteBtn = screen.getByRole('button', { name: /Delete chat: PMF Discussion/i });
    await user.click(deleteBtn);

    expect(screen.getByText('Delete Conversation?')).toBeInTheDocument();

    const confirmBtn = screen.getByRole('button', { name: 'Delete' });
    await user.click(confirmBtn);

    expect(handleDelete).toHaveBeenCalledWith('s-1');
  });
});
