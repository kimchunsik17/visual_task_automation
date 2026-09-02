import React from 'react';

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            minHeight: '100dvh',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px',
            padding: '24px',
            textAlign: 'center',
            background: '#f8fafc',
            color: '#0f172a',
          }}
        >
          <h2 style={{ margin: 0 }}>문제가 발생했어요</h2>
          <p style={{ margin: 0, color: '#475569' }}>
            화면을 그리는 중 오류가 났습니다. 새로고침하면 대부분 해결됩니다.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            style={{
              padding: '8px 20px',
              borderRadius: '8px',
              border: 'none',
              background: '#2563eb',
              color: 'white',
              fontSize: '15px',
              cursor: 'pointer',
            }}
          >
            새로고침
          </button>
          {/* 스택·컴포넌트 트리는 개발 중에만 노출한다 */}
          {import.meta.env.DEV && (
            <details
              style={{
                whiteSpace: 'pre-wrap',
                textAlign: 'left',
                maxWidth: '800px',
                maxHeight: '40dvh',
                overflow: 'auto',
                background: '#fee2e2',
                padding: '12px',
                borderRadius: '8px',
              }}
            >
              <summary>오류 상세 (DEV)</summary>
              {this.state.error && this.state.error.toString()}
              <br />
              {this.state.errorInfo && this.state.errorInfo.componentStack}
            </details>
          )}
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
