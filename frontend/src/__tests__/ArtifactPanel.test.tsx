import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { ArtifactPanel } from '../components/ArtifactPanel';

describe('ArtifactPanel Component', () => {
  it('renders sandboxed iframe with sandbox="" and mandatory security notice', () => {
    const artifact = {
      id: 'art-1',
      title: 'Growth Playbook HTML',
      type: 'html',
      html: '<h1>Growth Playbook</h1><p>Step 1: Retention</p>',
    };

    const { container } = render(
      <ArtifactPanel
        isOpen={true}
        artifact={artifact}
        onClose={vi.fn()}
      />
    );

    expect(screen.getByText('Growth Playbook HTML')).toBeInTheDocument();
    expect(
      screen.getByText('Sandboxed preview: scripts and external requests are blocked.')
    ).toBeInTheDocument();

    const iframe = container.querySelector('iframe');
    expect(iframe).toBeInTheDocument();
    expect(iframe).toHaveAttribute('sandbox', '');
    expect(iframe?.getAttribute('sandbox')).not.toContain('allow-scripts');
    expect(iframe?.getAttribute('sandbox')).not.toContain('allow-same-origin');
  });

  it('switches between Preview and Source tabs', async () => {
    const user = userEvent.setup();
    const artifact = {
      id: 'art-2',
      title: 'Essay Markdown',
      type: 'markdown',
      content: '# Ship 30 Essay\n\nWriting daily builds leverage.',
    };

    render(
      <ArtifactPanel
        isOpen={true}
        artifact={artifact}
        onClose={vi.fn()}
      />
    );

    const sourceTab = screen.getByRole('button', { name: 'Source' });
    await user.click(sourceTab);

    expect(screen.getByText(/Writing daily builds leverage./i)).toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', async () => {
    const user = userEvent.setup();
    const handleClose = vi.fn();

    render(
      <ArtifactPanel
        isOpen={true}
        artifact={null}
        onClose={handleClose}
      />
    );

    const closeBtn = screen.getByRole('button', { name: /Close artifact panel/i });
    await user.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
