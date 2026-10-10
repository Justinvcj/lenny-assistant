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
  API_BASE_URL,
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
    statusText:
      status === 204
        ? 'No Content'
        : status === 200
        ? 'OK'
        : status === 404
        ? 'Not Found'
        : status === 422
        ? 'Unprocessable Entity'
        : status === 500
        ? 'Internal Server Error'
        : status === 502
        ? 'Bad Gateway'
        : 'Error',
    headers: headerMap,
    json: async () => {
      if (typeof body === 'string') {
        try {
          return JSON.parse(body);
        } catch {
          throw new SyntaxError('Unexpected token in JSON');
        }
      }
      return body;
    },
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  } as unknown as Response;
}

describe('Adversarial Stress Testing — Typed API Client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  describe('Challenge 1: fetch throws TypeError (Offline / DNS Failure / Network Down)', () => {
    it('bubbles up TypeError when network is completely offline (Failed to fetch)', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));

      await expect(sendMessage('sess-1', 'Are you there?')).rejects.toThrow(TypeError);

      try {
        await sendMessage('sess-1', 'Are you there?');
        expect.unreachable('Should have thrown TypeError');
      } catch (err: any) {
        expect(err).toBeInstanceOf(TypeError);
        expect(err).not.toBeInstanceOf(ApiError);
        expect(err.message).toBe('Failed to fetch');
      }
    });

    it('bubbles up TypeError during DNS resolution failure on listSessions', async () => {
      globalThis.fetch = vi
        .fn()
        .mockRejectedValue(new TypeError('getaddrinfo ENOTFOUND localhost'));

      await expect(listSessions()).rejects.toThrow(TypeError);

      try {
        await listSessions();
      } catch (err: any) {
        expect(err).toBeInstanceOf(TypeError);
        expect(err).not.toBeInstanceOf(ApiError);
        expect(err.message).toContain('ENOTFOUND');
      }
    });

    it('bubbles up TypeError during getHealth when host connection is refused', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('fetch failed: ECONNREFUSED'));

      await expect(getHealth()).rejects.toThrow(TypeError);

      try {
        await getHealth();
      } catch (err: any) {
        expect(err).toBeInstanceOf(TypeError);
        expect(err).not.toBeInstanceOf(ApiError);
      }
    });
  });

  describe('Challenge 2: Unexpected Server Payloads & ApiError Handling', () => {
    it('handles unexpected HTML error response (e.g. 502 Bad Gateway from reverse proxy)', async () => {
      const htmlResp = {
        ok: false,
        status: 502,
        statusText: 'Bad Gateway',
        headers: new Headers({
          'content-type': 'text/html',
          'X-Request-ID': 'proxy-502-req',
        }),
        json: async () => {
          throw new SyntaxError('Unexpected token < in JSON at position 0');
        },
        text: async () => '<html><body>502 Bad Gateway: upstream server down</body></html>',
      } as unknown as Response;

      globalThis.fetch = vi.fn().mockResolvedValue(htmlResp);

      try {
        await sendMessage('sess-1', 'test message');
        expect.unreachable('Should have thrown');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.statusCode).toBe(502);
        expect(err.code).toBe('unknown_error');
        expect(err.message).toBe('Bad Gateway');
        expect(err.requestId).toBe('proxy-502-req');
        expect(err.data).toBeNull();
      }
    });

    it('handles unexpected raw text response with empty statusText', async () => {
      const textResp = {
        ok: false,
        status: 500,
        statusText: '', // Empty in HTTP/2
        headers: new Headers({
          'content-type': 'text/plain',
        }),
        json: async () => {
          throw new SyntaxError('Unexpected token');
        },
        text: async () => 'Internal Server Error (Crash)',
      } as unknown as Response;

      globalThis.fetch = vi.fn().mockResolvedValue(textResp);

      try {
        await listSessions();
        expect.unreachable('Should have thrown');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.statusCode).toBe(500);
        expect(err.code).toBe('unknown_error');
        expect(err.message).toBe('Request failed with status 500');
        expect(err.requestId).toBeNull();
        expect(err.data).toBeNull();
      }
    });

    it('handles non-standard error payload where error is a string instead of object', async () => {
      const stringErrorPayload = {
        error: 'Authentication credentials were not provided',
      };

      globalThis.fetch = vi.fn().mockResolvedValue(
        createMockResponse(stringErrorPayload, 401, {
          'x-request-id': 'unauth-req',
        })
      );

      try {
        await getSession('sess-secret');
        expect.unreachable('Should have thrown');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.statusCode).toBe(401);
        expect(err.code).toBe('unknown_error');
        // Because string does not have .message property, falls back to statusText
        expect(err.message).toBe('Error');
        expect(err.requestId).toBe('unauth-req');
        expect(err.data).toEqual(stringErrorPayload);
      }
    });

    it('handles standard FastAPI HTTPException payload { detail: "string" } with 404', async () => {
      const fastApiPayload = {
        detail: 'Session not found in storage',
      };

      globalThis.fetch = vi.fn().mockResolvedValue(
        createMockResponse(fastApiPayload, 404, {
          'X-Request-ID': 'fastapi-404',
        })
      );

      try {
        await getSession('sess-missing');
        expect.unreachable('Should have thrown');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.statusCode).toBe(404);
        expect(err.code).toBe('not_found'); // Fallback handles 404
        expect(err.message).toBe('Not Found'); // statusText fallback
        expect(err.requestId).toBe('fastapi-404');
        expect(err.data).toEqual(fastApiPayload);
      }
    });

    it('handles unexpected 503 response on /health without database property', async () => {
      const unexpected503 = {
        detail: 'Service temporarily overloaded',
      };

      globalThis.fetch = vi.fn().mockResolvedValue(
        createMockResponse(unexpected503, 503, {
          'X-Request-ID': 'req-503-raw',
        })
      );

      // Should throw ApiError because data.database is missing
      try {
        await getHealth();
        expect.unreachable('Should have thrown ApiError');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.statusCode).toBe(503);
        expect(err.code).toBe('unknown_error');
        expect(err.requestId).toBe('req-503-raw');
      }
    });

    it('handles 200 OK with null/empty JSON body safely', async () => {
      const emptyJsonResponse = {
        ok: true,
        status: 200,
        statusText: 'OK',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => null,
        text: async () => 'null',
      } as unknown as Response;

      globalThis.fetch = vi.fn().mockResolvedValue(emptyJsonResponse);

      const res = await listSessions();
      expect(res).toBeNull();
    });
  });

  describe('Challenge 3: X-Request-ID Header Case Insensitivity & Missing Headers', () => {
    it('extracts X-Request-ID when header is entirely lowercase (x-request-id)', async () => {
      const errorPayload = {
        error: { code: 'server_error', message: 'Database query failed' },
      };

      globalThis.fetch = vi.fn().mockResolvedValue(
        createMockResponse(errorPayload, 500, {
          'x-request-id': 'lower-case-uuid-789',
        })
      );

      try {
        await listSessions();
        expect.unreachable('Should have thrown');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.requestId).toBe('lower-case-uuid-789');
      }
    });

    it('extracts X-Request-ID when header is mixed case (X-Request-Id)', async () => {
      const errorPayload = {
        error: { code: 'forbidden', message: 'Action disallowed' },
      };

      globalThis.fetch = vi.fn().mockResolvedValue(
        createMockResponse(errorPayload, 403, {
          'X-Request-Id': 'mixed-case-uuid-456',
        })
      );

      try {
        await deleteSession('sess-protected');
        expect.unreachable('Should have thrown');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.requestId).toBe('mixed-case-uuid-456');
      }
    });

    it('leaves requestId as null when X-Request-ID header is omitted entirely', async () => {
      const errorPayload = {
        error: { code: 'bad_request', message: 'Malformed JSON' },
      };

      // Create response with no X-Request-ID header
      globalThis.fetch = vi.fn().mockResolvedValue(createMockResponse(errorPayload, 400));

      try {
        await createSession('Title');
        expect.unreachable('Should have thrown');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.requestId).toBeNull();
      }
    });
  });

  describe('Challenge 4: Pre-aborted Signal & AbortController Lifecycle', () => {
    it('immediately rejects when passed an already-aborted AbortSignal', async () => {
      const controller = new AbortController();
      controller.abort(); // Pre-aborted before calling sendMessage

      globalThis.fetch = vi.fn().mockImplementation((_url, options) => {
        if (options?.signal?.aborted) {
          return Promise.reject(new DOMException('The user aborted a request.', 'AbortError'));
        }
        return Promise.resolve(createMockResponse({}));
      });

      const promise = sendMessage('sess-1', 'Message with pre-aborted signal', controller.signal);

      await expect(promise).rejects.toThrow('The user aborted a request.');

      try {
        await sendMessage('sess-1', 'Message with pre-aborted signal', controller.signal);
      } catch (err: any) {
        expect(err).toBeInstanceOf(DOMException);
        expect(err.name).toBe('AbortError');
        expect(err).not.toBeInstanceOf(ApiError);
      }

      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/sessions/sess-1/messages',
        expect.objectContaining({ signal: controller.signal })
      );
    });

    it('immediately rejects when passed static AbortSignal.abort()', async () => {
      const abortedSignal = AbortSignal.abort();

      globalThis.fetch = vi.fn().mockImplementation((_url, options) => {
        if (options?.signal?.aborted) {
          return Promise.reject(new DOMException('This operation was aborted', 'AbortError'));
        }
        return Promise.resolve(createMockResponse({}));
      });

      await expect(
        sendMessage('sess-1', 'Message with AbortSignal.abort()', abortedSignal)
      ).rejects.toThrow('This operation was aborted');
    });

    it('does not swallow or convert AbortError into ApiError during getHealth cancellation', async () => {
      const controller = new AbortController();

      globalThis.fetch = vi.fn().mockImplementation((_url, options) => {
        return new Promise((_resolve, reject) => {
          options?.signal?.addEventListener('abort', () => {
            reject(new DOMException('The user aborted a request.', 'AbortError'));
          });
        });
      });

      const promise = getHealth(controller.signal);
      controller.abort();

      try {
        await promise;
        expect.unreachable('Should have aborted');
      } catch (err: any) {
        expect(err.name).toBe('AbortError');
        expect(err).not.toBeInstanceOf(ApiError);
      }
    });

    it('supports AbortSignal forwarding across getConfig', async () => {
      const controller = new AbortController();

      globalThis.fetch = vi.fn().mockImplementation((_url, options) => {
        if (options?.signal?.aborted) {
          return Promise.reject(new DOMException('Aborted getConfig', 'AbortError'));
        }
        return Promise.resolve(createMockResponse({ provider: 'ollama', model: 'qwen2.5:7b' }));
      });

      controller.abort();
      await expect(getConfig(controller.signal)).rejects.toThrow('Aborted getConfig');
    });
  });

  describe('Challenge 5: URL Path Escaping & Security', () => {
    it('properly encodes session IDs containing special characters and path traversal', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue(
        createMockResponse({
          id: 'sess/../evil',
          title: 'Special',
          llm_provider: 'ollama',
          llm_model: 'qwen2.5:7b',
          created_at: '2026-10-10T10:00:00Z',
          updated_at: '2026-10-10T10:00:00Z',
          messages: [],
        })
      );

      await getSession('sess/../evil');

      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/sessions/sess%2F..%2Fevil',
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('properly encodes artifact IDs containing spaces and query characters', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue(
        createMockResponse({
          id: 'art?foo=bar#baz',
          session_id: 's1',
          type: 'markdown',
          title: 'T',
          content: 'C',
          created_at: '2026-10-10T10:00:00Z',
        })
      );

      await getArtifact('art?foo=bar#baz');

      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/artifacts/art%3Ffoo%3Dbar%23baz',
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('exposes API_BASE_URL without trailing slashes and canonical refusal constant', () => {
      expect(API_BASE_URL).not.toMatch(/\/$/);
      expect(EXACT_REFUSAL_MESSAGE).toBe(
        "I don't have information about that in the transcripts."
      );
    });
  });
});
