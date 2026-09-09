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
  { children: ReactNode; label?: string },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
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
