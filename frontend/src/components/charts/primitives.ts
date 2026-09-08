/**
 * Chart colours come from the same CSS custom properties as everything else, so
 * a chart inverts with the theme without a single line of chart-specific theme
 * code. Recharts wants concrete strings, hence the read at render time.
 */
export function chartColors() {
  const styles = getComputedStyle(document.documentElement)
  const read = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback
  return {
    ink: read('--c-text', '#1a1918'),
    ink2: read('--c-text-secondary', '#5c5b59'),
    ink3: read('--c-text-tertiary', '#8a8987'),
    line: read('--c-line', 'rgba(0,0,0,0.1)'),
    accent: read('--c-accent', '#c94a26'),
    positive: read('--c-positive', '#2f6b4a'),
    negative: read('--c-negative', '#a8453b'),
    track: read('--c-track', 'rgba(0,0,0,0.08)'),
    raised: read('--c-raised', '#ffffff'),
  }
}

/** Reduce a series to at most `target` points, keeping the first and last. */
export function downsample<T>(points: T[], target: number): T[] {
  if (points.length <= target) return points
  const step = (points.length - 1) / (target - 1)
  const out: T[] = []
  for (let i = 0; i < target; i += 1) out.push(points[Math.round(i * step)])
  return out
}
