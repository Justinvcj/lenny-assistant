import { describe, it, expect } from 'vitest';
import {
  escapeHtml,
  wrapHtmlDocument,
  prepareHtmlArtifact,
  ARTIFACT_MAX_BYTES,
  CSP_META_TAG,
} from '../utils/sanitizeArtifact';

describe('Challenger M3 Empirical Stress Tests: Title XSS Sanitization (R3)', () => {
  const hostilePayloads: { name: string; payload: string }[] = [
    {
      name: 'Classic script injection',
      payload: '</title><script>alert(1)</script>',
    },
    {
      name: 'Style tag body hijacking',
      payload: '</title><style>body { display: none; background: red; }</style>',
    },
    {
      name: 'SVG onload attack vector',
      payload: '</title><svg onload=alert(1)>',
    },
    {
      name: 'SVG slash onload attack vector',
      payload: '</title><svg/onload=alert(1)>',
    },
    {
      name: 'SVG with CDATA and script block',
      payload: '</title><svg><desc><![CDATA[</desc><script>alert(1)</script>]]></svg>',
    },
    {
      name: 'Attribute breakout with double quote',
      payload: '"><script>alert(1)</script>',
    },
    {
      name: 'Attribute breakout with single quote',
      payload: '\'"><script>alert(1)</script>',
    },
    {
      name: 'Mixed case title and script tags',
      payload: '</TiTlE><ScRiPt>alert(1)</sCrIpT>',
    },
    {
      name: 'Uppercase TITLE and SCRIPT',
      payload: '</TITLE><SCRIPT>alert(1)</SCRIPT>',
    },
    {
      name: 'Iframe with javascript protocol',
      payload: '</title><iframe src="javascript:alert(1)"></iframe>',
    },
    {
      name: 'Img tag with onerror handler',
      payload: '</title><img src=x onerror=alert(1)>',
    },
    {
      name: 'Body tag with onload handler',
      payload: '</title><body onload=alert(1)>',
    },
    {
      name: 'Base tag hijacking',
      payload: '</title><base href="javascript:alert(1)//">',
    },
    {
      name: 'Unicode fullwidth tag characters',
      payload: '＜/title＞＜script＞alert(1)＜/script＞',
    },
    {
      name: 'Literal unicode escapes in raw text',
      payload: '\\u003c/title\\u003e\\u003cscript\\u003ealert(1)\\u003c/script\\u003e',
    },
    {
      name: 'HTML entities in title text',
      payload: '&lt;/title&gt;&lt;script&gt;alert(1)&lt;/script&gt;',
    },
    {
      name: 'All 5 sensitive characters together with quotes and ampersands',
      payload: 'Test & <Tag> "Quote" \'Apostrophe\' `Backtick` / Slash',
    },
    {
      name: 'Long string with payload at the end (5,000 chars)',
      payload: 'A'.repeat(5000) + '</title><script>alert(1)</script>',
    },
  ];

  describe('1. escapeHtml aggressive vector neutralization', () => {
    it.each(hostilePayloads)('neutralizes payload: $name', ({ payload }) => {
      const escaped = escapeHtml(payload);

      // Verify no raw unescaped <, >, ", ', & remain
      expect(escaped).not.toContain('<');
      expect(escaped).not.toContain('>');
      expect(escaped).not.toContain('"');
      expect(escaped).not.toContain("'");

      // Verify HTML entities are present where characters existed
      if (payload.includes('&')) expect(escaped).toContain('&amp;');
      if (payload.includes('<')) expect(escaped).toContain('&lt;');
      if (payload.includes('>')) expect(escaped).toContain('&gt;');
      if (payload.includes('"')) expect(escaped).toContain('&quot;');
      if (payload.includes("'")) expect(escaped).toContain('&#39;');
    });

    it('returns empty string on empty, null, undefined', () => {
      expect(escapeHtml('')).toBe('');
      expect(escapeHtml(null as unknown as string)).toBe('');
      expect(escapeHtml(undefined as unknown as string)).toBe('');
    });
  });

  describe('2. wrapHtmlDocument title breakout prevention', () => {
    it.each(hostilePayloads)(
      'prevents <title> breakout and script injection for: $name',
      ({ payload }) => {
        const doc = wrapHtmlDocument(payload, '<p>Safe Body</p>');

        // 1. Must never contain unescaped script tag anywhere in head or body
        expect(doc.toLowerCase()).not.toContain('<script');
        expect(doc.toLowerCase()).not.toContain('</script>');

        // 2. Must never contain unescaped svg, img, iframe, or body tag from payload
        expect(doc.toLowerCase()).not.toContain('<svg');
        expect(doc.toLowerCase()).not.toContain('<img');
        expect(doc.toLowerCase()).not.toContain('<iframe');

        // 3. Must contain exactly ONE <title> and ONE </title> tag in the entire document
        const titleOpenMatches = doc.match(/<title>/gi) || [];
        const titleCloseMatches = doc.match(/<\/title>/gi) || [];
        expect(titleOpenMatches.length).toBe(1);
        expect(titleCloseMatches.length).toBe(1);

        // 4. Verify CSP meta tag is untouched
        expect(doc).toContain(CSP_META_TAG);
      }
    );
  });

  describe('3. prepareHtmlArtifact end-to-end integration', () => {
    it.each(hostilePayloads)(
      'safely wraps standard artifact without title breakout for: $name',
      ({ payload }) => {
        const res = prepareHtmlArtifact(payload, '<div><h1>Artifact Header</h1></div>');
        expect(res.isOversized).toBe(false);

        const doc = res.wrappedHtml;
        expect(doc.toLowerCase()).not.toContain('<script');
        const titleOpenMatches = doc.match(/<title>/gi) || [];
        const titleCloseMatches = doc.match(/<\/title>/gi) || [];
        expect(titleOpenMatches.length).toBe(1);
        expect(titleCloseMatches.length).toBe(1);
      }
    );

    it('safely wraps oversized artifact with hostile title without breakout', () => {
      const hostileTitle = '</title><script>alert("oversized")</script>';
      const oversizedContent = 'x'.repeat(ARTIFACT_MAX_BYTES + 50);

      const res = prepareHtmlArtifact(hostileTitle, oversizedContent);
      expect(res.isOversized).toBe(true);

      const doc = res.wrappedHtml;
      expect(doc.toLowerCase()).not.toContain('<script');
      expect(doc).toContain('&lt;/title&gt;&lt;script&gt;');
      const titleOpenMatches = doc.match(/<title>/gi) || [];
      const titleCloseMatches = doc.match(/<\/title>/gi) || [];
      expect(titleOpenMatches.length).toBe(1);
      expect(titleCloseMatches.length).toBe(1);
    });
  });
});
