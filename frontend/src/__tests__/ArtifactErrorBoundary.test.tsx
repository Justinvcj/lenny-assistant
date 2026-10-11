import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ArtifactErrorBoundary } from '../components/ArtifactErrorBoundary';
import { ArtifactPanel } from '../components/ArtifactPanel';
import * as api from '../api';

describe('Artifact Observability & Error Boundary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders children when no rendering error occurs', () => {
    render(
      <ArtifactErrorBoundary artifactId="art-123">
        <div data-testid="child-content">Normal Artifact Content</div>
      </ArtifactErrorBoundary>
    );

    expect(screen.getByTestId('child-content')).toHaveTextContent('Normal Artifact Content');
  });

  it('catches render exception, displays friendly fallback, and posts client event without content', () => {
    const postSpy = vi.spyOn(api, 'postClientEvent').mockResolvedValue(undefined);
    // Suppress console.error in test runner for intentional throw
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const ThrowingComponent = () => {
      throw new Error('Simulated DOM render failure');
    };

    render(
      <ArtifactErrorBoundary artifactId="art-error-456">
        <ThrowingComponent />
      </ArtifactErrorBoundary>
    );

    expect(screen.getByTestId('artifact-render-error')).toBeInTheDocument();
    expect(screen.getByText(/Unable to display artifact/i)).toBeInTheDocument();

    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(postSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'artifact_render_error',
        artifact_id: 'art-error-456',
        reason: 'Simulated DOM render failure',
      })
    );

    consoleErrorSpy.mockRestore();
  });

  it('reports artifact_size_rejected telemetry and displays oversized fallback when artifact exceeds 200KB', () => {
    const postSpy = vi.spyOn(api, 'postClientEvent').mockResolvedValue(undefined);
    const oversizedContent = 'A'.repeat(200001);

    render(
      <ArtifactPanel
        isOpen={true}
        artifact={{
          id: 'art-huge-789',
          title: 'Oversized Artifact',
          type: 'markdown',
          content: oversizedContent,
        }}
        onClose={() => {}}
      />
    );

    expect(screen.getByTestId('artifact-oversized-fallback')).toBeInTheDocument();
    expect(screen.getByText(/Artifact Size Limit Exceeded/i)).toBeInTheDocument();

    expect(postSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'artifact_size_rejected',
        artifact_id: 'art-huge-789',
      })
    );
  });
});
