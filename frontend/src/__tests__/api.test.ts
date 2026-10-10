import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  getHealth,
  getConfig,
  listSessions,
  createSession,
  getSession,
  deleteSession,
  sendMessage,
  getArtifact,
  ApiError,
  EXACT_REFUSAL_MESSAGE,
} from '../api';

function createMockResponse(
  body: any,
  status: number = 200,
  headers: Record<string, string> = {}
): Response {
  const headerMap = new Headers({
    'content-type': 'application/json',
    ...headers,
  });

  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 204 ? 'No Content' : status === 200 ? 'OK' : 'Error',
    headers: headerMap,
    json: async () => (typeof body === 'string' ? JSON.parse(body) : body),
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  } as unknown as Response;
}

describe('Typed API Client (frontend/src/api.ts)', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  describe('Success Responses (200 / 201 / 204)', () => {
    it('getHealth returns 200 with database and ollama diagnostics', async () => {
      const mockHealth = {
        status: 'ok',
        database: { connected: true, vector_count: 850 },
        ollama: {
          reachable: true,
          llm_model_present: true,
          embedding_model_present: true,
          llm_model: 'qwen2.5:7b',
          embedding_model: 'nomic-embed-text',
        },
      };

      globalThis.fetch = vi.fn().mockResolvedValue(createMockResponse(mockHealth, 200));

      const res = await getHealth();
      expect(res).toEqual(mockHealth);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/health',
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('getHealth returns degraded data when server responds with 503', async () => {
      const mockHealth503 = {
        status: 'degraded',
        database: { connected: false, vector_count: 0 },
        ollama: {
          reachable: true,
          llm_model_present: true,
          embedding_model_present: true,
          llm_model: 'qwen2.5:7b',
          embedding_model: 'nomic-embed-text',
        },
      };

      globalThis.fetch = vi.fn().mockResolvedValue(createMockResponse(mockHealth503, 503));

      const res = await getHealth();
      expect(res).toEqual(mockHealth503);
    });

    it('getConfig returns active provider and model metadata', async () => {
      const mockConfig = {
        provider: 'ollama',
        model: 'qwen2.5:7b',
        embedding_model: 'nomic-embed-text',
        embedding_dim: 768,
      };

      globalThis.fetch = vi.fn().mockResolvedValue(createMockResponse(mockConfig, 200));

      const res = await getConfig();
      expect(res).toEqual(mockConfig);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/config',
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('listSessions returns array of session objects', async () => {
      const mockSessions = [
        {
          id: 'sess-1',
          title: 'First Chat',
          llm_provider: 'ollama',
          llm_model: 'qwen2.5:7b',
          created_at: '2026-10-10T10:00:00Z',
          updated_at: '2026-10-10T10:00:00Z',
        },
      ];

      globalThis.fetch = vi.fn().mockResolvedValue(createMockResponse(mockSessions, 200));

      const res = await listSessions();
      expect(res).toEqual(mockSessions);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/sessions',
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('createSession sends title and receives 201 Created', async () => {
      const mockCreated = {
        id: 'sess-2',
        title: 'New Discussion',
        llm_provider: 'ollama',
        llm_model: 'qwen2.5:7b',
        created_at: '2026-10-10T10:05:00Z',
        updated_at: '2026-10-10T10:05:00Z',
      };

      globalThis.fetch = vi.fn().mockResolvedValue(createMockResponse(mockCreated, 201));

      const res = await createSession('New Discussion');
      expect(res).toEqual(mockCreated);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/sessions',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ title: 'New Discussion' }),
        })
      );
    });

    it('createSession without title sends empty object', async () => {
      const mockCreated = {
        id: 'sess-3',
        title: null,
        llm_provider: 'ollama',
        llm_model: 'qwen2.5:7b',
        created_at: '2026-10-10T10:06:00Z',
        updated_at: '2026-10-10T10:06:00Z',
      };

      globalThis.fetch = vi.fn().mockResolvedValue(createMockResponse(mockCreated, 201));

      const res = await createSession();
      expect(res).toEqual(mockCreated);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/sessions',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({}),
        })
      );
    });

    it('getSession returns session details with messages array', async () => {
      const mockDetail = {
        id: 'sess-1',
        title: 'Session With Messages',
        llm_provider: 'ollama',
        llm_model: 'qwen2.5:7b',
        created_at: '2026-10-10T10:00:00Z',
        updated_at: '2026-10-10T10:00:00Z',
        messages: [
          {
            id: 'msg-1',
            session_id: 'sess-1',
            role: 'user',
            content: 'Hello',
            citations: [],
            tool_trace: [],
            degraded: false,
            created_at: '2026-10-10T10:01:00Z',
          },
        ],
      };

      globalThis.fetch = vi.fn().mockResolvedValue(createMockResponse(mockDetail, 200));

      const res = await getSession('sess-1');
      expect(res).toEqual(mockDetail);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/sessions/sess-1',
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('deleteSession returns undefined on 204 No Content', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue(createMockResponse(null, 204));

      const res = await deleteSession('sess-1');
      expect(res).toBeUndefined();
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/sessions/sess-1',
        expect.objectContaining({ method: 'DELETE' })
      );
    });

    it('sendMessage sends user question and returns ChatResponse', async () => {
      const mockChatResponse = {
        message: {
          id: 'msg-2',
          session_id: 'sess-1',
          role: 'assistant',
          content: 'Here is the answer [S1].',
          intent: 'QA',
          citations: [
            {
              n: 1,
              chunk_id: 'chunk-1',
              doc_slug: 'episode-1',
              title: 'Ep 1',
              guest: 'Guest A',
              passage: 'Passage text',
            },
          ],
          tool_trace: [],
          degraded: false,
          latency_ms: 1200,
          created_at: '2026-10-10T10:02:00Z',
        },
        citations: [
          {
            n: 1,
            chunk_id: 'chunk-1',
            doc_slug: 'episode-1',
            title: 'Ep 1',
            guest: 'Guest A',
            passage: 'Passage text',
          },
        ],
        intent: 'QA',
        degraded: false,
        latency_ms: 1200,
        artifact: null,
      };

      globalThis.fetch = vi.fn().mockResolvedValue(createMockResponse(mockChatResponse, 200));

      const res = await sendMessage('sess-1', 'How do I know if I have PMF?');
      expect(res).toEqual(mockChatResponse);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/sessions/sess-1/messages',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ content: 'How do I know if I have PMF?' }),
        })
      );
    });

    it('getArtifact returns artifact payload', async () => {
      const mockArtifact = {
        id: 'art-1',
        session_id: 'sess-1',
        message_id: 'msg-2',
        type: 'html',
        title: 'Artifact Doc',
        content: '<div>artifact</div>',
        created_at: '2026-10-10T10:02:00Z',
      };

      globalThis.fetch = vi.fn().mockResolvedValue(createMockResponse(mockArtifact, 200));

      const res = await getArtifact('art-1');
      expect(res).toEqual(mockArtifact);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/artifacts/art-1',
        expect.objectContaining({ method: 'GET' })
      );
    });
  });

  describe('Error Scenarios & ApiError Parsing', () => {
    it('throws ApiError with 404 and session_not_found code', async () => {
      const errorPayload = {
        error: {
          code: 'session_not_found',
          message: 'Session sess-999 not found',
        },
      };

      globalThis.fetch = vi.fn().mockResolvedValue(
        createMockResponse(errorPayload, 404, { 'X-Request-ID': 'req-not-found' })
      );

      await expect(getSession('sess-999')).rejects.toThrow(ApiError);

      try {
        await getSession('sess-999');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.statusCode).toBe(404);
        expect(err.code).toBe('session_not_found');
        expect(err.message).toBe('Session sess-999 not found');
        expect(err.requestId).toBe('req-not-found');
      }
    });

    it('throws ApiError with 422 and validation_error code', async () => {
      const errorPayload = {
        error: {
          code: 'validation_error',
          message: 'body.content: String should have at most 4000 characters',
        },
      };

      globalThis.fetch = vi.fn().mockResolvedValue(
        createMockResponse(errorPayload, 422, { 'X-Request-ID': 'req-val-err' })
      );

      try {
        await sendMessage('sess-1', 'a'.repeat(4001));
        expect.unreachable('Should have thrown');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.statusCode).toBe(422);
        expect(err.code).toBe('validation_error');
        expect(err.message).toContain('4000 characters');
        expect(err.requestId).toBe('req-val-err');
      }
    });

    it('throws ApiError with 502 and llm_unavailable code', async () => {
      const errorPayload = {
        error: {
          code: 'llm_unavailable',
          message: 'Ollama service unreachable at http://localhost:11434',
        },
      };

      globalThis.fetch = vi.fn().mockResolvedValue(
        createMockResponse(errorPayload, 502, { 'X-Request-ID': 'req-llm-down' })
      );

      try {
        await sendMessage('sess-1', 'Hello');
        expect.unreachable('Should have thrown');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.statusCode).toBe(502);
        expect(err.code).toBe('llm_unavailable');
        expect(err.requestId).toBe('req-llm-down');
      }
    });

    it('throws ApiError with 504 and agent_timeout code', async () => {
      const errorPayload = {
        error: {
          code: 'agent_timeout',
          message: 'Agent execution timed out after 120s',
        },
      };

      globalThis.fetch = vi.fn().mockResolvedValue(
        createMockResponse(errorPayload, 504, { 'X-Request-ID': 'req-timeout' })
      );

      try {
        await sendMessage('sess-1', 'Complex analysis');
        expect.unreachable('Should have thrown');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.statusCode).toBe(504);
        expect(err.code).toBe('agent_timeout');
        expect(err.requestId).toBe('req-timeout');
      }
    });

    it('handles non-JSON error response gracefully without crashing', async () => {
      const htmlResponse = {
        ok: false,
        status: 502,
        statusText: 'Bad Gateway',
        headers: new Headers({ 'content-type': 'text/html' }),
        json: async () => {
          throw new Error('Unexpected token <');
        },
        text: async () => '<html><body>502 Bad Gateway</body></html>',
      } as unknown as Response;

      globalThis.fetch = vi.fn().mockResolvedValue(htmlResponse);

      try {
        await listSessions();
        expect.unreachable('Should have thrown');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.statusCode).toBe(502);
        expect(err.code).toBe('unknown_error');
        expect(err.message).toBe('Bad Gateway');
      }
    });

    it('handles null X-Request-ID when header is omitted', async () => {
      const errorPayload = {
        error: { code: 'bad_request', message: 'Invalid payload' },
      };

      globalThis.fetch = vi.fn().mockResolvedValue(createMockResponse(errorPayload, 400));

      try {
        await createSession();
        expect.unreachable('Should have thrown');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.requestId).toBeNull();
      }
    });
  });

  describe('AbortSignal & Cancellation', () => {
    it('forwards AbortSignal and propagates native AbortError upon cancellation', async () => {
      const controller = new AbortController();

      globalThis.fetch = vi.fn().mockImplementation((_url, options) => {
        if (options?.signal?.aborted) {
          return Promise.reject(new DOMException('The user aborted a request.', 'AbortError'));
        }
        return new Promise((_resolve, reject) => {
          options?.signal?.addEventListener('abort', () => {
            reject(new DOMException('The user aborted a request.', 'AbortError'));
          });
        });
      });

      const promise = sendMessage('sess-1', 'Inflight message', controller.signal);
      controller.abort();

      await expect(promise).rejects.toThrow('The user aborted a request.');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/sessions/sess-1/messages',
        expect.objectContaining({ signal: controller.signal })
      );
    });
  });

  describe('Constants & Contracts', () => {
    it('exports the canonical refusal message string', () => {
      expect(EXACT_REFUSAL_MESSAGE).toBe(
        "I don't have information about that in the transcripts."
      );
    });
  });
});
