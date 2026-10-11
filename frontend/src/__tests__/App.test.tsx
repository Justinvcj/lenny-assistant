import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { App } from '../App';
import * as api from '../api';
import {
  Session,
  SessionDetail,
  Message,
  ChatResponse,
  HealthResponse,
  ConfigResponse,
  ApiError,
  EXACT_REFUSAL_MESSAGE,
} from '../api';

const defaultHealthOk: HealthResponse = {
  status: 'ok',
  database: { connected: true, vector_count: 120 },
  ollama: {
    reachable: true,
    llm_model_present: true,
    embedding_model_present: true,
    llm_model: 'qwen2.5:7b',
    embedding_model: 'nomic-embed-text',
  },
};

const defaultConfig: ConfigResponse = {
  provider: 'ollama',
  model: 'qwen2.5:7b',
  embedding_model: 'nomic-embed-text',
  embedding_dim: 768,
};

const mockSessions: Session[] = [
  {
    id: 'sess-1',
    title: 'Retention Mechanics',
    llm_provider: 'ollama',
    llm_model: 'qwen2.5:7b',
    created_at: '2026-10-10T09:00:00Z',
    updated_at: '2026-10-10T09:00:00Z',
  },
  {
    id: 'sess-2',
    title: 'Finding PMF Faster',
    llm_provider: 'ollama',
    llm_model: 'qwen2.5:7b',
    created_at: '2026-10-10T11:00:00Z', // Newest session
    updated_at: '2026-10-10T11:00:00Z',
  },
];

const mockSession2Detail: SessionDetail = {
  ...mockSessions[1],
  messages: [
    {
      id: 'm-201',
      session_id: 'sess-2',
      role: 'user',
      content: 'What is true PMF?',
      citations: [],
      tool_trace: [],
      degraded: false,
      created_at: '2026-10-10T11:01:00Z',
    },
    {
      id: 'm-202',
      session_id: 'sess-2',
      role: 'assistant',
      content: 'PMF is exponential organic pull that strains company operations [S1].',
      citations: [
        {
          n: 1,
          chunk_id: 'chk-pmf-1',
          doc_slug: 'podcast-shreyas-doshi',
          title: 'Good PM, Bad PM',
          guest: 'Shreyas Doshi',
          passage: 'True product-market fit feels like the market is pulling the product out of your hands.',
        },
      ],
      tool_trace: [],
      degraded: false,
      latency_ms: 2800,
      created_at: '2026-10-10T11:01:03Z',
    },
  ],
};

const mockSession1Detail: SessionDetail = {
  ...mockSessions[0],
  messages: [
    {
      id: 'm-101',
      session_id: 'sess-1',
      role: 'user',
      content: 'How should we measure retention cohorts?',
      citations: [],
      tool_trace: [],
      degraded: false,
      created_at: '2026-10-10T09:01:00Z',
    },
    {
      id: 'm-102',
      session_id: 'sess-1',
      role: 'assistant',
      content: 'Measure retention curves until they flatten into asymptotic lines.',
      citations: [],
      tool_trace: [],
      degraded: false,
      latency_ms: 1900,
      created_at: '2026-10-10T09:01:02Z',
    },
  ],
};

