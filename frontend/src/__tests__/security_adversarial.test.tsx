import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MessageItem } from '../components/MessageItem';
import { ArtifactPanel } from '../components/ArtifactPanel';
import { Message } from '../api';

describe('Adversarial Security Verification — Milestone 2', () => {
  describe('Requirement 1: ArtifactPanel iframe sandbox', () => {
    it('enforces empty sandbox attribute and strictly forbids allow-scripts and allow-same-origin', () => {
      const hostileHtml = `
        <!DOCTYPE html>
        <html>
          <head>
            <script>window.parent.evilExploit = true;</script>
          </head>
          <body>
            <h1>Exploit Attempt</h1>
            <script>document.cookie = "stolen=true";</script>
            <iframe src="https://evil.example.com"></iframe>
          </body>
        </html>
      `;

      const { container } = render(
        <ArtifactPanel
          isOpen={true}
          artifact={{
            id: 'art-exploit-1',
            title: 'Hostile Artifact',
            type: 'html',
            content: hostileHtml,
          }}
          onClose={() => {}}
        />
      );

      const iframe = container.querySelector('iframe');
      expect(iframe).toBeInTheDocument();
      expect(iframe).toHaveAttribute('sandbox', '');

      const sandboxVal = iframe?.getAttribute('sandbox') || '';
      expect(sandboxVal).not.toContain('allow-scripts');
      expect(sandboxVal).not.toContain('allow-same-origin');
      expect(sandboxVal).not.toContain('allow-forms');
      expect(sandboxVal).not.toContain('allow-popups');
      expect(sandboxVal).not.toContain('allow-top-navigation');
      expect(sandboxVal).not.toContain('allow-modals');
      expect(sandboxVal.trim()).toBe('');

      // Mandatory notice check
      expect(
        screen.getByText('Sandboxed preview: scripts and external requests are blocked.')
      ).toBeInTheDocument();
    });

    it('routes raw content with HTML brackets to sandboxed iframe even if type is unspecified', () => {
      const untypedArtifact = {
        title: 'Untyped HTML Artifact',
        content: '<div class="alert">Warning: test</div>',
      };

      const { container } = render(
        <ArtifactPanel
          isOpen={true}
          artifact={untypedArtifact}
          onClose={() => {}}
        />
      );

      const iframe = container.querySelector('iframe');
      expect(iframe).toBeInTheDocument();
      expect(iframe).toHaveAttribute('sandbox', '');
      expect(iframe?.getAttribute('sandbox')).toBe('');
    });

    it('renders non-HTML markdown artifact safely without un-sandboxed execution', () => {
      const markdownArtifact = {
        title: 'Plain Markdown Artifact',
        type: 'markdown',
        content: '# Safe Markdown\nNo raw HTML tags here.',
      };

      const { container } = render(
        <ArtifactPanel
          isOpen={true}
          artifact={markdownArtifact}
          onClose={() => {}}
        />
      );

      const iframe = container.querySelector('iframe');
      expect(iframe).toBeNull();
      expect(container.querySelector('pre')).toHaveTextContent('# Safe Markdown');
    });
  });

  describe('Requirement 2: Safe Markdown rendering (XSS Prevention)', () => {
    const createAssistantMessage = (content: string): Message => ({
      id: `msg-${Date.now()}-${Math.random()}`,
      session_id: 'sess-sec-test',
      role: 'assistant',
      content,
      citations: [],
      tool_trace: [],
      degraded: false,
      created_at: new Date().toISOString(),
    });

    it('does NOT render executable <script> tags from assistant markdown', () => {
      const maliciousScript = 'Here is an answer:\n\n<script>window.pwned = true;</script>\n\nEnd of answer.';
      const { container } = render(<MessageItem message={createAssistantMessage(maliciousScript)} />);

      expect(container.querySelector('script')).toBeNull();
      expect((window as any).pwned).toBeUndefined();
    });

    it('does NOT render executable <iframe> tags from assistant markdown', () => {
      const maliciousIframe = 'Look at this frame:\n\n<iframe src="https://attacker.com/steal"></iframe>\n\nDone.';
      const { container } = render(<MessageItem message={createAssistantMessage(maliciousIframe)} />);

      expect(container.querySelector('iframe')).toBeNull();
    });

    it('does NOT render <img> with onerror or other event handlers as HTML', () => {
      const maliciousImg = 'Image test:\n\n<img src="bogus.png" onerror="window.imgHacked = true;" />\n\nDone.';
      const { container } = render(<MessageItem message={createAssistantMessage(maliciousImg)} />);

      const img = container.querySelector('img');
      expect(img).toBeNull();
      expect((window as any).imgHacked).toBeUndefined();
    });

    it('does NOT render other active HTML elements like <svg>, <object>, <embed>, <form>', () => {
      const maliciousTags = `
        <svg onload="window.svgHacked = true;"></svg>
        <object data="data:text/html,<script>alert(1)</script>"></object>
        <embed src="test.swf"></embed>
        <form action="https://attacker.com"><button type="submit">Phish</button></form>
      `;
      const { container } = render(<MessageItem message={createAssistantMessage(maliciousTags)} />);

      expect(container.querySelector('svg')).toBeNull();
      expect(container.querySelector('object')).toBeNull();
      expect(container.querySelector('embed')).toBeNull();
      expect(container.querySelector('form')).toBeNull();
    });
  });

  describe('Requirement 3: Outbound links in Markdown', () => {
    const createAssistantMessage = (content: string): Message => ({
      id: `msg-${Date.now()}-${Math.random()}`,
      session_id: 'sess-link-test',
      role: 'assistant',
      content,
      citations: [],
      tool_trace: [],
      degraded: false,
      created_at: new Date().toISOString(),
    });

    it('ensures all standard markdown links have target="_blank" and rel="noopener noreferrer"', () => {
      const markdownWithLinks = `
Check out [Lenny Podcast](https://lennyspodcast.com) and [Substack](https://lennysnewsletter.com).
Also read [Docs](https://docs.example.com/guide "Official Guide").
      `;

      const { container } = render(<MessageItem message={createAssistantMessage(markdownWithLinks)} />);

      const links = container.querySelectorAll('a');
      expect(links.length).toBe(3);

      links.forEach((link) => {
        expect(link).toHaveAttribute('target', '_blank');
        expect(link).toHaveAttribute('rel', 'noopener noreferrer');
        expect(link.getAttribute('href')).toMatch(/^https:\/\//);
      });
    });

    it('sanitizes javascript: links to href="#" with target="_blank" and rel="noopener noreferrer"', () => {
      const maliciousLinks = `
[Exploit 1](javascript:alert('xss1'))
[Exploit 2](JAVASCRIPT:alert('xss2'))
[Exploit 3](   javascript:alert('xss3'))
[Exploit 4](javascript:void(0))
      `;

      const { container } = render(<MessageItem message={createAssistantMessage(maliciousLinks)} />);

      const links = container.querySelectorAll('a');
      expect(links.length).toBe(4);

      links.forEach((link) => {
        expect(link).toHaveAttribute('target', '_blank');
        expect(link).toHaveAttribute('rel', 'noopener noreferrer');
        expect(link.getAttribute('href')).toBe('#');
      });
    });

    it('renders inline citation links [S1] as buttons, not outbound <a> links', () => {
      const textWithCitations = 'This statement is from [S1] and also [S2].';
      const { container } = render(<MessageItem message={createAssistantMessage(textWithCitations)} />);

      // Citations should be rendered as button.citation-chip, not <a> with target="_blank"
      const citationButtons = container.querySelectorAll('button.citation-chip');
      expect(citationButtons.length).toBe(2);

      const links = container.querySelectorAll('a');
      expect(links.length).toBe(0);
    });
  });
});
