import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { EmptyState, STARTER_QUESTIONS } from '../components/EmptyState';

describe('EmptyState Component', () => {
  it('renders welcome title, subtitle, and all 3 canonical starter question chips', () => {
    const handleSelect = vi.fn();
    render(<EmptyState onSelectStarterQuestion={handleSelect} />);

    expect(screen.getByText('Lenny Growth Assistant')).toBeInTheDocument();
    expect(
      screen.getByText(/Ask questions about product management, growth, retention/i)
    ).toBeInTheDocument();

    for (const q of STARTER_QUESTIONS) {
      expect(screen.getByRole('button', { name: `Ask question: ${q}` })).toBeInTheDocument();
    }
  });

  it('triggers onSelectStarterQuestion with the clicked question text', async () => {
    const user = userEvent.setup();
    const handleSelect = vi.fn();
    render(<EmptyState onSelectStarterQuestion={handleSelect} />);

    const chip = screen.getByRole('button', {
      name: 'Ask question: How do I know if I have PMF?',
    });
    await user.click(chip);

    expect(handleSelect).toHaveBeenCalledWith('How do I know if I have PMF?');
  });
});
