import http from 'http';
import { createServer } from 'vite';

async function runProxyVerification() {
  console.log('====================================================');
  console.log('PART 1: EMPIRICAL VITE PROXY VERIFICATION (MOCK TARGET)');
  console.log('====================================================');

  const receivedRequests = [];
  const mockServer = http.createServer((req, res) => {
    let raw = '';
    req.on('data', chunk => { raw += chunk; });
    req.on('end', () => {
      let parsed = null;
      if (raw) {
        try { parsed = JSON.parse(raw); } catch { parsed = raw; }
      }
      receivedRequests.push({
        method: req.method,
        url: req.url,
        headers: req.headers,
        body: parsed,
      });
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        ok: true,
        receivedUrl: req.url,
        receivedMethod: req.method,
        receivedBody: parsed,
      }));
    });
  });

  await new Promise(r => mockServer.listen(0, '127.0.0.1', r));
  const mockPort = mockServer.address().port;
  console.log(`[SETUP] Mock backend listening on 127.0.0.1:${mockPort}`);

  // Create Vite dev server with proxy pointed at mockPort
  const viteServer = await createServer({
    configFile: false,
    root: '.',
    server: {
      host: '127.0.0.1',
      port: 34567,
      strictPort: true,
      proxy: {
        '/api': {
          target: `http://127.0.0.1:${mockPort}`,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
        '/health': {
          target: `http://127.0.0.1:${mockPort}`,
          changeOrigin: true,
        },
        '/config': {
          target: `http://127.0.0.1:${mockPort}`,
          changeOrigin: true,
        },
        '/sessions': {
          target: `http://127.0.0.1:${mockPort}`,
          changeOrigin: true,
        },
        '/artifacts': {
          target: `http://127.0.0.1:${mockPort}`,
          changeOrigin: true,
        },
        '/client-events': {
          target: `http://127.0.0.1:${mockPort}`,
          changeOrigin: true,
        },
      },
    },
  });

  await viteServer.listen();
  const vitePort = viteServer.httpServer.address().port;
  console.log(`[SETUP] Vite dev server listening on 127.0.0.1:${vitePort}`);

  const testCases = [
    { name: 'GET /api/health -> rewrite to /health', method: 'GET', path: '/api/health', expectedUrl: '/health' },
    { name: 'GET /api/config -> rewrite to /config', method: 'GET', path: '/api/config', expectedUrl: '/config' },
    { name: 'GET /api/sessions -> rewrite to /sessions', method: 'GET', path: '/api/sessions', expectedUrl: '/sessions' },
    { name: 'GET /api/sessions/sess-123/messages -> rewrite', method: 'GET', path: '/api/sessions/sess-123/messages', expectedUrl: '/sessions/sess-123/messages' },
    { name: 'GET /api/artifacts/art-555 -> rewrite', method: 'GET', path: '/api/artifacts/art-555', expectedUrl: '/artifacts/art-555' },
    { name: 'GET /api/client-events -> rewrite', method: 'GET', path: '/api/client-events', expectedUrl: '/client-events' },
    { name: 'Query param preservation on /api rewrite', method: 'GET', path: '/api/sessions?status=active&limit=10', expectedUrl: '/sessions?status=active&limit=10' },
    { name: 'Direct GET /health -> forward to /health', method: 'GET', path: '/health', expectedUrl: '/health' },
    { name: 'Direct GET /config -> forward to /config', method: 'GET', path: '/config', expectedUrl: '/config' },
    { name: 'Direct GET /sessions -> forward to /sessions', method: 'GET', path: '/sessions', expectedUrl: '/sessions' },
    { name: 'Direct GET /sessions/sess-456/messages', method: 'GET', path: '/sessions/sess-456/messages', expectedUrl: '/sessions/sess-456/messages' },
    { name: 'Direct GET /artifacts/art-888', method: 'GET', path: '/artifacts/art-888', expectedUrl: '/artifacts/art-888' },
    { name: 'Direct GET /client-events', method: 'GET', path: '/client-events', expectedUrl: '/client-events' },
    {
      name: 'POST /api/sessions body forwarding',
      method: 'POST',
      path: '/api/sessions',
      body: JSON.stringify({ title: 'Adversarial Session' }),
      expectedUrl: '/sessions',
      verifyBody: true,
    },
    {
      name: 'Custom header forwarding (X-Request-ID)',
      method: 'GET',
      path: '/api/health',
      headers: { 'X-Request-ID': 'req-adv-mock-test-123' },
      expectedUrl: '/health',
      verifyHeader: 'x-request-id',
      expectedHeaderVal: 'req-adv-mock-test-123',
    },
  ];

  let passedMock = 0;
  for (const tc of testCases) {
    const res = await fetch(`http://127.0.0.1:${vitePort}${tc.path}`, {
      method: tc.method,
      headers: tc.headers || { 'Content-Type': 'application/json' },
      body: tc.body,
    });

    const rawText = await res.text();
    let data = null;
    try { data = JSON.parse(rawText); } catch {}
    console.log(`[FETCH RESULT] ${tc.path} -> HTTP ${res.status}: ${rawText.slice(0, 100)}`);

    if (res.status !== 200) {
      throw new Error(`FAIL: ${tc.name} returned status ${res.status}`);
    }
    if (data.receivedUrl !== tc.expectedUrl) {
      throw new Error(`FAIL: ${tc.name} expected URL ${tc.expectedUrl}, received ${data.receivedUrl}`);
    }

    if (tc.verifyBody && (!data.receivedBody || data.receivedBody.title !== 'Adversarial Session')) {
      throw new Error(`FAIL: ${tc.name} body was not forwarded correctly`);
    }

    if (tc.verifyHeader) {
      const lastReq = receivedRequests[receivedRequests.length - 1];
      if (lastReq.headers[tc.verifyHeader] !== tc.expectedHeaderVal) {
        throw new Error(`FAIL: ${tc.name} header ${tc.verifyHeader} was not forwarded`);
      }
    }

    console.log(`  ✓ ${tc.name} -> Target received: ${data.receivedUrl} [Method: ${data.receivedMethod}]`);
    passedMock++;
  }

  await viteServer.close();
  mockServer.close();
  console.log(`\nMock Proxy Result: ${passedMock}/${testCases.length} tests passed.\n`);

  console.log('====================================================');
  console.log('PART 2: LIVE BACKEND PROXY VERIFICATION (LOCAL PORT 8000)');
  console.log('====================================================');

  // Test with actual vite.config.ts pointing to localhost:8000
  const liveVite = await createServer({
    configFile: './vite.config.ts',
    root: '.',
    server: {
      port: 3009,
    },
  });

  await liveVite.listen();
  const livePort = liveVite.httpServer.address().port;
  console.log(`[SETUP] Live Vite dev server running on 127.0.0.1:${livePort}`);

  const liveEndpoints = [
    { ep: '/health', validate: d => (d.status === 'ok' || d.status === 'degraded') && d.database?.connected === true },
    { ep: '/api/health', validate: d => (d.status === 'ok' || d.status === 'degraded') && d.database?.connected === true },
    { ep: '/config', validate: d => typeof d.provider === 'string' && typeof d.model === 'string' },
    { ep: '/api/config', validate: d => typeof d.provider === 'string' && typeof d.model === 'string' },
    { ep: '/sessions', validate: d => Array.isArray(d) },
    { ep: '/api/sessions', validate: d => Array.isArray(d) },
  ];

  let passedLive = 0;
  for (const item of liveEndpoints) {
    const res = await fetch(`http://127.0.0.1:${livePort}${item.ep}`);
    if (res.status !== 200) {
      throw new Error(`Live proxy fail for ${item.ep}: status ${res.status}`);
    }
    const json = await res.json();
    if (!item.validate(json)) {
      throw new Error(`Live proxy fail for ${item.ep}: validation failed on payload: ${JSON.stringify(json)}`);
    }
    console.log(`  ✓ Live proxy verified: ${item.ep} -> HTTP 200 JSON valid`);
    passedLive++;
  }

  await liveVite.close();
  console.log(`\nLive Backend Proxy Result: ${passedLive}/${liveEndpoints.length} tests passed.\n`);

  console.log('====================================================');
  console.log('ALL VITE PROXY ADVERSARIAL CHECKS PASSED EMPIRICALLY');
  console.log('====================================================');
}

runProxyVerification().catch(err => {
  console.error('FATAL VERIFICATION FAILURE:', err);
  process.exit(1);
});
