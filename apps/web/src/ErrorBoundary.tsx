import { Component, type ErrorInfo, type ReactNode } from "react";

type ErrorBoundaryProps = {
  children: ReactNode;
};

type ErrorBoundaryState = {
  error: Error | null;
};

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // The fallback keeps the local workspace usable even when a malformed result reaches the UI.
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <main className="content" aria-labelledby="workspace-error-heading">
          <section className="panel" role="alert">
            <p className="section-kicker">작업 화면</p>
            <h1 id="workspace-error-heading">작업 화면을 복구하지 못했습니다</h1>
            <p className="error-banner">{this.state.error.message}</p>
            <button className="action-button" type="button" onClick={() => this.setState({ error: null })}>
              다시 시도
            </button>
          </section>
        </main>
      );
    }

    return this.props.children;
  }
}
