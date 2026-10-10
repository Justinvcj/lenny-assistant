import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { CitationChips } from '../components/CitationChips';
import { CitationItem } from '../api';

const mockCitations: CitationItem[] = [
  {
    n: 1,
    chunk_id: 'chunk-uuid-1',
    doc_slug: 'podcast-shreyas-doshi',
    title: 'Good Product Manager, Bad Product Manager',
    guest: 'Shreyas Doshi',
    passage: 'PMF is not a binary milestone. It is a gradient of pull and retention.',
  },
  {
    n: 2,
    chunk_id: 'chunk-uuid-2',
    doc_slug: 'podcast-elena-verna',
    title: 'Product-Led Growth Playbook',
    guest: null, // Test guest fallback
    passage: 'PLG flywheel spins faster when onboarding friction is eliminated.',
  },
];

describe('CitationChips Component', () => {
  it('renders interactive [S#] chips and collapsed Sources header', () => {
    render(<CitationChips citations={mockCitations} />);

    expect(screen.getByRole('button', { name: /Source S1: Shreyas Doshi — Good Product Manager, Bad Product Manager/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Source S2/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Sources \(2\)/i })).toBeInTheDocument();
    expect(screen.queryByText(/PMF is not a binary milestone/i)).not.toBeInTheDocument();
  });

  it('expands accordion when Sources header is clicked, showing passages and guest names', async () => {
    const user = userEvent.setup();
    render(<CitationChips citations={mockCitations} />);

    const headerBtn = screen.getByRole('button', { name: /Sources \(2\)/i });
    await user.click(headerBtn);

    expect(screen.getByText(/PMF is not a binary milestone/i)).toBeInTheDocument();
    expect(screen.getByText(/PLG flywheel spins faster/i)).toBeInTheDocument();
    expect(screen.getByText('Shreyas Doshi')).toBeInTheDocument();
    expect(screen.getByText('Lenny Rachitsky')).toBeInTheDocument(); // Fallback for null guest
  });

  it('expands accordion and highlights passage when citation chip is clicked', async () => {
    const user = userEvent.setup();
    const handleSelect = vi.fn();
    render(<CitationChips citations={mockCitations} onCitationSelect={handleSelect} />);

    const chip1 = screen.getByRole('button', { name: /Source S1:/i });
    await user.click(chip1);

    expect(handleSelect).toHaveBeenCalledWith(1);
    expect(screen.getByText(/PMF is not a binary milestone/i)).toBeInTheDocument();
  });

  it('renders nothing when citations array is empty', () => {
    const { container } = render(<CitationChips citations={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
