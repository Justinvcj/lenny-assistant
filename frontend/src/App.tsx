import React, { useEffect, useState } from 'react';

interface ConfigData {
  provider: string;
  model: string;
  embedding_model: string;
  embedding_dim: number;
}

interface HealthData {
  status: string;
  database: {
    connected: boolean;
    vector_count: number;
  };
  ollama: {
    reachable: boolean;
    llm_model_present: boolean;
    embedding_model_present: boolean;
    llm_model: string;
    embedding_model: string;
  };
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const App: React.FC = () => {
  const [config, setConfig] = useState<ConfigData | null>(null);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [configRes, healthRes] = await Promise.all([
        fetch(`${API_BASE}/config`),
        fetch(`${API_BASE}/health`),
      ]);

      if (configRes.ok) {
        setConfig(await configRes.json());
      }
      if (healthRes.ok || healthRes.status === 503) {
        setHealth(await healthRes.json());
      } else {
        setError(`Health error: HTTP ${healthRes.status}`);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to connect to backend API');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, []);

  const isHealthy = health?.status === 'ok';

  return (
    <div style={{ padding: '2rem', maxWidth: '800px', margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #334155', paddingBottom: '1rem' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.5rem', color: '#38bdf8' }}>Lenny Growth Assistant</h1>
          <p style={{ margin: '0.25rem 0 0', color: '#94a3b8', fontSize: '0.875rem' }}>Grounded AI assistant over Lenny's Podcast transcripts</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {/* Status Dot */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', background: '#1e293b', padding: '0.4rem 0.75rem', borderRadius: '9999px', fontSize: '0.85rem' }}>
            <span
              style={{
                display: 'inline-block',
                width: '10px',
                height: '10px',
                borderRadius: '50%',
                backgroundColor: isHealthy ? '#22c55e' : '#eab308',
                boxShadow: isHealthy ? '0 0 8px #22c55e' : '0 0 8px #eab308',
              }}
            />
            <span style={{ color: '#cbd5e1' }}>{health?.status || (loading ? 'checking...' : 'offline')}</span>
          </div>

          {/* Model Badge */}
          {config && (
            <div style={{ background: '#3b82f6', color: '#ffffff', padding: '0.4rem 0.75rem', borderRadius: '6px', fontSize: '0.85rem', fontWeight: 600 }}>
              {config.provider}: {config.model}
            </div>
          )}
        </div>
      </header>

      <main style={{ marginTop: '2rem' }}>
        {error && (
          <div style={{ padding: '1rem', background: '#450a0a', border: '1px solid #dc2626', borderRadius: '8px', color: '#fca5a5', marginBottom: '1.5rem' }}>
            <strong>Connection Notice:</strong> {error}
          </div>
        )}

        <section style={{ background: '#1e293b', borderRadius: '8px', padding: '1.5rem', border: '1px solid #334155' }}>
          <h2 style={{ marginTop: 0, fontSize: '1.15rem', color: '#f1f5f9' }}>System Health Status</h2>
          {loading && !health ? (
            <p style={{ color: '#94a3b8' }}>Loading system diagnostics...</p>
          ) : health ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
              <div style={{ background: '#0f172a', padding: '1rem', borderRadius: '6px', border: '1px solid #334155' }}>
                <h3 style={{ margin: '0 0 0.5rem', fontSize: '0.95rem', color: '#94a3b8' }}>PostgreSQL + pgvector</h3>
                <p style={{ margin: '0.25rem 0' }}>Connected: <strong>{health.database.connected ? 'Yes' : 'No'}</strong></p>
                <p style={{ margin: '0.25rem 0' }}>Indexed Chunks: <strong>{health.database.vector_count}</strong></p>
              </div>

              <div style={{ background: '#0f172a', padding: '1rem', borderRadius: '6px', border: '1px solid #334155' }}>
                <h3 style={{ margin: '0 0 0.5rem', fontSize: '0.95rem', color: '#94a3b8' }}>Ollama Local LLM</h3>
                <p style={{ margin: '0.25rem 0' }}>Reachable: <strong>{health.ollama.reachable ? 'Yes' : 'No'}</strong></p>
                <p style={{ margin: '0.25rem 0' }}>Chat Model ({health.ollama.llm_model}): <strong>{health.ollama.llm_model_present ? 'Ready' : 'Missing'}</strong></p>
                <p style={{ margin: '0.25rem 0' }}>Embed Model ({health.ollama.embedding_model}): <strong>{health.ollama.embedding_model_present ? 'Ready' : 'Missing'}</strong></p>
              </div>
            </div>
          ) : (
            <p style={{ color: '#ef4444' }}>Unable to retrieve health status.</p>
          )}
        </section>

        <section style={{ marginTop: '2rem', textAlign: 'center', color: '#64748b', fontSize: '0.85rem' }}>
          P1 Scaffold active. Chat interface and RAG agent pipeline load in upcoming phases.
        </section>
      </main>
    </div>
  );
};

export default App;
