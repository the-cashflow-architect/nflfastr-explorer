/**
 * The HTTP layer. One fetch wrapper, one error shape, no per-page duplication.
 *
 * Errors are surfaced, never swallowed into an empty state. "No results" and
 * "the server is unreachable" look identical in a table if the failure path
 * returns an empty array, and on a reference site that difference is the whole
 * question of whether the number you are looking at is real.
 */

const BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  // Declared rather than written as constructor parameter properties: the
  // project compiles with `erasableSyntaxOnly`, which rules those out.
  readonly status: number
  readonly detail?: unknown

  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }

  /** A season whose play data is still materialising, not a failure. */
  get isSeasonLoading(): boolean {
    return this.status === 503
  }

  get isNotFound(): boolean {
    return this.status === 404
  }
}

export function apiUrl(path: string, params?: Record<string, unknown>): string {
  const url = `${BASE}${path}`
  if (!params) return url
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) {
      if (value.length) search.set(key, value.join(','))
    } else {
      search.set(key, String(value))
    }
  }
  const query = search.toString()
  return query ? `${url}?${query}` : url
}

export async function api<T>(
  path: string,
  params?: Record<string, unknown>,
  init?: RequestInit,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(apiUrl(path, params), {
      headers: { Accept: 'application/json' },
      ...init,
    })
  } catch (cause) {
    throw new ApiError(0, 'Could not reach the server.', cause)
  }

  if (!response.ok) {
    let detail: unknown
    let message = `Request failed (${response.status})`
    try {
      const body = await response.json()
      detail = body
      if (typeof body?.detail === 'string') message = body.detail
    } catch {
      /* A non-JSON error body is still an error; the status carries the meaning. */
    }
    throw new ApiError(response.status, message, detail)
  }

  return (await response.json()) as T
}
