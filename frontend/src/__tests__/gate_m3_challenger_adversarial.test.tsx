import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { CitationChips } from '../components/CitationChips';
import { DEFAULT_REPHRASING_TIPS } from '../components/RefusalCard';
import { Composer } from '../components/Composer';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { MessageItem, isRefusalContent } from '../components/MessageItem';
import { App } from '../App';
import * as api from '../api';
import { CitationItem, Message, EXACT_REFUSAL_MESSAGE } from '../api';

const mockRichCitations: CitationItem[] = [
  {
    n: 1,
    chunk_id: 'chk-uuid-shreyas',
    doc_slug: 'podcast-shreyas-doshi',
    title: 'Good PM, Bad PM',
    guest: 'Shreyas Doshi',
    passage: 'PMF is not a binary milestone. It is an operational pull gradient.',
  },
  {
    n: 2,
    chunk_id: 'chk-uuid-elena',
    doc_slug: 'podcast-elena-verna',
    title: 'Product-Led Growth Playbook',
    guest: null, // Test guest fallback
    passage: 'PLG velocity expands when friction is aggressively minimized.',
  },
  {
    n: 3,
    chunk_id: 'chk-uuid-brian',
    doc_slug: 'podcast-brian-chesky',
    title: 'Design-led Companies',
    guest: '   ', // Test whitespace guest fallback
    passage: 'Great founders curate details that software defaults ignore.',
  },
];

