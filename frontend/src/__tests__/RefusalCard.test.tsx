import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { RefusalCard } from '../components/RefusalCard';
import { EXACT_REFUSAL_MESSAGE } from '../api';

describe('RefusalCard Component', () => {
  it('renders canonical refusal statement and default rephrasing tips', () => {
    render(<RefusalCard />);

    expect(screen.getByText(EXACT_REFUSAL_MESSAGE)).toBeInTheDocument();
    expect(screen.getByText(/Tips for better results:/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Ask about core product management topics/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Ask about specific podcast guests/i)
    ).toBeInTheDocument();
  });

  it('strictly never renders citation chips or source accordions', () => {
    const { container } = render(<RefusalCard />);

    expect(screen.queryByText(/\[S\d+\]/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Sources/i)).not.toBeInTheDocument();
    expect(container.querySelector('.citation-chip')).toBeNull();
    expect(container.querySelector('.sources-accordion')).toBeNull();
  });

  it('handles optional onTipClick handler', async () => {
    const user = userEvent.setup();
    const handleTipClick = vi.fn();
    render(<RefusalCard onTipClick={handleTipClick} />);

    const tip = screen.getByText(/Ask about specific podcast guests/i);
    await user.click(tip);

    expect(handleTipClick).toHaveBeenCalledWith(
      expect.stringContaining('specific podcast guests')
    );
  });
});
