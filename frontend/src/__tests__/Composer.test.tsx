import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { Composer } from '../components/Composer';

describe('Composer Component', () => {
  it('renders textarea, character counter, send button, and quick-action chips', () => {
    const handleSend = vi.fn();
    render(<Composer onSend={handleSend} />);

    expect(screen.getByTestId('composer-textarea')).toBeInTheDocument();
    expect(screen.getByTestId('char-counter')).toHaveTextContent('0 / 4,000');
    expect(screen.getByTestId('composer-send-btn')).toBeDisabled();
    expect(screen.getByText('Turn that into a Ship 30 essay')).toBeInTheDocument();
    expect(screen.getByText('Make a one-pager (HTML)')).toBeInTheDocument();
  });

  it('updates character count and enables send button when user enters valid text', async () => {
    const user = userEvent.setup();
    const handleSend = vi.fn();
    render(<Composer onSend={handleSend} />);

    const textarea = screen.getByTestId('composer-textarea');
    await user.type(textarea, 'What drives retention?');

    expect(screen.getByTestId('char-counter')).toHaveTextContent('22 / 4,000');
    expect(screen.getByTestId('composer-send-btn')).toBeEnabled();
  });

  it('submits on Enter key and clears textarea and counter', async () => {
    const user = userEvent.setup();
    const handleSend = vi.fn();
    render(<Composer onSend={handleSend} />);

    const textarea = screen.getByTestId('composer-textarea');
    await user.type(textarea, 'Hello Lenny{Enter}');

    expect(handleSend).toHaveBeenCalledTimes(1);
    expect(handleSend).toHaveBeenCalledWith('Hello Lenny');
    expect(textarea).toHaveValue('');
    expect(screen.getByTestId('char-counter')).toHaveTextContent('0 / 4,000');
  });

  it('inserts newline on Shift+Enter without submitting', async () => {
    const user = userEvent.setup();
    const handleSend = vi.fn();
    render(<Composer onSend={handleSend} />);

    const textarea = screen.getByTestId('composer-textarea');
    await user.type(textarea, 'Line 1{Shift>}{Enter}{/Shift}Line 2');

    expect(handleSend).not.toHaveBeenCalled();
    expect(textarea).toHaveValue('Line 1\nLine 2');
  });

  it('applies progressive warning styles and blocks submission beyond 4,000 characters', async () => {
    const handleSend = vi.fn();
    const { rerender } = render(<Composer onSend={handleSend} initialValue={'a'.repeat(3500)} />);

    let counter = screen.getByTestId('char-counter');
    expect(counter).toHaveClass('char-counter');
    expect(counter).not.toHaveClass('warning');

    // Warning state: 3501 - 3999
    rerender(<Composer onSend={handleSend} initialValue={'a'.repeat(3501)} />);
    counter = screen.getByTestId('char-counter');
    expect(counter).toHaveClass('warning');

    // Limit state: 4000
    rerender(<Composer onSend={handleSend} initialValue={'a'.repeat(4000)} />);
    counter = screen.getByTestId('char-counter');
    expect(counter).toHaveClass('limit');

    // Over limit: 4001
    rerender(<Composer onSend={handleSend} initialValue={'a'.repeat(4001)} />);
    counter = screen.getByTestId('char-counter');
    expect(counter).toHaveClass('limit');
    expect(screen.getByTestId('composer-send-btn')).toBeDisabled();
  });

  it('disables textarea, send button, and quick-action chips while inflight', () => {
    const handleSend = vi.fn();
    render(<Composer onSend={handleSend} inflight={true} initialValue="Waiting question" />);

    expect(screen.getByTestId('composer-textarea')).toBeDisabled();
    expect(screen.getByTestId('composer-send-btn')).toBeDisabled();
    expect(screen.getByText('Turn that into a Ship 30 essay')).toBeDisabled();
    expect(screen.getByText('Make a one-pager (HTML)')).toBeDisabled();
  });

  it('triggers quick-action chip click handler', async () => {
    const user = userEvent.setup();
    const handleSend = vi.fn();
    const handleQuickAction = vi.fn();
    render(<Composer onSend={handleSend} onQuickAction={handleQuickAction} />);

    const essayChip = screen.getByText('Turn that into a Ship 30 essay');
    await user.click(essayChip);

    expect(handleQuickAction).toHaveBeenCalledWith('Turn that into a Ship 30 essay');
  });
});