describe('App Component Integration Suite', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(api, 'getHealth').mockResolvedValue(defaultHealthOk);
    vi.spyOn(api, 'getConfig').mockResolvedValue(defaultConfig);
    vi.spyOn(api, 'listSessions').mockResolvedValue([]);
    vi.spyOn(api, 'getSession').mockResolvedValue({
      id: 'empty',
      title: 'Empty',
      llm_provider: 'ollama',
      llm_model: 'qwen2.5:7b',
      created_at: '2026-10-10T00:00:00Z',
      updated_at: '2026-10-10T00:00:00Z',
      messages: [],
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // =========================================================================
  // 1. Initial Loading & Health/Config Diagnostics
  // =========================================================================
  describe('1. Initial Loading & Health/Config Diagnostics', () => {
    it('polls /health and /config on mount, rendering model badge and online health dot', async () => {
      render(<App />);

      expect(api.getHealth).toHaveBeenCalledTimes(1);
      expect(api.getConfig).toHaveBeenCalledTimes(1);
      expect(api.listSessions).toHaveBeenCalledTimes(1);

      // Model badge display: {provider} · {model}
      const modelBadge = await screen.findByRole('status', { name: /Active model: ollama · qwen2\.5:7b/i });
      expect(modelBadge).toBeInTheDocument();
      expect(modelBadge).toHaveTextContent('ollama · qwen2.5:7b');

      // Health connection dot status
      const healthBadge = screen.getByRole('status', { name: /Connection status: online/i });
      expect(healthBadge).toBeInTheDocument();
      expect(healthBadge).toHaveTextContent('online');

      // Empty State shown when no sessions exist (level 2 heading)
      expect(screen.getByRole('heading', { level: 2, name: /Lenny Growth Assistant/i })).toBeInTheDocument();
    });

    it('renders amber status dot when health check reports degraded status', async () => {
      vi.spyOn(api, 'getHealth').mockResolvedValue({
        status: 'degraded',
        database: { connected: true, vector_count: 0 },
        ollama: {
          reachable: true,
          llm_model_present: false,
          embedding_model_present: true,
          llm_model: '',
          embedding_model: 'nomic-embed-text',
        },
      });

      render(<App />);

      const healthBadge = await screen.findByRole('status', { name: /Connection status: degraded/i });
      expect(healthBadge).toBeInTheDocument();
      expect(healthBadge).toHaveTextContent('degraded');
    });

    it('renders offline status dot when health check fails network request', async () => {
      vi.spyOn(api, 'getHealth').mockRejectedValue(new Error('Network connection failed'));

      render(<App />);

      const healthBadge = await screen.findByRole('status', { name: /Connection status: offline/i });
      expect(healthBadge).toBeInTheDocument();
      expect(healthBadge).toHaveTextContent('offline');
    });

    it('renders knowledge base empty banner when /health reports ingested: false or 0 vectors', async () => {
      vi.spyOn(api, 'getHealth').mockResolvedValue({
        status: 'ok',
        ingested: false,
        database: { connected: true, vector_count: 0, ingested: false },
        ollama: defaultHealthOk.ollama,
      });

      render(<App />);

      const kbBanner = await screen.findByTestId('kb-empty-banner');
      expect(kbBanner).toBeInTheDocument();
      expect(kbBanner).toHaveTextContent(/Knowledge base is empty/i);
    });
  });

  // =========================================================================
  // 2. Session List Loading & Session Switching
  // =========================================================================
  describe('2. Session List Loading & Session Switching', () => {
    it('loads sessions sorted newest first, selects the first session, and loads its messages', async () => {
      vi.spyOn(api, 'listSessions').mockResolvedValue(mockSessions);
      vi.spyOn(api, 'getSession').mockImplementation(async (id: string) => {
        if (id === 'sess-2') return mockSession2Detail;
        if (id === 'sess-1') return mockSession1Detail;
        throw new Error('Not found');
      });

      render(<App />);

      // Wait for session list to load
      await waitFor(() => {
        expect(api.listSessions).toHaveBeenCalled();
      });

      // Session 2 is newest (11:00 vs 09:00), so it must be selected first
      await waitFor(() => {
        expect(api.getSession).toHaveBeenCalledWith('sess-2');
      });

      // Verify messages from session 2 are displayed
      expect(await screen.findByText('What is true PMF?')).toBeInTheDocument();
      expect(screen.getByText(/PMF is exponential organic pull/i)).toBeInTheDocument();

      // Verify active highlight on session 2
      const session2Option = screen.getByRole('option', { selected: true });
      expect(session2Option).toHaveTextContent('Finding PMF Faster');
    });

    it('switches active session and loads messages when clicking another session in sidebar', async () => {
      const user = userEvent.setup();
      vi.spyOn(api, 'listSessions').mockResolvedValue(mockSessions);
      vi.spyOn(api, 'getSession').mockImplementation(async (id: string) => {
        if (id === 'sess-2') return mockSession2Detail;
        if (id === 'sess-1') return mockSession1Detail;
        throw new Error('Not found');
      });

      render(<App />);

      // Initially on session 2
      expect(await screen.findByText('What is true PMF?')).toBeInTheDocument();

      // Click session 1 in sidebar
      const session1Btn = screen.getByText('Retention Mechanics');
      await user.click(session1Btn);

      // Verify getSession called for session 1
      await waitFor(() => {
        expect(api.getSession).toHaveBeenCalledWith('sess-1');
      });

      // Verify session 1 messages displayed and session 2 messages removed
      expect(await screen.findByText('How should we measure retention cohorts?')).toBeInTheDocument();
      expect(screen.getByText(/Measure retention curves until they flatten/i)).toBeInTheDocument();
      expect(screen.queryByText('What is true PMF?')).not.toBeInTheDocument();
    });

    it('clears active session and messages when clicking "New Chat"', async () => {
      const user = userEvent.setup();
      vi.spyOn(api, 'listSessions').mockResolvedValue(mockSessions);
      vi.spyOn(api, 'getSession').mockResolvedValue(mockSession2Detail);

      render(<App />);

      expect(await screen.findByText('What is true PMF?')).toBeInTheDocument();

      // Click New Chat button
      const newChatBtn = screen.getByRole('button', { name: /Start a new chat session|New Chat/i });
      await user.click(newChatBtn);

      // Messages should be cleared, Empty State should appear
      expect(screen.queryByText('What is true PMF?')).not.toBeInTheDocument();
      expect(screen.getByRole('heading', { level: 2, name: /Lenny Growth Assistant/i })).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 3. Empty State Starter Questions
  // =========================================================================
  describe('3. Empty State Starter Prompts', () => {
    it('clicking starter prompt chip creates a session and submits the question', async () => {
      const user = userEvent.setup();
      vi.spyOn(api, 'listSessions').mockResolvedValue([]);

      const createdSession: Session = {
        id: 'sess-auto-1',
        title: 'How do I know if I have PMF?',
        llm_provider: 'ollama',
        llm_model: 'qwen2.5:7b',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      const mockResponse: ChatResponse = {
        message: {
          id: 'm-auto-resp',
          session_id: 'sess-auto-1',
          role: 'assistant',
          content: 'You have PMF when customers are retaining and word of mouth accelerates [S1].',
          citations: [
            {
              n: 1,
              chunk_id: 'c-pmf',
              doc_slug: 'podcast-elena-verna',
              title: 'Growth Loops',
              guest: 'Elena Verna',
              passage: 'When retention flattens, you have foundational product-market fit.',
            },
          ],
          tool_trace: [],
          degraded: false,
          latency_ms: 2200,
          created_at: new Date().toISOString(),
        },
        citations: [],
        intent: 'QA',
        degraded: false,
        latency_ms: 2200,
      };

      vi.spyOn(api, 'createSession').mockResolvedValue(createdSession);
      vi.spyOn(api, 'sendMessage').mockResolvedValue(mockResponse);

      render(<App />);

      // Find starter prompt chip
      const starterChip = await screen.findByRole('button', {
        name: /Ask question: How do I know if I have PMF\?/i,
      });
      await user.click(starterChip);

      // Verify createSession was called
      expect(api.createSession).toHaveBeenCalledWith('How do I know if I have PMF?', expect.any(AbortSignal));

      // Verify sendMessage was called
      expect(api.sendMessage).toHaveBeenCalledWith(
        'sess-auto-1',
        'How do I know if I have PMF?',
        expect.any(AbortSignal)
      );

      // Verify user message and assistant answer appear
      const userMessageArticle = await screen.findByRole('article', { name: 'User Message' });
      expect(within(userMessageArticle).getByText('How do I know if I have PMF?')).toBeInTheDocument();
      expect(await screen.findByText(/You have PMF when customers are retaining/i)).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 4. Grounded Chat Flow & Citations
  // =========================================================================
  describe('4. Grounded Chat Flow & Citations', () => {
    it('renders user message, loading skeleton with timer, and assistant message with citation chips', async () => {
      vi.spyOn(api, 'listSessions').mockResolvedValue([]);

      let resolveSendMessage: (value: ChatResponse) => void;
      const sendPromise = new Promise<ChatResponse>((resolve) => {
        resolveSendMessage = resolve;
      });

      vi.spyOn(api, 'createSession').mockResolvedValue({
        id: 'sess-grounded',
        title: 'Founder delegation',
        llm_provider: 'ollama',
        llm_model: 'qwen2.5:7b',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
      vi.spyOn(api, 'sendMessage').mockReturnValue(sendPromise);

      render(<App />);

      // Type question in composer
      const textarea = await screen.findByTestId('composer-textarea');
      fireEvent.change(textarea, { target: { value: 'How should founders give away Legos?' } });

      const sendBtn = screen.getByTestId('composer-send-btn');
      fireEvent.click(sendBtn);

      // User message rendered immediately
      expect(screen.getByText('How should founders give away Legos?')).toBeInTheDocument();

      // Loading skeleton displayed with Cancel button
      const cancelBtn = await screen.findByTestId('skeleton-cancel-btn');
      expect(cancelBtn).toBeInTheDocument();
      expect(screen.getByTestId('loading-skeleton-container')).toBeInTheDocument();
      expect(screen.getByText(/Searching transcripts\.\.\./i)).toBeInTheDocument();

      // Resolve the network call with grounded citations
      const assistantMessage: Message = {
        id: 'msg-asst-legos',
        session_id: 'sess-grounded',
        role: 'assistant',
        content: 'Founders must give away Legos to scale effectively [S1].',
        citations: [
          {
            n: 1,
            chunk_id: 'chunk-legos',
            doc_slug: 'podcast-molly-graham',
            title: 'Give Away Your Legos',
            guest: 'Molly Graham',
            passage: 'If you want to grow, you have to let go of responsibilities you love.',
          },
        ],
        tool_trace: [],
        degraded: false,
        latency_ms: 3100,
        created_at: new Date().toISOString(),
      };

      resolveSendMessage!({
        message: assistantMessage,
        citations: assistantMessage.citations,
        intent: 'QA',
        degraded: false,
        latency_ms: 3100,
      });

      // Loading skeleton disappears
      await waitFor(() => {
        expect(screen.queryByTestId('loading-skeleton-container')).not.toBeInTheDocument();
      });

      // Assistant message renders
      expect(await screen.findByText(/Founders must give away Legos to scale effectively/i)).toBeInTheDocument();
      expect(screen.getByText(/3\.1s/i)).toBeInTheDocument();

      // Citation chip rendered
      expect(screen.getByRole('button', { name: /Sources \(1\)/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Source S1: Molly Graham — Give Away Your Legos/i })).toBeInTheDocument();
    });

    it('clicking citation chip expands sources accordion and renders passage', async () => {
      const user = userEvent.setup();
      vi.spyOn(api, 'listSessions').mockResolvedValue([mockSessions[1]]);
      vi.spyOn(api, 'getSession').mockResolvedValue(mockSession2Detail);

      render(<App />);

      // Wait for session 2 to load with citation [S1]
      expect(await screen.findByText('What is true PMF?')).toBeInTheDocument();

      // Initially, the raw passage is hidden
      expect(
        screen.queryByText(/True product-market fit feels like the market is pulling/i)
      ).not.toBeInTheDocument();

      // Click citation chip in accordion header group
      const chip = screen.getByRole('button', { name: /Source S1: Shreyas Doshi/i });
      await user.click(chip);

      // Accordion is expanded and passage is rendered
      expect(
        await screen.findByText(/True product-market fit feels like the market is pulling the product out of your hands/i)
      ).toBeInTheDocument();
      expect(screen.getByText('Shreyas Doshi')).toBeInTheDocument();
      expect(screen.getByText('podcast-shreyas-doshi')).toBeInTheDocument();
    });

    it('clicking inline [S#] tag inside markdown text expands sources accordion and reveals passage', async () => {
      const user = userEvent.setup();
      vi.spyOn(api, 'listSessions').mockResolvedValue([mockSessions[1]]);
      vi.spyOn(api, 'getSession').mockResolvedValue(mockSession2Detail);

      render(<App />);

      expect(await screen.findByText('What is true PMF?')).toBeInTheDocument();

      // Accordion initially closed
      expect(
        screen.queryByText(/True product-market fit feels like the market is pulling/i)
      ).not.toBeInTheDocument();

      // Click inline [S1] button inside the assistant message text
      const inlineTag = screen.getByRole('button', { name: /Jump to source S1/i });
      await user.click(inlineTag);

      // Accordion expands and displays the passage
      expect(
        await screen.findByText(/True product-market fit feels like the market is pulling the product out of your hands/i)
      ).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 5. Canonical Refusal Response
  // =========================================================================
  describe('5. Canonical Refusal Response', () => {
    it('canonical refusal response renders neutral RefusalCard without citation chips', async () => {
      const user = userEvent.setup();
      vi.spyOn(api, 'listSessions').mockResolvedValue([]);

      const mockRefusalResponse: ChatResponse = {
        message: {
          id: 'm-refusal',
          session_id: 'sess-refusal',
          role: 'assistant',
          content: EXACT_REFUSAL_MESSAGE,
          citations: [],
          tool_trace: [],
          degraded: false,
          latency_ms: 1200,
          created_at: new Date().toISOString(),
        },
        citations: [],
        intent: 'QA',
        degraded: false,
        latency_ms: 1200,
      };

      vi.spyOn(api, 'createSession').mockResolvedValue({
        id: 'sess-refusal',
        title: 'Off topic query',
        llm_provider: 'ollama',
        llm_model: 'qwen2.5:7b',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
      vi.spyOn(api, 'sendMessage').mockResolvedValue(mockRefusalResponse);

      render(<App />);

      const textarea = await screen.findByTestId('composer-textarea');
      await user.type(textarea, 'What is the recipe for chicken parmesan?');

      const sendBtn = screen.getByTestId('composer-send-btn');
      await user.click(sendBtn);

      // Refusal card renders canonical statement and tips
      expect(await screen.findByText(EXACT_REFUSAL_MESSAGE)).toBeInTheDocument();
      expect(screen.getByText(/Tips for better results:/i)).toBeInTheDocument();
      expect(screen.getByText(/Ask about core product management topics/i)).toBeInTheDocument();

      // Strictly NO citation chips or sources accordion
      expect(screen.queryByRole('region', { name: /Grounded transcript sources/i })).not.toBeInTheDocument();
      expect(screen.queryByText(/Sources \(/i)).not.toBeInTheDocument();
    });

    it('refusal card renders even if refusal message has minor whitespace or lacks trailing period', async () => {
      const user = userEvent.setup();
      vi.spyOn(api, 'listSessions').mockResolvedValue([]);

      const mockTolerantRefusal: ChatResponse = {
        message: {
          id: 'm-refusal-tolerant',
          session_id: 'sess-refusal-2',
          role: 'assistant',
          content: "I don't have information about that in the transcripts  ", // No period, trailing spaces
          citations: [],
          tool_trace: [],
          degraded: false,
          latency_ms: 950,
          created_at: new Date().toISOString(),
        },
        citations: [],
        intent: 'QA',
        degraded: false,
        latency_ms: 950,
      };

      vi.spyOn(api, 'createSession').mockResolvedValue({
        id: 'sess-refusal-2',
        title: 'Off topic query 2',
        llm_provider: 'ollama',
        llm_model: 'qwen2.5:7b',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
      vi.spyOn(api, 'sendMessage').mockResolvedValue(mockTolerantRefusal);

      render(<App />);

      const textarea = await screen.findByTestId('composer-textarea');
      await user.type(textarea, 'Who won the 2024 NBA Finals?');

      const sendBtn = screen.getByTestId('composer-send-btn');
      await user.click(sendBtn);

      expect(
        await screen.findByText(/I don't have information about that in the transcripts/i)
      ).toBeInTheDocument();
      expect(screen.getByText(/Tips for better results:/i)).toBeInTheDocument();
      expect(screen.queryByRole('region', { name: /Grounded transcript sources/i })).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // 6. API Error Handling & Retry
  // =========================================================================
  describe('6. API Error Handling & Retry', () => {
    it('API error renders inline ErrorBanner with Request ID and Retry button', async () => {
      const user = userEvent.setup();
      vi.spyOn(api, 'listSessions').mockResolvedValue([]);
      vi.spyOn(api, 'createSession').mockResolvedValue({
        id: 'sess-err',
        title: 'Failing Query',
        llm_provider: 'ollama',
        llm_model: 'qwen2.5:7b',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });

      const failingApiError = new ApiError(
        'llm_unavailable',
        'Ollama local LLM is unavailable',
        502,
        'req-ollama-down-456'
      );

      vi.spyOn(api, 'sendMessage')
        .mockRejectedValueOnce(failingApiError)
        .mockResolvedValueOnce({
          message: {
            id: 'm-recovered',
            session_id: 'sess-err',
            role: 'assistant',
            content: 'Recovered after retry successfully.',
            citations: [],
            tool_trace: [],
            degraded: false,
            latency_ms: 1800,
            created_at: new Date().toISOString(),
          },
          citations: [],
          intent: 'QA',
          degraded: false,
          latency_ms: 1800,
        });

      render(<App />);

      const textarea = await screen.findByTestId('composer-textarea');
      await user.type(textarea, 'What is customer retention?');

      const sendBtn = screen.getByTestId('composer-send-btn');
      await user.click(sendBtn);

      // Verify ErrorBanner renders with friendly message & Request ID
      const errorBanner = await screen.findByTestId('error-banner');
      expect(errorBanner).toBeInTheDocument();
      expect(screen.getByTestId('error-message')).toHaveTextContent(
        'Ollama local LLM is unavailable. Please verify Ollama is running with qwen2.5:7b.'
      );
      expect(screen.getByTestId('error-request-id')).toHaveTextContent('Request ID: req-ollama-down-456');

      // Retry button present
      const retryBtn = screen.getByTestId('error-retry-btn');
      expect(retryBtn).toBeInTheDocument();

      // Click Retry button
      await user.click(retryBtn);

      // Second sendMessage attempt succeeds
      expect(api.sendMessage).toHaveBeenCalledTimes(2);

      // Error banner is cleared, assistant response rendered
      await waitFor(() => {
        expect(screen.queryByTestId('error-banner')).not.toBeInTheDocument();
      });
      expect(await screen.findByText('Recovered after retry successfully.')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 7. Request Cancellation & AbortController
  // =========================================================================
  describe('7. Request Cancellation & AbortController', () => {
    it('clicking Cancel during in-flight request aborts cleanly via AbortController', async () => {
      vi.spyOn(api, 'listSessions').mockResolvedValue([]);
      vi.spyOn(api, 'createSession').mockResolvedValue({
        id: 'sess-cancel',
        title: 'Cancelling request',
        llm_provider: 'ollama',
        llm_model: 'qwen2.5:7b',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });

      let capturedSignal: AbortSignal | undefined;
      const abortHandler = vi.fn();

      vi.spyOn(api, 'sendMessage').mockImplementation(async (_id, _msg, signal) => {
        capturedSignal = signal;
        if (signal) {
          signal.addEventListener('abort', abortHandler);
        }
        return new Promise((_resolve, reject) => {
          signal?.addEventListener('abort', () => {
            const err = new DOMException('The user aborted a request.', 'AbortError');
            reject(err);
          });
        });
      });

      render(<App />);

      const textarea = await screen.findByTestId('composer-textarea');
      fireEvent.change(textarea, { target: { value: 'Why does PMF take months?' } });

      const sendBtn = screen.getByTestId('composer-send-btn');
      fireEvent.click(sendBtn);

      // Loading skeleton appears with active Cancel button
      const cancelBtn = await screen.findByTestId('skeleton-cancel-btn');
      expect(cancelBtn).toBeInTheDocument();
      expect(capturedSignal).toBeDefined();
      expect(capturedSignal?.aborted).toBe(false);

      // User message rendered optimistically
      expect(screen.getByText('Why does PMF take months?')).toBeInTheDocument();

      // Click Cancel
      fireEvent.click(cancelBtn);

      // Abort signal should be aborted
      expect(capturedSignal?.aborted).toBe(true);
      expect(abortHandler).toHaveBeenCalled();

      // Skeleton disappears
      await waitFor(() => {
        expect(screen.queryByTestId('loading-skeleton-container')).not.toBeInTheDocument();
      });

      // Optimistic message should be rolled back cleanly
      expect(screen.queryByText('Why does PMF take months?')).not.toBeInTheDocument();

      // NO error banner displayed for intentional cancellation
      expect(screen.queryByTestId('error-banner')).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // 8. Session Deletion & Confirmation Modal
  // =========================================================================
  describe('8. Session Deletion & Confirmation Modal', () => {
    it('deleting a session via confirmation dialog removes it from sidebar and switches active session', async () => {
      const user = userEvent.setup();
      vi.spyOn(api, 'listSessions').mockResolvedValue(mockSessions);
      vi.spyOn(api, 'getSession').mockImplementation(async (id: string) => {
        if (id === 'sess-2') return mockSession2Detail;
        if (id === 'sess-1') return mockSession1Detail;
        throw new Error('Not found');
      });
      vi.spyOn(api, 'deleteSession').mockResolvedValue(undefined);

      render(<App />);

      // Wait for sessions to load
      expect(await screen.findByText('What is true PMF?')).toBeInTheDocument();

      // Find delete button for "Finding PMF Faster" (active session sess-2)
      const deleteBtn = screen.getByRole('button', { name: /Delete chat: Finding PMF Faster/i });
      await user.click(deleteBtn);

      // Confirmation dialog should appear
      const dialog = await screen.findByRole('dialog', { name: /Delete Conversation\?/i });
      expect(dialog).toBeInTheDocument();
      expect(dialog).toHaveTextContent(/Are you sure you want to delete “Finding PMF Faster”\?/i);

      // Click Cancel in modal first
      const cancelBtn = within(dialog).getByRole('button', { name: /^Cancel$/i });
      await user.click(cancelBtn);

      // Modal closed, session still present
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(screen.getByText('Finding PMF Faster')).toBeInTheDocument();
      expect(api.deleteSession).not.toHaveBeenCalled();

      // Click delete button again
      await user.click(deleteBtn);

      // Confirm deletion in modal
      const confirmDialog = await screen.findByRole('dialog', { name: /Delete Conversation\?/i });
      const confirmDeleteBtn = within(confirmDialog).getByRole('button', { name: /^Delete$/i });
      await user.click(confirmDeleteBtn);

      // Verify deleteSession was called with sess-2
      await waitFor(() => {
        expect(api.deleteSession).toHaveBeenCalledWith('sess-2');
      });

      // Session 2 removed from sidebar, switched to session 1
      await waitFor(() => {
        expect(screen.queryByText('Finding PMF Faster')).not.toBeInTheDocument();
      });
      expect(screen.getByText('Retention Mechanics')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 9. Responsive Navigation Drawer
  // =========================================================================
  describe('9. Responsive Navigation Drawer', () => {
    it('toggles mobile sidebar drawer when hamburger toggle button is clicked', async () => {
      const user = userEvent.setup();
      vi.spyOn(api, 'listSessions').mockResolvedValue(mockSessions);

      render(<App />);

      const toggleBtn = screen.getByRole('button', { name: /Open sidebar navigation/i });
      expect(toggleBtn).toBeInTheDocument();
      expect(toggleBtn).toHaveAttribute('aria-expanded', 'false');

      // Click toggle button
      await user.click(toggleBtn);

      // Toggle button aria attributes update to open state
      expect(screen.getByRole('button', { name: /Close sidebar navigation/i })).toHaveAttribute(
        'aria-expanded',
        'true'
      );

      // Drawer backdrop is rendered
      const backdrop = document.querySelector('.drawer-backdrop');
      expect(backdrop).toBeInTheDocument();

      // Click backdrop to close
      if (backdrop) {
        await user.click(backdrop as HTMLElement);
      }

      // Sidebar closes
      expect(screen.getByRole('button', { name: /Open sidebar navigation/i })).toHaveAttribute(
        'aria-expanded',
        'false'
      );
    });
  });
});
