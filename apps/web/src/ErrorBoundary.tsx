import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "./components/ui/button";

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
        <main className="mx-auto grid min-h-screen max-w-3xl place-items-center p-6" aria-labelledby="workspace-error-heading">
          <section className="grid w-full gap-4 rounded-xl border bg-card p-6 text-card-foreground shadow-sm" role="alert">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">작업 화면</p>
            <h1 id="workspace-error-heading">작업 화면을 복구하지 못했습니다</h1>
            <p className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              화면을 다시 그리지 못했습니다. 다시 시도를 눌러 주세요. 그래도 같으면 이 화면을 닫았다가 다시 열어 보세요.
            </p>
            <details className="text-xs text-muted-foreground">
              <summary>자세한 내용</summary>
              <p>{this.state.error.message}</p>
            </details>
            <Button type="button" onClick={() => this.setState({ error: null })}>
              다시 시도
            </Button>
          </section>
        </main>
      );
    }

    return this.props.children;
  }
}
