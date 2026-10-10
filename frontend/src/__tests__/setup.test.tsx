import React, { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect } from 'vitest';

const TestCounter: React.FC = () => {
  const [count, setCount] = useState(0);
  return (
    <div>
      <p data-testid="counter-value">Count: {count}</p>
      <button onClick={() => setCount(count + 1)}>Increment</button>
    </div>
  );
};

describe('Frontend Test Infrastructure Smoke Test', () => {
  it('runs pure assertions via Vitest', () => {
    expect(1 + 1).toBe(2);
  });

  it('renders React components into JSDOM and evaluates jest-dom matchers', () => {
    render(<div data-testid="banner">Lenny Assistant Active</div>);
    const banner = screen.getByTestId('banner');
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent('Lenny Assistant Active');
  });

  it('handles user events with @testing-library/user-event', async () => {
    const user = userEvent.setup();
    render(<TestCounter />);

    const counter = screen.getByTestId('counter-value');
    const button = screen.getByRole('button', { name: /increment/i });

    expect(counter).toHaveTextContent('Count: 0');
    await user.click(button);
    expect(counter).toHaveTextContent('Count: 1');
  });

  it('verifies JSDOM shims for scrollTo, scrollIntoView, and ResizeObserver', () => {
    expect(() => window.scrollTo(0, 0)).not.toThrow();

    const element = document.createElement('div');
    expect(() => element.scrollIntoView()).not.toThrow();

    const observer = new ResizeObserver(() => {});
    expect(observer).toBeDefined();
    expect(() => observer.observe(element)).not.toThrow();
  });
});
