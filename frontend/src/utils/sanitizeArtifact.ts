/**
 * Safe HTML artifact sanitization and wrapping pipeline.
 * Follows docs/security.md Section 2 EXACTLY:
 * 1. Size check against ARTIFACT_MAX_BYTES (200,000 bytes)
 * 2. DOMPurify with FORBID_TAGS [script, iframe, object, embed, form, link, meta, base]
 *    Forbidden all on* attributes and javascript: URLs.
 *    Remote images (http/https) are stripped to prevent tracking pixels.
 * 3. Wrapped in a document with the CSP meta tag from security.md:
 *    default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; base-uri 'none'; form-action 'none'
 */

import DOMPurify from 'dompurify';

export const ARTIFACT_MAX_BYTES = 200_000;

export const CSP_META_TAG =
  '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; font-src data:; base-uri \'none\'; form-action \'none\';" />';

export function isArtifactOversized(content: string): boolean {
  if (!content) return false;
  // Compute approximate byte size in utf-8
  if (typeof TextEncoder !== 'undefined') {
    return new TextEncoder().encode(content).length > ARTIFACT_MAX_BYTES;
  }
  return content.length > ARTIFACT_MAX_BYTES;
}

export function sanitizeHtml(rawHtml: string): string {
  if (!rawHtml) return '';

  // Setup DOMPurify sanitize options
  const sanitized = DOMPurify.sanitize(rawHtml, {
    FORBID_TAGS: [
      'script',
      'iframe',
      'object',
      'embed',
      'form',
      'link',
      'meta',
      'base',
    ],
    FORBID_ATTR: [
      'onerror',
      'onload',
      'onclick',
      'onmouseover',
      'onfocus',
      'onblur',
      'onmouseenter',
      'onmouseleave',
      'onkeydown',
      'onkeyup',
      'onkeypress',
      'onsubmit',
      'onchange',
      'onreset',
      'onselect',
      'onabort',
      'ondblclick',
      'ondrag',
      'ondrop',
    ],
    ALLOW_DATA_ATTR: false,
    RETURN_TRUSTED_TYPE: false,
  });

  // Strip remote image elements or http/https srcs (blocks tracking pixels)
  const withoutRemoteImages = (sanitized as string).replace(
    /<img[^>]*src=["']https?:\/\/[^"']*["'][^>]*>/gi,
    ''
  );

  // Strip javascript: URLs if any remain
  const inert = withoutRemoteImages.replace(
    /href=["']\s*javascript:[^"']*["']/gi,
    'href="#"'
  );

  return inert;
}

export function wrapHtmlDocument(title: string, sanitizedHtml: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  ${CSP_META_TAG}
  <title>${title || 'Generated Artifact'}</title>
</head>
<body>
${sanitizedHtml}
</body>
</html>`;
}

export function prepareHtmlArtifact(title: string, rawHtml: string): {
  isOversized: boolean;
  wrappedHtml: string;
} {
  const isOversized = isArtifactOversized(rawHtml);
  if (isOversized) {
    return {
      isOversized: true,
      wrappedHtml: wrapHtmlDocument(
        title,
        `<p style="color:red;font-family:sans-serif;padding:1rem;">Artifact size exceeds ${ARTIFACT_MAX_BYTES.toLocaleString()} bytes limit. Rendering blocked.</p>`
      ),
    };
  }

  const sanitized = sanitizeHtml(rawHtml);
  return {
    isOversized: false,
    wrappedHtml: wrapHtmlDocument(title, sanitized),
  };
}
