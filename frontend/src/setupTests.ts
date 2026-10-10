import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// Automatically unmount React component trees and clear mock states after each test
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// Polyfill window & element scroll methods missing in JSDOM (needed for auto-scroll in chat)
window.scrollTo = vi.fn();
Element.prototype.scrollIntoView = vi.fn();

// Mock ResizeObserver (needed for auto-expanding textarea in Composer)
globalThis.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Mock matchMedia (needed for responsive layout checks and prefers-reduced-motion)
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(), // Deprecated form
    removeListener: vi.fn(), // Deprecated form
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});
