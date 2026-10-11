/**
 * Typed API Client for Lenny Growth Assistant Backend.
 * Conforms to FastAPI backend routes, schemas, and error envelopes.
 */

export interface ErrorDetail {
  code: string;
  message: string;
}

export interface ApiErrorEnvelope {
  error: ErrorDetail;
}

export interface HealthDatabaseStatus {
  connected: boolean;
  vector_count: number;
  ingested?: boolean;
}

export interface HealthOllamaStatus {
  reachable: boolean;
  llm_model_present: boolean;
  embedding_model_present: boolean;
  llm_model: string;
  embedding_model: string;
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  ingested?: boolean;
  database: HealthDatabaseStatus;
  ollama: HealthOllamaStatus;
}

export interface ConfigResponse {
  provider: string;
  model: string;
  embedding_model: string;
  embedding_dim: number;
}

export interface CitationItem {
  n: number;
  chunk_id: string;
  doc_slug: string;
  title: string;
  guest?: string | null;
  passage: string;
}

export interface Message {
  id: string;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  intent?: string | null;
  citations: CitationItem[];
  tool_trace: Array<Record<string, any>>;
  degraded: boolean;
  latency_ms?: number | null;
  created_at: string;
  artifact?: Record<string, any> | null;
  artifacts?: Array<Record<string, any>> | null;
}

export interface Session {
  id: string;
  title?: string | null;
  llm_provider: string;
  llm_model: string;
  created_at: string;
  updated_at: string;
}

export interface SessionDetail extends Session {
  messages: Message[];
}

export interface ChatResponse {
  message: Message;
  citations: CitationItem[];
  intent?: string | null;
  degraded: boolean;
  latency_ms?: number | null;
  artifact?: Record<string, any> | null;
}

export interface ArtifactResponse {
  id: string;
  session_id: string;
  message_id?: string | null;
  type: 'markdown' | 'html';
  title: string;
  content: string;
  created_at: string;
}

export const EXACT_REFUSAL_MESSAGE = "I don't have information about that in the transcripts.";

export class ApiError extends Error {
  code: string;
  statusCode: number;
  requestId?: string | null;
  data?: any;

  constructor(
    code: string,
    message: string,
    statusCode: number,
    requestId?: string | null,
    data?: any
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.statusCode = statusCode;
    this.requestId = requestId;
    this.data = data;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

export const API_BASE_URL = (
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) ||
  'http://localhost:8000'
).replace(/\/+$/, '');

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  const url = `${API_BASE_URL}${cleanEndpoint}`;
  const headers = new Headers(options.headers || {});

  if (!headers.has('Content-Type') && options.body && typeof options.body === 'string') {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  const requestId = response.headers.get('X-Request-ID');

  if (response.status === 204) {
    return undefined as unknown as T;
  }

  let data: any;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  } else {
    try {
      const text = await response.text();
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }

  // Handle /health special case where HTTP 503 is returned when DB is disconnected
  if (response.status === 503 && cleanEndpoint === '/health' && data?.database) {
    return data as T;
  }

  if (!response.ok) {
    const errorCode =
      data?.error?.code || (response.status === 404 ? 'not_found' : 'unknown_error');
    const errorMessage =
      data?.error?.message || response.statusText || `Request failed with status ${response.status}`;
    throw new ApiError(errorCode, errorMessage, response.status, requestId, data);
  }

  return data as T;
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>('/health', { method: 'GET', signal });
}

export async function getConfig(signal?: AbortSignal): Promise<ConfigResponse> {
  return request<ConfigResponse>('/config', { method: 'GET', signal });
}

export async function listSessions(signal?: AbortSignal): Promise<Session[]> {
  return request<Session[]>('/sessions', { method: 'GET', signal });
}

export async function createSession(title?: string, signal?: AbortSignal): Promise<Session> {
  return request<Session>('/sessions', {
    method: 'POST',
    body: JSON.stringify(title ? { title } : {}),
    signal,
  });
}

export async function getSession(sessionId: string, signal?: AbortSignal): Promise<SessionDetail> {
  return request<SessionDetail>(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'GET',
    signal,
  });
}

export async function deleteSession(sessionId: string, signal?: AbortSignal): Promise<void> {
  return request<void>(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
    signal,
  });
}

export async function sendMessage(
  sessionId: string,
  content: string,
  signal?: AbortSignal
): Promise<ChatResponse> {
  return request<ChatResponse>(`/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
    signal,
  });
}

export async function getArtifact(artifactId: string, signal?: AbortSignal): Promise<ArtifactResponse> {
  return request<ArtifactResponse>(`/artifacts/${encodeURIComponent(artifactId)}`, {
    method: 'GET',
    signal,
  });
}

export interface ClientEventPayload {
  type: string;
  artifact_id?: string | null;
  reason: string;
}

export async function postClientEvent(event: ClientEventPayload): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/client-events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event),
    });
  } catch (err) {
    console.warn('Failed to send client event telemetry:', err);
  }
}

