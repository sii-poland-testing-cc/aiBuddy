"use client";

import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen items-center justify-center bg-buddy-base text-buddy-text font-sans">
          <div className="flex flex-col items-center gap-4 max-w-sm text-center px-6">
            <span className="text-5xl leading-none">⚠️</span>
            <p className="text-sm text-buddy-text-muted leading-relaxed">
              Wystąpił nieoczekiwany błąd. Odśwież stronę, aby kontynuować.
            </p>
            <button
              onClick={() => window.location.reload()}
              className="px-5 py-2 bg-gradient-to-r from-buddy-gold to-buddy-gold-light text-buddy-surface text-sm font-semibold rounded-lg hover:opacity-90 transition-opacity"
            >
              Odśwież
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
