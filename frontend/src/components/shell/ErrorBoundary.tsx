import { Component, type ErrorInfo, type ReactNode } from 'react'

/**
 * Stops one broken component from blanking the whole product.
 *
 * This is not hypothetical. A single bad property read in the footer's coverage
 * line threw during render, React unmounted the tree, and every one of the
 * twenty-three routes rendered an empty dark rectangle — while the typecheck,
 * the linter and the production build all passed, because the crash was in the
 * shape of the data rather than the shape of the code.
 *
 * A reference site can survive a broken block. It cannot survive looking dead.
 */
export class ErrorBoundary extends Component<
  {
    children: ReactNode
    label?: string
    /**
     * A change here clears a caught error. The page boundary passes the path:
     * it lives in the shell, which stays mounted across navigation, so without
     * it one page that threw left "could not be displayed" on every route
     * after it — and the iOS app has no reload button to clear it.
     */
    resetKey?: string
  },
  { error: Error | null; resetKey?: string }
> {
  state: { error: Error | null; resetKey?: string } = { error: null, resetKey: this.props.resetKey }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  // A reset, not a remount: a page that did not throw keeps its state.
  static getDerivedStateFromProps(props: { resetKey?: string }, state: { resetKey?: string }) {
    return props.resetKey === state.resetKey ? null : { error: null, resetKey: props.resetKey }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Left in deliberately: in development this is the fastest route from a
    // blank panel to the component that broke.
    console.error('Render failed', this.props.label ?? '', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="rounded-md border border-line bg-raised px-3 py-2 text-[12px] text-ink-3">
          This part of the page could not be displayed. The rest of the page is unaffected.
        </div>
      )
    }
    return this.props.children
  }
}
