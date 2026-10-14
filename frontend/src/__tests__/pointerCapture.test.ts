import { describe, it, expect, vi } from 'vitest';

describe('JSDOM Pointer Capture Polyfill Stress Test (setupTests.ts)', () => {
  it('1. verifies all three methods exist as functions on Element.prototype', () => {
    expect(Element.prototype.hasPointerCapture).toBeDefined();
    expect(typeof Element.prototype.hasPointerCapture).toBe('function');

    expect(Element.prototype.setPointerCapture).toBeDefined();
    expect(typeof Element.prototype.setPointerCapture).toBe('function');

    expect(Element.prototype.releasePointerCapture).toBeDefined();
    expect(typeof Element.prototype.releasePointerCapture).toBe('function');
  });

  it('2. verifies methods are inherited by various HTMLElement instances', () => {
    const tagNames = [
      'div',
      'button',
      'input',
      'textarea',
      'a',
      'select',
      'nav',
      'main',
      'aside',
      'section',
      'span',
    ];

    tagNames.forEach((tag) => {
      const el = document.createElement(tag);
      expect(typeof el.hasPointerCapture).toBe('function');
      expect(typeof el.setPointerCapture).toBe('function');
      expect(typeof el.releasePointerCapture).toBe('function');
    });
  });

  it('3. verifies methods are inherited by SVGElement instances', () => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');

    [svg, path, rect].forEach((el) => {
      expect(typeof el.hasPointerCapture).toBe('function');
      expect(typeof el.setPointerCapture).toBe('function');
      expect(typeof el.releasePointerCapture).toBe('function');
    });
  });

  describe('4. hasPointerCapture return values and boundary inputs', () => {
    const el = document.createElement('div');

    it('returns boolean false for valid pointer IDs', () => {
      expect(el.hasPointerCapture(1)).toBe(false);
      expect(el.hasPointerCapture(0)).toBe(false);
      expect(el.hasPointerCapture(42)).toBe(false);
      expect(el.hasPointerCapture(1000000)).toBe(false);
    });

    it('returns boolean false without crashing for edge case and hostile inputs', () => {
      const hostileInputs = [
        -1,
        -99999,
        0,
        1.5,
        NaN,
        Infinity,
        -Infinity,
        null as any,
        undefined as any,
        '' as any,
        'pointer-1' as any,
        {} as any,
        [] as any,
        (() => {}) as any,
        Symbol('pointer') as any,
      ];

      hostileInputs.forEach((input) => {
        expect(() => el.hasPointerCapture(input)).not.toThrow();
        expect(el.hasPointerCapture(input)).toBe(false);
      });

      // Also call with no arguments
      expect(() => (el.hasPointerCapture as any)()).not.toThrow();
      expect((el.hasPointerCapture as any)()).toBe(false);
    });
  });

  describe('5. setPointerCapture execution and boundary inputs', () => {
    const el = document.createElement('button');

    it('returns undefined and does not throw for standard pointer IDs', () => {
      expect(el.setPointerCapture(1)).toBeUndefined();
      expect(el.setPointerCapture(0)).toBeUndefined();
      expect(el.setPointerCapture(999)).toBeUndefined();
    });

    it('does not throw for edge case and hostile inputs', () => {
      const hostileInputs = [
        -1,
        -99999,
        0,
        1.5,
        NaN,
        Infinity,
        -Infinity,
        null as any,
        undefined as any,
        '' as any,
        'pointer-id' as any,
        {} as any,
        [] as any,
      ];

      hostileInputs.forEach((input) => {
        expect(() => el.setPointerCapture(input)).not.toThrow();
        expect(el.setPointerCapture(input)).toBeUndefined();
      });

      // Call with no arguments
      expect(() => (el.setPointerCapture as any)()).not.toThrow();
      expect((el.setPointerCapture as any)()).toBeUndefined();
    });

    it('executes without error on detached and DOM-attached elements', () => {
      const detached = document.createElement('div');
      expect(() => detached.setPointerCapture(1)).not.toThrow();

      const attached = document.createElement('div');
      document.body.appendChild(attached);
      expect(() => attached.setPointerCapture(1)).not.toThrow();
      document.body.removeChild(attached);
    });
  });

  describe('6. releasePointerCapture execution and boundary inputs', () => {
    const el = document.createElement('button');

    it('returns undefined and does not throw when releasing valid pointer IDs', () => {
      expect(el.releasePointerCapture(1)).toBeUndefined();
      expect(el.releasePointerCapture(0)).toBeUndefined();
      expect(el.releasePointerCapture(999)).toBeUndefined();
    });

    it('does not throw when releasing capture that was never acquired', () => {
      const freshEl = document.createElement('div');
      expect(() => freshEl.releasePointerCapture(100)).not.toThrow();
      expect(freshEl.releasePointerCapture(100)).toBeUndefined();
    });

    it('does not throw for edge case and hostile inputs', () => {
      const hostileInputs = [
        -1,
        -99999,
        0,
        1.5,
        NaN,
        Infinity,
        -Infinity,
        null as any,
        undefined as any,
        '' as any,
        'pointer-id' as any,
        {} as any,
        [] as any,
      ];

      hostileInputs.forEach((input) => {
        expect(() => el.releasePointerCapture(input)).not.toThrow();
        expect(el.releasePointerCapture(input)).toBeUndefined();
      });

      // Call with no arguments
      expect(() => (el.releasePointerCapture as any)()).not.toThrow();
      expect((el.releasePointerCapture as any)()).toBeUndefined();
    });
  });

  describe('7. Vi.spyOn and Mockability Verification', () => {
    it('allows Vitest spyOn on instance methods', () => {
      const btn = document.createElement('button');
      const setSpy = vi.spyOn(btn, 'setPointerCapture');
      const releaseSpy = vi.spyOn(btn, 'releasePointerCapture');
      const hasSpy = vi.spyOn(btn, 'hasPointerCapture');

      btn.setPointerCapture(5);
      expect(setSpy).toHaveBeenCalledWith(5);

      btn.hasPointerCapture(5);
      expect(hasSpy).toHaveBeenCalledWith(5);

      btn.releasePointerCapture(5);
      expect(releaseSpy).toHaveBeenCalledWith(5);

      setSpy.mockRestore();
      releaseSpy.mockRestore();
      hasSpy.mockRestore();
    });

    it('allows Vitest spyOn on Element.prototype', () => {
      const setProtoSpy = vi.spyOn(Element.prototype, 'setPointerCapture');
      const releaseProtoSpy = vi.spyOn(Element.prototype, 'releasePointerCapture');

      const div = document.createElement('div');
      div.setPointerCapture(12);
      div.releasePointerCapture(12);

      expect(setProtoSpy).toHaveBeenCalledWith(12);
      expect(releaseProtoSpy).toHaveBeenCalledWith(12);

      setProtoSpy.mockRestore();
      releaseProtoSpy.mockRestore();
    });
  });

  describe('8. Radix UI Pointer Event Lifecycle Simulation', () => {
    it('successfully handles a full pointerdown -> pointermove -> pointerup cycle', () => {
      const container = document.createElement('div');
      document.body.appendChild(container);

      let capturedPointerId: number | null = null;
      let releasedPointerId: number | null = null;

      container.onpointerdown = (e) => {
        container.setPointerCapture(e.pointerId);
        capturedPointerId = e.pointerId;
      };

      container.onpointermove = (e) => {
        if (container.hasPointerCapture(e.pointerId)) {
          // pointer is captured
        }
      };

      container.onpointerup = (e) => {
        if (capturedPointerId !== null) {
          container.releasePointerCapture(e.pointerId);
          releasedPointerId = e.pointerId;
        }
      };

      // Dispatch simulated PointerEvent
      const pointerId = 7;
      container.dispatchEvent(new Event('pointerdown'));
      container.onpointerdown({ pointerId } as any);
      expect(capturedPointerId).toBe(7);

      container.onpointermove({ pointerId } as any);

      container.onpointerup({ pointerId } as any);
      expect(releasedPointerId).toBe(7);

      document.body.removeChild(container);
    });
  });

  describe('9. Stress testing high volume rapid invocations (10,000 iterations)', () => {
    it('executes 10,000 set/has/release cycles without error or slowdown', () => {
      const el = document.createElement('div');
      const startTime = performance.now();

      for (let i = 0; i < 10000; i++) {
        el.setPointerCapture(i);
        const has = el.hasPointerCapture(i);
        expect(has).toBe(false);
        el.releasePointerCapture(i);
      }

      const elapsed = performance.now() - startTime;
      expect(elapsed).toBeLessThan(1000); // Should run in well under 1 second
    });
  });
});
