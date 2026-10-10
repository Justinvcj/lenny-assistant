import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { Header } from '../components/Header';

describe('Header Component', () => {
  it('renders application brand, model badge, and live online health status', () => {
    const handleToggle = vi.fn();
    render(
      <Header
        provider="ollama"
        model="qwen2.5:7b"
        healthStatus="ok"
        onToggleSidebar={handleToggle}
      />
    );

    expect(screen.getByText('Lenny Growth Assistant')).toBeInTheDocument();
    expect(screen.getByText('ollama · qwen2.5:7b')).toBeInTheDocument();
    expect(screen.getByText('online')).toBeInTheDocument();
  });

  it('renders degraded and offline health badges correctly', () => {
    const { rerender } = render(
      <Header
        provider="ollama"
        model="qwen2.5:7b"
        healthStatus="degraded"
        onToggleSidebar={vi.fn()}
      />
    );
    expect(screen.getByText('degraded')).toBeInTheDocument();

    rerender(
      <Header
        provider="ollama"
        model="qwen2.5:7b"
        healthStatus="offline"
        onToggleSidebar={vi.fn()}
      />
    );
    expect(screen.getByText('offline')).toBeInTheDocument();
  });

  it('triggers onToggleSidebar when mobile hamburger button is clicked', async () => {
    const user = userEvent.setup();
    const handleToggle = vi.fn();
    render(<Header onToggleSidebar={handleToggle} isSidebarOpen={false} />);

    const toggleBtn = screen.getByRole('button', { name: /Open sidebar navigation/i });
    await user.click(toggleBtn);

    expect(handleToggle).toHaveBeenCalledTimes(1);
  });
});
