import type { AppState, StateResponse } from '@/types'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}
export async function api<T = Record<string, unknown>>(
  path: string,
  data?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const timeout = AbortSignal.timeout(45_000)
  const response = await fetch(path, {
    method: data === undefined ? 'GET' : 'POST',
    credentials: 'same-origin',
    headers: data === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: data === undefined ? undefined : JSON.stringify(data),
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  })
  const result = await response.json()
  if (!response.ok)
    throw new ApiError(result.error || 'Request failed. Try again.', response.status)
  return result as T
}
export function mergeState(previous: AppState | null, result: StateResponse): AppState {
  const updates = new Map(result.project_updates.map((p) => [p.id, p]))
  return {
    ...result,
    projects:
      result.projects ??
      (updates.size
        ? (previous?.projects || []).map((p) => updates.get(p.id) || p)
        : previous?.projects || []),
  }
}
export const errorText = (error: unknown) =>
  error instanceof Error
    ? error.name === 'TimeoutError'
      ? 'The server is taking too long. Your saved data is retained.'
      : error.message
    : 'Could not complete the request.'
export function bytes(value: number | null) {
  if (!value) return '0 B'
  const index = Math.max(0, Math.min(Math.floor(Math.log(value) / Math.log(1024)), 4))
  return `${(value / 1024 ** index).toFixed(index > 1 ? 1 : 0)} ${['B', 'KB', 'MB', 'GB', 'TB'][index]}`
}
export const qualityLabel = (value: number) => (value ? `${value}p` : 'Highest available')
export const qualityOptions = (
  values = [2160, 1080, 720, 480, 380],
  inherited = 'Highest available',
) => [
  { value: '0', label: inherited },
  ...[...new Set(values.filter((q) => q > 0))]
    .sort((a, b) => b - a)
    .map((q) => ({ value: String(q), label: `Prefer ${q}p` })),
]
