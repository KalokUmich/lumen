/**
 * Top-level error boundary — catches React render errors so a broken surface
 * shows an error panel instead of going silently blank.
 */

import React from "react";

type Props = { children: React.ReactNode; surface?: string };
type State = { error: Error | null };

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("ErrorBoundary caught", error, info);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-full flex-col items-center justify-center p-6 text-center">
          <div className="rounded-lg border border-danger/40 bg-danger/5 p-6 max-w-lg">
            <div className="text-lg font-semibold text-danger">Something went wrong</div>
            {this.props.surface && (
              <div className="mt-1 text-xs uppercase tracking-wider text-fg-subtle">
                surface: {this.props.surface}
              </div>
            )}
            <pre className="mt-3 max-h-48 overflow-auto rounded bg-bg-subtle p-3 text-left font-mono text-xs text-fg-muted">
              {this.state.error.message}
              {this.state.error.stack && "\n\n" + this.state.error.stack.split("\n").slice(0, 8).join("\n")}
            </pre>
            <button onClick={this.reset} className="btn-primary mt-4">
              Try again
            </button>
            <div className="mt-3 text-xs text-fg-subtle">
              Open DevTools console for full stack trace.
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
