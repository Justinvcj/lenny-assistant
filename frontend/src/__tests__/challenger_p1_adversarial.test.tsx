import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import { App } from '../App';
import { Composer } from '../components/Composer';


// Storage Mock for JSDOM
const storageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = String(value);
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: storageMock,
  writable: true,
});
Object.defineProperty(globalThis, 'localStorage', {
  value: storageMock,
  writable: true,
});

// Read index.css dynamically in Node test environment
let cssContent = '';
try {
  const req = eval('require');
  const fs = req('fs');
  const path = req('path');
  cssContent = fs.readFileSync(path.resolve((globalThis as any).process.cwd(), 'src/index.css'), 'utf-8');
} catch {
  cssContent = '';
}

describe('Challenger Phase 1 Layout & Shortcut Adversarial Test Suite', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  // =========================================================================
  // 1. CSS In-Flow Flex & Layout Invariants
  // =========================================================================
  describe('1. CSS Layout Invariants & Cut-Off Prevention Tokens', () => {
    it('defines --sidebar-collapsed-width: 60px in :root', () => {
      expect(cssContent).toMatch(/--sidebar-collapsed-width:\s*60px;/);
    });

    it('enforces height: 100dvh with 100vh fallback and min-height: 0 on .app-shell', () => {
      expect(cssContent).toMatch(/\.app-shell\s*\{[^}]*height:\s*100vh;[^}]*height:\s*100dvh;[^}]*min-height:\s*0;/);
    });

    it('enforces flex: 1 1 0% and min-height: 0 on .app-body', () => {
      expect(cssContent).toMatch(/\.app-body\s*\{[^}]*flex:\s*1\s+1\s+0%;[^}]*min-height:\s*0;/);
    });

    it('enforces min-height: 0 and min-width: 0 on .chat-viewport', () => {
      expect(cssContent).toMatch(/\.chat-viewport\s*\{[^}]*min-width:\s*0;[^}]*min-height:\s*0;/);
    });

    it('enforces overflow-y: auto and min-height: 0 on .chat-scroll-area', () => {
      expect(cssContent).toMatch(/\.chat-scroll-area\s*\{[^}]*min-height:\s*0;[^}]*overflow-y:\s*auto;/);
    });

    it('strictly guarantees .composer-dock is in-flow flex-shrink: 0 and NOT position: absolute', () => {
      expect(cssContent).toMatch(/\.composer-dock\s*\{[^}]*flex-shrink:\s*0;[^}]*position:\s*relative;/);
      expect(cssContent).not.toMatch(/\.composer-dock\s*\{[^}]*position:\s*absolute/);
      expect(cssContent).toContain('max(0.75rem, env(safe-area-inset-bottom))');
    });

    it('contains collapsed sidebar width rules in desktop media query', () => {
      expect(cssContent).toMatch(/\.app-sidebar\.collapsed\s*\{[^}]*width:\s*var\(--sidebar-collapsed-width\);/);
    });
  });

  // =========================================================================
  // 2. Keyboard Shortcut Ctrl+B / Cmd+B & LocalStorage Contract
  // =========================================================================
  describe('2. Keyboard Shortcut Ctrl+B & LocalStorage State Machine', () => {
    it('initializes sidebar state from localStorage if lenny_sidebar_collapsed is true', () => {
      window.localStorage.setItem('lenny_sidebar_collapsed', 'true');
      const { container } = render(<App />);
      const sidebar = container.querySelector('.app-sidebar');
      expect(sidebar).toBeTruthy();
      expect(sidebar?.classList.contains('collapsed')).toBe(true);
    });

    it('initializes sidebar state as expanded if lenny_sidebar_collapsed is absent or false', () => {
      const { container } = render(<App />);
      const sidebar = container.querySelector('.app-sidebar');
      expect(sidebar).toBeTruthy();
      expect(sidebar?.classList.contains('collapsed')).toBe(false);
    });

    it('toggles sidebar collapse state and updates localStorage on Ctrl+B', () => {
      const { container } = render(<App />);
      const sidebar = container.querySelector('.app-sidebar');
      expect(sidebar?.classList.contains('collapsed')).toBe(false);
      expect(window.localStorage.getItem('lenny_sidebar_collapsed')).toBeNull();

      // Trigger Ctrl+B
      act(() => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', ctrlKey: true }));
      });

      expect(sidebar?.classList.contains('collapsed')).toBe(true);
      expect(window.localStorage.getItem('lenny_sidebar_collapsed')).toBe('true');

      // Trigger Ctrl+B again to un-collapse
      act(() => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', ctrlKey: true }));
      });

      expect(sidebar?.classList.contains('collapsed')).toBe(false);
      expect(window.localStorage.getItem('lenny_sidebar_collapsed')).toBe('false');
    });

    it('toggles sidebar collapse state and updates localStorage on Cmd+B (metaKey)', () => {
      const { container } = render(<App />);
      const sidebar = container.querySelector('.app-sidebar');
      expect(sidebar?.classList.contains('collapsed')).toBe(false);

      act(() => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'B', metaKey: true }));
      });

      expect(sidebar?.classList.contains('collapsed')).toBe(true);
      expect(window.localStorage.getItem('lenny_sidebar_collapsed')).toBe('true');
    });

    it('prevents default browser bookmark behavior on Ctrl+B / Cmd+B', () => {
      render(<App />);
      const event = new KeyboardEvent('keydown', { key: 'b', ctrlKey: true, cancelable: true });
      const preventDefaultSpy = vi.spyOn(event, 'preventDefault');

      window.dispatchEvent(event);
      expect(preventDefaultSpy).toHaveBeenCalled();
    });
  });

  // =========================================================================
  // 3. Multiline Composer Auto-Growth & Boundaries
  // =========================================================================
  describe('3. Multiline Composer Auto-Growth & Clamp', () => {
    it('renders composer textarea with rows=1 and allows text entry', () => {
      render(<Composer />);
      const textarea = screen.getByTestId('composer-textarea') as HTMLTextAreaElement;
      expect(textarea).toBeTruthy();
      expect(textarea.getAttribute('rows')).toBe('1');

      fireEvent.change(textarea, { target: { value: 'Multiline\nText\nEntry' } });
      expect(textarea.value).toBe('Multiline\nText\nEntry');
    });

    it('displays character counter and updates class near limit', () => {
      render(<Composer maxLength={4000} />);
      const textarea = screen.getByTestId('composer-textarea') as HTMLTextAreaElement;
      const counter = screen.getByTestId('char-counter');

      expect(counter.textContent).toContain('0 / 4,000');

      // 3600 characters triggers warning
      const longText = 'a'.repeat(3600);
      fireEvent.change(textarea, { target: { value: longText } });
      expect(counter.className).toContain('warning');

      // 4000 characters triggers limit
      const limitText = 'a'.repeat(4000);
      fireEvent.change(textarea, { target: { value: limitText } });
      expect(counter.className).toContain('limit');
    });
  });
});
