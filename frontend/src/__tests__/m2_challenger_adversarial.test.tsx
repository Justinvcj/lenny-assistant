import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { CitationChips } from '../components/CitationChips';
import { Composer } from '../components/Composer';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { MessageItem } from '../components/MessageItem';
import { App } from '../App';
import * as api from '../api';
import { CitationItem, Message, EXACT_REFUSAL_MESSAGE } from '../api';

const mockCitations: CitationItem[] = [
  {
    n: 1,
    chunk_id: 'chunk-1',
    doc_slug: 'podcast-shreyas',
    title: 'Good PM, Bad PM',
    guest: 'Shreyas Doshi',
    passage: 'First passage text about product management.',
  },
  {
    n: 2,
    chunk_id: 'chunk-2',
    doc_slug: 'podcast-elena',
    title: 'Growth Flywheels',
    guest: null, // null guest to test fallback
    passage: 'Second passage text about growth loops.',
  },
  {
    n: 3,
    chunk_id: 'chunk-3',
    doc_slug: 'podcast-brian',
    title: 'Design-led Companies',
    guest: '   ', // whitespace guest to test fallback
    passage: 'Third passage text about founders and design.',
  },
];

describe('Challenger M2-1 Empirical Adversarial Suite', () => {
  // =========================================================================
  // Challenge 1: Citation Chips & Accordion
  // =========================================================================
  describe('1. Citation Chips & Accordion Behavior', () => {
    it('opens accordion when chip is clicked if initially closed', async () => {
      const user = userEvent.setup();
      render(<CitationChips citations={mockCitations} initialExpanded={false} />);

      // Initially closed
      expect(screen.queryByText(/First passage text/i)).not.toBeInTheDocument();

      // Click chip 1
      const chip1 = screen.getByRole('button', { name: /Source S1: Shreyas Doshi/i });
      await user.click(chip1);

      // Now open
      expect(screen.getByText(/First passage text/i)).toBeInTheDocument();
    });

    it('does NOT collapse accordion when chip is clicked while already expanded (header toggles, chip keeps expanded)', async () => {
      const user = userEvent.setup();
      render(<CitationChips citations={mockCitations} initialExpanded={true} />);

      // Initially expanded
      expect(screen.getByText(/First passage text/i)).toBeInTheDocument();

      // Click chip 1 again
      const chip1 = screen.getByRole('button', { name: /Source S1: Shreyas Doshi/i });
      await user.click(chip1);

      // Still expanded (chip click ensures isExpanded === true, does not collapse)
      expect(screen.getByText(/First passage text/i)).toBeInTheDocument();

      // Now click Sources header button — it DOES toggle closed
      const headerBtn = screen.getByRole('button', { name: /Sources \(3\)/i });
      await user.click(headerBtn);

      expect(screen.queryByText(/First passage text/i)).not.toBeInTheDocument();

      // Click header button again — toggles open
      await user.click(headerBtn);
      expect(screen.getByText(/First passage text/i)).toBeInTheDocument();
    });

    it('falls back cleanly to "Lenny Rachitsky" when guest name is null or whitespace', () => {
      render(<CitationChips citations={mockCitations} initialExpanded={true} />);

      // S1 has explicit guest
      expect(screen.getByText('Shreyas Doshi')).toBeInTheDocument();

      // S2 has guest: null -> fallback to Lenny Rachitsky
      // S3 has guest: '   ' -> fallback to Lenny Rachitsky
      const fallbackElements = screen.getAllByText('Lenny Rachitsky');
      expect(fallbackElements.length).toBe(2);

      // Accessible label on S2 chip (null guest) does not contain "null" or "undefined"
      const chip2 = screen.getByRole('button', { name: /Source S2/i });
      expect(chip2).toHaveAttribute('aria-label', 'Source S2');
    });

    it('renders null / empty DOM when citations array is empty or undefined', () => {
      const { container: containerEmpty } = render(<CitationChips citations={[]} />);
      expect(containerEmpty).toBeEmptyDOMElement();

      const { container: containerNull } = render(
        <CitationChips citations={null as unknown as CitationItem[]} />
      );
      expect(containerNull).toBeEmptyDOMElement();
    });
  });

  // =========================================================================
  // Challenge 2: Refusal Card & Suppression of Citation Chips
  // =========================================================================
  describe('2. Refusal Card & Citation Suppression', () => {
    it('renders RefusalCard when assistant response is exact canonical refusal', () => {
      const refusalMsg: Message = {
        id: 'msg-refusal-1',
        session_id: 'sess-1',
        role: 'assistant',
        content: "I don't have information about that in the transcripts.",
        citations: [],
        tool_trace: [],
        degraded: false,
        created_at: new Date().toISOString(),
      };

      render(<MessageItem message={refusalMsg} />);

      expect(screen.getByText("I don't have information about that in the transcripts.")).toBeInTheDocument();
      expect(screen.getByText(/Tips for better results:/i)).toBeInTheDocument();
      expect(screen.getByRole('region', { name: /Assistant Refusal Notice/i })).toBeInTheDocument();
    });

    it('renders RefusalCard when message has surrounding whitespace', () => {
      const refusalMsg: Message = {
        id: 'msg-refusal-ws',
        session_id: 'sess-1',
        role: 'assistant',
        content: "   I don't have information about that in the transcripts. \n  ",
        citations: [],
        tool_trace: [],
        degraded: false,
        created_at: new Date().toISOString(),
      };

      render(<MessageItem message={refusalMsg} />);
      expect(screen.getByRole('region', { name: /Assistant Refusal Notice/i })).toBeInTheDocument();
    });

    it('STRICTLY hides citation chips and sources accordion on refusal even if citations array is populated', () => {
      const refusalMsgWithCitations: Message = {
        id: 'msg-refusal-with-cits',
        session_id: 'sess-1',
        role: 'assistant',
        content: EXACT_REFUSAL_MESSAGE,
        citations: mockCitations, // Even if citations are passed
        tool_trace: [],
        degraded: false,
        created_at: new Date().toISOString(),
      };

      const { container } = render(<MessageItem message={refusalMsgWithCitations} />);

      // Refusal card is present
      expect(screen.getByRole('region', { name: /Assistant Refusal Notice/i })).toBeInTheDocument();

      // Citations MUST NOT be rendered
      expect(container.querySelector('.citation-chip')).toBeNull();
      expect(container.querySelector('.sources-accordion')).toBeNull();
      expect(screen.queryByText(/Sources/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/Good PM, Bad PM/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/First passage text/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/\[S1\]/i)).not.toBeInTheDocument();
    });

    it('renders as user message and NOT RefusalCard if a user sends the refusal text', () => {
      const userMsg: Message = {
        id: 'msg-user-mimic',
        session_id: 'sess-1',
        role: 'user',
        content: EXACT_REFUSAL_MESSAGE,
        citations: [],
        tool_trace: [],
        degraded: false,
        created_at: new Date().toISOString(),
      };

      const { container } = render(<MessageItem message={userMsg} />);
      expect(container.querySelector('.message-user')).toBeInTheDocument();
      expect(container.querySelector('.refusal-card')).toBeNull();
      expect(screen.queryByText(/Tips for better results:/i)).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // Challenge 3: Composer Keyboard, Whitespace, & In-flight State
  // =========================================================================
  describe('3. Composer Keyboard & Constraint Behaviors', () => {
    it('Enter sends message when content is valid and clears the input', async () => {
      const user = userEvent.setup();
      const handleSend = vi.fn();
      render(<Composer onSend={handleSend} />);

      const textarea = screen.getByTestId('composer-textarea');
      await user.type(textarea, 'How to measure PMF?{Enter}');

      expect(handleSend).toHaveBeenCalledTimes(1);
      expect(handleSend).toHaveBeenCalledWith('How to measure PMF?');
      expect(textarea).toHaveValue('');
    });

    it('Shift+Enter inserts newline without sending message', async () => {
      const user = userEvent.setup();
      const handleSend = vi.fn();
      render(<Composer onSend={handleSend} />);

      const textarea = screen.getByTestId('composer-textarea');
      await user.type(textarea, 'Line 1{Shift>}{Enter}{/Shift}Line 2');

      expect(handleSend).not.toHaveBeenCalled();
      expect(textarea).toHaveValue('Line 1\nLine 2');
    });

    it('does NOT send message when user presses Enter on empty input or whitespace', async () => {
      const user = userEvent.setup();
      const handleSend = vi.fn();
      render(<Composer onSend={handleSend} />);

      const textarea = screen.getByTestId('composer-textarea');

      // 1. Enter on completely empty
      await user.type(textarea, '{Enter}');
      expect(handleSend).not.toHaveBeenCalled();

      // 2. Enter on only spaces and tabs
      await user.type(textarea, '     {Enter}');
      expect(handleSend).not.toHaveBeenCalled();

      // 3. Enter on newlines
      await user.type(textarea, '\n\n   \n{Enter}');
      expect(handleSend).not.toHaveBeenCalled();
    });

    it('disables send button when content exceeds 4000 characters', async () => {
      const handleSend = vi.fn();
      const { rerender } = render(<Composer onSend={handleSend} initialValue={'a'.repeat(4000)} />);

      // Exactly 4000 characters: enabled
      const sendBtn = screen.getByTestId('composer-send-btn');
      expect(sendBtn).toBeEnabled();

      // 4001 characters: disabled
      rerender(<Composer onSend={handleSend} initialValue={'a'.repeat(4001)} />);
      expect(sendBtn).toBeDisabled();

      // Enter key when >4000 does NOT send
      const textarea = screen.getByTestId('composer-textarea');
      fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
      expect(handleSend).not.toHaveBeenCalled();
    });

    it('disables quick-action chips and prevents their invocation while inflight', async () => {
      const user = userEvent.setup();
      const handleSend = vi.fn();
      const handleQuickAction = vi.fn();

      render(
        <Composer
          onSend={handleSend}
          onQuickAction={handleQuickAction}
          inflight={true}
        />
      );

      const essayChip = screen.getByTestId('quick-action-turn-that-into-a-ship-30-essay');
      const htmlChip = screen.getByTestId('quick-action-make-a-one-pager-html-');

      expect(essayChip).toBeDisabled();
      expect(htmlChip).toBeDisabled();

      await user.click(essayChip);
      expect(handleQuickAction).not.toHaveBeenCalled();
      expect(handleSend).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // Challenge 4: Loading Skeleton & AbortController Cancellation
  // =========================================================================
  describe('4. Loading Skeleton Timer & AbortController Cancellation', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('increments elapsed timer every second and updates stage progression', () => {
      const handleCancel = vi.fn();
      render(<LoadingSkeleton onCancel={handleCancel} />);

      const timerDisplay = screen.getByTestId('skeleton-elapsed-timer');
      const stageDisplay = screen.getByTestId('skeleton-stage-text');

      expect(timerDisplay).toHaveTextContent('(0s)');
      expect(stageDisplay).toHaveTextContent('Searching transcripts...');

      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(timerDisplay).toHaveTextContent('(1s)');

      act(() => {
        vi.advanceTimersByTime(2000);
      });
      expect(timerDisplay).toHaveTextContent('(3s)');
      expect(stageDisplay).toHaveTextContent('Searching transcripts...');

      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(timerDisplay).toHaveTextContent('(4s)');
      expect(stageDisplay).toHaveTextContent('Synthesizing answer...');
    });

    it('invokes onCancel callback when Cancel button is clicked', () => {
      const handleCancel = vi.fn();
      render(<LoadingSkeleton onCancel={handleCancel} />);

      const cancelBtn = screen.getByTestId('skeleton-cancel-btn');
      fireEvent.click(cancelBtn);

      expect(handleCancel).toHaveBeenCalledTimes(1);
    });

    it('App integration: clicking Cancel invokes abort() on the active AbortController', async () => {
      vi.useRealTimers();

      let capturedSignal: AbortSignal | undefined;
      const abortSpy = vi.fn();

      vi.spyOn(api, 'listSessions').mockResolvedValue([]);
      vi.spyOn(api, 'getHealth').mockResolvedValue({
        status: 'ok',
        database: { connected: true, vector_count: 50 },
        ollama: {
          reachable: true,
          llm_model_present: true,
          embedding_model_present: true,
          llm_model: 'qwen2.5:7b',
          embedding_model: 'nomic-embed-text',
        },
      });
      vi.spyOn(api, 'getConfig').mockResolvedValue({
        provider: 'ollama',
        model: 'qwen2.5:7b',
        embedding_model: 'nomic-embed-text',
        embedding_dim: 768,
      });
      vi.spyOn(api, 'createSession').mockImplementation(async (_title, signal) => {
        if (signal) {
          signal.addEventListener('abort', abortSpy);
        }
        return {
          id: 'sess-new-1',
          title: 'New Session',
          llm_provider: 'ollama',
          llm_model: 'qwen2.5:7b',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
      });
      vi.spyOn(api, 'sendMessage').mockImplementation(async (_id, _msg, signal) => {
        capturedSignal = signal;
        if (signal) {
          signal.addEventListener('abort', abortSpy);
        }
        return new Promise((_resolve, reject) => {
          signal?.addEventListener('abort', () => {
            const err = new DOMException('The user aborted a request.', 'AbortError');
            reject(err);
          });
        });
      });

      render(<App />);

      // Find composer and send message
      const textarea = await screen.findByTestId('composer-textarea');
      fireEvent.change(textarea, { target: { value: 'Why does PMF take so long?' } });

      const sendBtn = screen.getByTestId('composer-send-btn');
      fireEvent.click(sendBtn);

      // Loading skeleton should now appear
      const cancelBtn = await screen.findByTestId('skeleton-cancel-btn');
      expect(cancelBtn).toBeInTheDocument();
      expect(capturedSignal).toBeDefined();
      expect(capturedSignal?.aborted).toBe(false);

      // Click Cancel
      fireEvent.click(cancelBtn);

      // Verify abort was called on signal
      expect(capturedSignal?.aborted).toBe(true);
      expect(abortSpy).toHaveBeenCalled();

      // Loading skeleton should disappear
      await waitFor(() => {
        expect(screen.queryByTestId('loading-skeleton-container')).not.toBeInTheDocument();
      });

      // No error banner should be displayed for voluntary cancellation
      expect(screen.queryByRole('region', { name: /Error notification/i })).not.toBeInTheDocument();
    });
  });
});
