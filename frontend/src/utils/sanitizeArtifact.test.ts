import { describe, it, expect } from 'vitest';
import {
  escapeHtml,
  wrapHtmlDocument,
  prepareHtmlArtifact,
  ARTIFACT_MAX_BYTES,
  CSP_META_TAG,
} from './sanitizeArtifact';

describe('Artifact Title XSS Sanitization & HTML Wrapping (Requirement R3)', () => {
  describe('escapeHtml utility', () => {
    it('escapes all sensitive HTML characters: &, <, >, ", \'', () => {
      expect(escapeHtml('Tom & Jerry')).toBe('Tom &amp; Jerry');
      expect(escapeHtml('<script>')).toBe('&lt;script&gt;');
      expect(escapeHtml('"quoted"')).toBe('&quot;quoted&quot;');
      expect(escapeHtml("'single'")).toBe('&#39;single&#39;');
      expect(escapeHtml('<a href="x" test=\'y\'>&</a>')).toBe(
        '&lt;a href=&quot;x&quot; test=&#39;y&#39;&gt;&amp;&lt;/a&gt;'
      );
    });

    it('handles empty, null, or undefined strings gracefully', () => {
      expect(escapeHtml('')).toBe('');
      expect(escapeHtml(null as unknown as string)).toBe('');
      expect(escapeHtml(undefined as unknown as string)).toBe('');
    });

    it('leaves safe alphanumeric and benign punctuation unchanged', () => {
      const safe = 'Key Growth Insights: Executive Summary - Chapter 1 (2026)';
      expect(escapeHtml(safe)).toBe(safe);
    });
  });

  describe('wrapHtmlDocument with injection payloads', () => {
    it('neutralizes hostile title breakout payload: </title><script>alert(1)</script>', () => {
      const hostileTitle = '</title><script>alert(1)</script>';
      const safeBody = '<p>Clean content</p>';

      const wrapped = wrapHtmlDocument(hostileTitle, safeBody);

      // Verify breakout tag is never present verbatim
      expect(wrapped).not.toContain('</title><script>alert(1)</script>');
      expect(wrapped).not.toContain('<script>alert(1)</script>');
      expect(wrapped).not.toContain('<script>');

      // Verify safe escaped representation inside <title>
      expect(wrapped).toContain('&lt;/title&gt;&lt;script&gt;alert(1)&lt;/script&gt;');
      expect(wrapped).toMatch(
        /<title>&lt;\/title&gt;&lt;script&gt;alert\(1\)&lt;\/script&gt;<\/title>/
      );
    });

    it('neutralizes tag attributes and event injection in title: "><img onerror=alert(1)>', () => {
      const hostileTitle = '"><img src=x onerror=alert(1)>';
      const wrapped = wrapHtmlDocument(hostileTitle, '<p>Body</p>');

      expect(wrapped).not.toContain('"><img');
      expect(wrapped).not.toContain('<img');
      expect(wrapped).toContain('&quot;&gt;&lt;img src=x onerror=alert(1)&gt;');
    });

    it('falls back to "Generated Artifact" if title is empty or falsy', () => {
      const wrapped = wrapHtmlDocument('', '<p>Body</p>');
      expect(wrapped).toContain('<title>Generated Artifact</title>');
    });

    it('preserves CSP meta tag in document head', () => {
      const wrapped = wrapHtmlDocument('Sample Title', '<p>Body</p>');
      expect(wrapped).toContain(CSP_META_TAG);
      expect(wrapped).toContain("default-src 'none'");
    });
  });

  describe('prepareHtmlArtifact end-to-end', () => {
    it('escapes hostile title in prepareHtmlArtifact output', () => {
      const hostileTitle = '</title><script>alert(1)</script>';
      const rawHtml = '<h1>Heading</h1><p>Body</p>';

      const result = prepareHtmlArtifact(hostileTitle, rawHtml);

      expect(result.isOversized).toBe(false);
      expect(result.wrappedHtml).not.toContain('</title><script>alert(1)</script>');
      expect(result.wrappedHtml).not.toContain('<script>');
      expect(result.wrappedHtml).toContain(
        '&lt;/title&gt;&lt;script&gt;alert(1)&lt;/script&gt;'
      );
    });

    it('escapes title even when artifact is oversized', () => {
      const hostileTitle = '</title><script>alert(1)</script>';
      const oversizedHtml = 'A'.repeat(ARTIFACT_MAX_BYTES + 10);

      const result = prepareHtmlArtifact(hostileTitle, oversizedHtml);

      expect(result.isOversized).toBe(true);
      expect(result.wrappedHtml).not.toContain('</title><script>alert(1)</script>');
      expect(result.wrappedHtml).not.toContain('<script>');
      expect(result.wrappedHtml).toContain(
        '&lt;/title&gt;&lt;script&gt;alert(1)&lt;/script&gt;'
      );
    });
  });
});