describe('Phase 5 Final Gate Review — Adversarial Behavioral Suite (Challenger M3-1)', () => {
  // =========================================================================
  // Gate Criterion 1: Citation Chip Rendering & Expandable Sources Drawer
  // =========================================================================
  describe('Gate 1: Citation Chip Rendering & Sources Drawer Verification', () => {
    it('verifies all 4 required fields in expandable drawer: guest name, episode title, doc slug, and exact passage text', async () => {
      const user = userEvent.setup();
      render(<CitationChips citations={mockRichCitations} messageId="gate-msg-1" />);

      // Accordion is initially closed
      expect(screen.queryByText(/PMF is not a binary milestone/i)).not.toBeInTheDocument();

      // Click Sources header button to expand
      const headerBtn = screen.getByRole('button', { name: /Sources \(3\)/i });
      expect(headerBtn).toHaveAttribute('aria-expanded', 'false');
      await user.click(headerBtn);
      expect(headerBtn).toHaveAttribute('aria-expanded', 'true');

      // 1. Verify Citation S1: All 4 fields present
      expect(screen.getByText('Shreyas Doshi')).toBeInTheDocument();
      expect(screen.getByText('— Good PM, Bad PM')).toBeInTheDocument();
      expect(screen.getByText('podcast-shreyas-doshi')).toBeInTheDocument();
      const passage1 = screen.getByText('PMF is not a binary milestone. It is an operational pull gradient.');
      expect(passage1).toBeInTheDocument();
      expect(passage1).toHaveClass('source-passage-box');

      // 2. Verify Citation S2: Fallback guest name, title, slug, exact passage
      expect(screen.getAllByText('Lenny Rachitsky')).toHaveLength(2); // Fallback for null (S2) and whitespace (S3)
      expect(screen.getByText('— Product-Led Growth Playbook')).toBeInTheDocument();
      expect(screen.getByText('podcast-elena-verna')).toBeInTheDocument();
      expect(screen.getByText('PLG velocity expands when friction is aggressively minimized.')).toBeInTheDocument();

      // 3. Verify Citation S3: Whitespace guest fallback, title, slug, exact passage
      expect(screen.getByText('— Design-led Companies')).toBeInTheDocument();
      expect(screen.getByText('podcast-brian-chesky')).toBeInTheDocument();
      expect(screen.getByText('Great founders curate details that software defaults ignore.')).toBeInTheDocument();
    });

    it('clicking an individual [S#] chip directly expands sources drawer and calls onCitationSelect', async () => {
      const user = userEvent.setup();
      const handleSelect = vi.fn();
      render(
        <CitationChips
          citations={mockRichCitations}
          messageId="gate-msg-2"
          onCitationSelect={handleSelect}
          initialExpanded={false}
        />
      );

      // Initially collapsed
      expect(screen.queryByText(/PMF is not a binary milestone/i)).not.toBeInTheDocument();

      // Click S1 chip
      const chip1 = screen.getByRole('button', { name: /Source S1: Shreyas Doshi/i });
      await user.click(chip1);

      // Drawer expanded, callback fired with citation index
      expect(handleSelect).toHaveBeenCalledWith(1);
      expect(screen.getByText(/PMF is not a binary milestone/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Sources \(3\)/i })).toHaveAttribute('aria-expanded', 'true');
    });

    it('renders HTML and special characters safely without evaluating markup in passage or title', async () => {
      const xssCitations: CitationItem[] = [
        {
          n: 1,
          chunk_id: 'chk-xss',
          doc_slug: 'slug-xss',
          title: 'Alert <img src=x onerror=alert(1)> Test',
          guest: 'Guest <script>evil()</script>',
          passage: 'Safe passage <b onclick="hack()">bold</b> & special "chars" \'quotes\'',
        },
      ];

      render(<CitationChips citations={xssCitations} initialExpanded={true} />);

      // Plain text verification — no executed DOM scripts
      expect(screen.getByText(/Alert <img src=x onerror=alert\(1\)> Test/)).toBeInTheDocument();
      expect(screen.getByText(/Guest <script>evil\(\)<\/script>/)).toBeInTheDocument();
      expect(screen.getByText(/Safe passage <b onclick="hack\(\)">bold<\/b> & special "chars" 'quotes'/)).toBeInTheDocument();
    });

    it('inline markdown [S#] links activate activeCitationNumber and expand sources drawer', async () => {
      const assistantMessage: Message = {
        id: 'msg-inline-test',
        session_id: 'sess-inline',
        role: 'assistant',
        content: 'Elena Verna explains growth loops [S2] and retention curves.',
        citations: mockRichCitations,
        tool_trace: [],
        degraded: false,
        created_at: new Date().toISOString(),
      };

      const user = userEvent.setup();
      render(<MessageItem message={assistantMessage} />);

      // Accordion initially closed
      expect(screen.queryByText(/PLG velocity expands when friction is aggressively minimized/i)).not.toBeInTheDocument();

      // Inline chip for [S2]
      const inlineChip = screen.getByRole('button', { name: /Jump to source S2/i });
      expect(inlineChip).toBeInTheDocument();

      // Click inline chip
      await user.click(inlineChip);

      // Sources drawer expands and renders passage S2
      expect(
        await screen.findByText(/PLG velocity expands when friction is aggressively minimized/i)
      ).toBeInTheDocument();
      expect(screen.getByText('podcast-elena-verna')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Gate Criterion 2: Refusal Card Rendering & Absence of Citations
  // =========================================================================
  describe('Gate 2: Refusal Card Behavioral Verification', () => {
    it('renders neutral RefusalCard upon receiving exact canonical refusal message', () => {
      const refusalMsg: Message = {
        id: 'msg-refusal-exact',
        session_id: 'sess-refusal',
        role: 'assistant',
        content: EXACT_REFUSAL_MESSAGE,
        citations: [],
        tool_trace: [],
        degraded: false,
        created_at: new Date().toISOString(),
      };

      const { container } = render(<MessageItem message={refusalMsg} />);

      // Canonical statement present
      expect(screen.getByText(EXACT_REFUSAL_MESSAGE)).toBeInTheDocument();

      // Rephrasing tips present
      expect(screen.getByText(/Tips for better results:/i)).toBeInTheDocument();
      for (const tip of DEFAULT_REPHRASING_TIPS) {
        expect(screen.getByText(tip)).toBeInTheDocument();
      }

      // STRICT ABSENCE OF CITATION CHIPS
      expect(container.querySelector('.citation-chip')).toBeNull();
      expect(container.querySelector('.sources-accordion')).toBeNull();
      expect(screen.queryByText(/Sources/i)).not.toBeInTheDocument();
    });

    it('STRICTLY suppresses citation chips even if backend mistakenly attaches citations to refusal', () => {
      const refusalWithOrphanCitations: Message = {
        id: 'msg-refusal-orphan',
        session_id: 'sess-refusal',
        role: 'assistant',
        content: EXACT_REFUSAL_MESSAGE,
        citations: mockRichCitations, // Non-empty citations
        tool_trace: [],
        degraded: false,
        created_at: new Date().toISOString(),
      };

      const { container } = render(<MessageItem message={refusalWithOrphanCitations} />);

      // Refusal card rendered
      expect(screen.getByRole('region', { name: /Assistant Refusal Notice/i })).toBeInTheDocument();

      // Citations MUST BE COMPLETELY ABSENT
      expect(container.querySelector('.citation-chip')).toBeNull();
      expect(container.querySelector('.sources-accordion')).toBeNull();
      expect(screen.queryByText(/podcast-shreyas-doshi/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/PMF is not a binary milestone/i)).not.toBeInTheDocument();
    });

    it('tolerates trailing period absence and outer whitespace in refusal detection', () => {
      expect(isRefusalContent("I don't have information about that in the transcripts.")).toBe(true);
      expect(isRefusalContent("I don't have information about that in the transcripts")).toBe(true);
      expect(isRefusalContent("   I don't have information about that in the transcripts. \n  ")).toBe(true);
      expect(isRefusalContent("\tI don't have information about that in the transcripts\t")).toBe(true);

      // Adversarial: Substring in non-refusal answer should NOT be treated as refusal
      expect(
        isRefusalContent(
          "I don't have information about that in the transcripts, but here is what Shreyas says about PMF."
        )
      ).toBe(false);
    });

    it('renders normal markdown assistant bubble and NOT RefusalCard when refusal text is embedded in larger answer', () => {
      const partialMatchMsg: Message = {
        id: 'msg-partial-refusal',
        session_id: 'sess-partial',
        role: 'assistant',
        content:
          "Note: I don't have information about that in the transcripts, but I can answer regarding growth loops [S1].",
        citations: [mockRichCitations[0]],
        tool_trace: [],
        degraded: false,
        created_at: new Date().toISOString(),
      };

      const { container } = render(<MessageItem message={partialMatchMsg} />);

      // Should NOT render RefusalCard
      expect(container.querySelector('.refusal-card')).toBeNull();
      expect(screen.queryByText(/Tips for better results:/i)).not.toBeInTheDocument();

      // Should render normal response and citations
      expect(screen.getByRole('article', { name: 'Assistant Response' })).toBeInTheDocument();
      expect(container.querySelector('.sources-accordion')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Gate Criterion 3: Composer Keyboard Behavior & 4000 Char Enforcement
  // =========================================================================
  describe('Gate 3: Composer Keyboard Behavior & Char Limits', () => {
    it('Enter sends valid message, trims outer whitespace, and clears textarea', async () => {
      const user = userEvent.setup();
      const handleSend = vi.fn();
      render(<Composer onSend={handleSend} />);

      const textarea = screen.getByTestId('composer-textarea');
      await user.type(textarea, '   How do founders give away Legos?   {Enter}');

      expect(handleSend).toHaveBeenCalledTimes(1);
      expect(handleSend).toHaveBeenCalledWith('How do founders give away Legos?');
      expect(textarea).toHaveValue('');
      expect(screen.getByTestId('char-counter')).toHaveTextContent('0 / 4,000');
    });

    it('Shift+Enter inserts newline without submitting', async () => {
      const user = userEvent.setup();
      const handleSend = vi.fn();
      render(<Composer onSend={handleSend} />);

      const textarea = screen.getByTestId('composer-textarea');
      await user.type(textarea, 'First line{Shift>}{Enter}{/Shift}Second line');

      expect(handleSend).not.toHaveBeenCalled();
      expect(textarea).toHaveValue('First line\nSecond line');
    });

    it('does NOT submit on Enter during IME composition', () => {
      const handleSend = vi.fn();
      render(<Composer onSend={handleSend} initialValue="Konnichiwa" />);

      const textarea = screen.getByTestId('composer-textarea');
      const event = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
      Object.defineProperty(event, 'isComposing', { value: true });
      fireEvent(textarea, event);

      expect(handleSend).not.toHaveBeenCalled();
    });

    it('blocks submission on whitespace-only input (spaces, tabs, newlines)', async () => {
      const user = userEvent.setup();
      const handleSend = vi.fn();
      render(<Composer onSend={handleSend} />);

      const textarea = screen.getByTestId('composer-textarea');
      const sendBtn = screen.getByTestId('composer-send-btn');

      // Empty
      await user.type(textarea, '{Enter}');
      expect(handleSend).not.toHaveBeenCalled();
      expect(sendBtn).toBeDisabled();

      // Spaces
      await user.type(textarea, '    {Enter}');
      expect(handleSend).not.toHaveBeenCalled();
      expect(sendBtn).toBeDisabled();

      // Newlines and tabs
      await user.clear(textarea);
      await user.type(textarea, '\n\t\n  \n{Enter}');
      expect(handleSend).not.toHaveBeenCalled();
      expect(sendBtn).toBeDisabled();
    });

    it('enforces 4,000 character limit: styling tiers (default -> warning -> limit) and blocks send above 4000', () => {
      const handleSend = vi.fn();
      const { rerender } = render(<Composer onSend={handleSend} initialValue={'a'.repeat(3500)} />);

      let counter = screen.getByTestId('char-counter');
      const sendBtn = screen.getByTestId('composer-send-btn');

      // 1. At 3500 chars: Normal tier
      expect(counter).toHaveClass('char-counter');
      expect(counter).not.toHaveClass('warning');
      expect(counter).not.toHaveClass('limit');
      expect(sendBtn).toBeEnabled();

      // 2. At 3501 chars: Warning tier
      rerender(<Composer onSend={handleSend} initialValue={'a'.repeat(3501)} />);
      counter = screen.getByTestId('char-counter');
      expect(counter).toHaveClass('warning');
      expect(counter).not.toHaveClass('limit');
      expect(sendBtn).toBeEnabled();

      // 3. At 4000 chars: Limit tier, but submittable
      rerender(<Composer onSend={handleSend} initialValue={'a'.repeat(4000)} />);
      counter = screen.getByTestId('char-counter');
      expect(counter).toHaveClass('limit');
      expect(sendBtn).toBeEnabled();

      // 4. At 4001 chars: Over limit tier, send button disabled, Enter blocked
      rerender(<Composer onSend={handleSend} initialValue={'a'.repeat(4001)} />);
      counter = screen.getByTestId('char-counter');
      expect(counter).toHaveClass('limit');
      expect(screen.getByTestId('composer-textarea')).toHaveAttribute('aria-invalid', 'true');
      expect(screen.getByTestId('composer-send-btn')).toBeDisabled();

      // Enter key blocked
      const textarea = screen.getByTestId('composer-textarea');
      fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
      expect(handleSend).not.toHaveBeenCalled();
    });

    it('disables composer input and send button during inflight request', () => {
      const handleSend = vi.fn();
      render(<Composer onSend={handleSend} inflight={true} initialValue="Inflight prompt" />);

      expect(screen.getByTestId('composer-textarea')).toBeDisabled();
      expect(screen.getByTestId('composer-send-btn')).toBeDisabled();
    });
  });

  // =========================================================================
  // Gate Criterion 4: Loading Skeleton, Timer & Cancel Abort Signal
  // =========================================================================
  describe('Gate 4: Loading Skeleton Timer & Cancel Abort Signal Verification', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('verifies elapsed timer increments every second and transitions stage text', () => {
      const handleCancel = vi.fn();
      render(<LoadingSkeleton onCancel={handleCancel} />);

      const timer = screen.getByTestId('skeleton-elapsed-timer');
      const stage = screen.getByTestId('skeleton-stage-text');

      expect(timer).toHaveTextContent('(0s)');
      expect(stage).toHaveTextContent('Searching transcripts...');

      // Advance by 1 second
      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(timer).toHaveTextContent('(1s)');
      expect(stage).toHaveTextContent('Searching transcripts...');

      // Advance by 3 more seconds (total 4s)
      act(() => {
        vi.advanceTimersByTime(3000);
      });
      expect(timer).toHaveTextContent('(4s)');
      expect(stage).toHaveTextContent('Synthesizing answer...');

      // Advance by 5 more seconds (total 9s)
      act(() => {
        vi.advanceTimersByTime(5000);
      });
      expect(timer).toHaveTextContent('(9s)');
      expect(stage).toHaveTextContent('Synthesizing answer...');
    });

    it('App integration: Cancel button triggers abort cleanly without UI hang and allows immediate retry', async () => {
      vi.useRealTimers();

      let activeSignal: AbortSignal | undefined;
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
      vi.spyOn(api, 'createSession').mockResolvedValue({
        id: 'sess-abort-test',
        title: 'Cancel test',
        llm_provider: 'ollama',
        llm_model: 'qwen2.5:7b',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });

      // Mock first sendMessage to hang until aborted
      vi.spyOn(api, 'sendMessage')
        .mockImplementationOnce(async (_id, _msg, signal) => {
          activeSignal = signal;
          if (signal) {
            signal.addEventListener('abort', abortSpy);
          }
          return new Promise((_resolve, reject) => {
            signal?.addEventListener('abort', () => {
              const abortErr = new DOMException('The user aborted a request.', 'AbortError');
              reject(abortErr);
            });
          });
        })
        .mockImplementationOnce(async (_id, _msg) => {
          // Second call resolves cleanly
          return {
            message: {
              id: 'm-second-msg',
              session_id: 'sess-abort-test',
              role: 'assistant',
              content: 'Second message succeeded without hang.',
              citations: [],
              tool_trace: [],
              degraded: false,
              latency_ms: 1500,
              created_at: new Date().toISOString(),
            },
            citations: [],
            intent: 'QA',
            degraded: false,
            latency_ms: 1500,
          };
        });

      render(<App />);

      // Step 1: Send first message
      const textarea = await screen.findByTestId('composer-textarea');
      fireEvent.change(textarea, { target: { value: 'First long running query' } });
      const sendBtn = screen.getByTestId('composer-send-btn');
      fireEvent.click(sendBtn);

      // Verify loading skeleton appears and signal is active
      const cancelBtn = await screen.findByTestId('skeleton-cancel-btn');
      expect(cancelBtn).toBeInTheDocument();
      expect(activeSignal).toBeDefined();
      expect(activeSignal?.aborted).toBe(false);

      // Step 2: Trigger Cancel
      fireEvent.click(cancelBtn);

      // Verify abort fired cleanly
      expect(activeSignal?.aborted).toBe(true);
      expect(abortSpy).toHaveBeenCalledTimes(1);

      // Verify loading skeleton unmounted and optimistic message rolled back
      await waitFor(() => {
        expect(screen.queryByTestId('loading-skeleton-container')).not.toBeInTheDocument();
      });
      expect(screen.queryByText('First long running query')).not.toBeInTheDocument();

      // Verify NO error banner was displayed
      expect(screen.queryByTestId('error-banner')).not.toBeInTheDocument();

      // Step 3: Verify UI is NOT hung — submit a second query immediately
      expect(textarea).toBeEnabled();
      fireEvent.change(textarea, { target: { value: 'Second immediate query' } });
      fireEvent.click(sendBtn);

      // Second message completes successfully
      expect(await screen.findByText('Second message succeeded without hang.')).toBeInTheDocument();
      expect(screen.getByText('Second immediate query')).toBeInTheDocument();
    });
  });
});
