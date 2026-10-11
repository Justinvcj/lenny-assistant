import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';
import { postClientEvent } from '../api';

export interface ArtifactErrorBoundaryProps {
  artifactId?: string | null;
  children: ReactNode;
}

interface ArtifactErrorBoundaryState {
  hasError: boolean;
  errorMessage: string;
}

export class ArtifactErrorBoundary extends Component<
  ArtifactErrorBoundaryProps,
  ArtifactErrorBoundaryState
> {
  constructor(props: ArtifactErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      errorMessage: '',
    };
  }

  static getDerivedStateFromError(error: Error): ArtifactErrorBoundaryState {
    return {
      hasError: true,
      errorMessage: error.message || 'Unknown render failure',
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('Artifact render error caught by boundary:', error, errorInfo);
    postClientEvent({
      type: 'artifact_render_error',
      artifact_id: this.props.artifactId,
      reason: error.message || 'Artifact render exception',
    });
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div
          className="artifact-error-fallback"
          role="alert"
          data-testid="artifact-render-error"
          style={{
            padding: '2rem 1.5rem',
            textAlign: 'center',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '0.75rem',
            color: '#ef4444',
          }}
        >
          <AlertTriangle size={36} aria-hidden="true" />
          <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>
            Unable to display artifact
          </h3>
          <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)', maxWidth: '320px' }}>
            A rendering error occurred while safely presenting this preview. The issue has been logged.
          </p>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ArtifactErrorBoundary;
