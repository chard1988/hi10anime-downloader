import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useApplication } from '@/hooks/use-application'
import { toast } from '@/components/ui/toast'
import { api, ApiError } from '@/lib/api'
import type { QueueQuery, StateResponse } from '@/types'
vi.mock('@/components/ui/toast', () => ({ toast: { add: vi.fn() } }))
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: vi.fn(),
}))
const mocked = vi.mocked(api)
const query: QueueQuery = {
  page: 0,
  pageSize: 25,
  groupSize: 5,
  filter: 'all',
  search: '',
  groups: {},
}
const response = {
  projects: [],
  project_updates: [],
  job: { running: false, error: null },
  download_job: { running: false, error: null },
  library_version: 1,
} as unknown as StateResponse
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => (resolve = done))
  return { promise, resolve }
}
afterEach(() => {
  mocked.mockReset()
  vi.mocked(toast.add).mockClear()
})
describe('application request lifecycle', () => {
  it('shares in-flight polls and aborts them on unmount', async () => {
    const request = deferred<StateResponse>()
    mocked.mockReturnValue(request.promise)
    const hook = renderHook(() => useApplication(query))
    expect(mocked).toHaveBeenCalledTimes(1)
    let first: Promise<void>, second: Promise<void>
    act(() => {
      first = hook.result.current.refresh()
      second = hook.result.current.refresh()
    })
    expect(first!).toBe(second!)
    expect(mocked).toHaveBeenCalledTimes(1)
    const signal = mocked.mock.calls[0][2]!
    hook.unmount()
    expect(signal.aborted).toBe(true)
    await act(async () => request.resolve(response))
  })
  it('discards stale responses when queue filters change', async () => {
    const old = deferred<StateResponse>(),
      next = deferred<StateResponse>()
    mocked.mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise)
    const hook = renderHook(({ value }) => useApplication(value), {
      initialProps: { value: query },
    })
    hook.rerender({ value: { ...query, filter: 'failed' } })
    expect(mocked).toHaveBeenCalledTimes(2)
    await act(async () => next.resolve({ ...response, library_version: 2 }))
    await waitFor(() => expect(hook.result.current.state?.library_version).toBe(2))
    await act(async () => old.resolve({ ...response, library_version: 1 }))
    expect(hook.result.current.state?.library_version).toBe(2)
  })
  it('locks and clears protected state after authentication expires', async () => {
    mocked.mockResolvedValueOnce(response).mockRejectedValueOnce(new ApiError('Unlock first', 401))
    const hook = renderHook(() => useApplication(query))
    await waitFor(() => expect(hook.result.current.state).not.toBeNull())
    await act(async () => {
      await hook.result.current.refresh()
    })
    expect(hook.result.current.locked).toBe(true)
    expect(hook.result.current.state).toBeNull()
  })
})

describe('mutations', () => {
  it('sets pending feedback immediately and blocks duplicate actions until the request finishes', async () => {
    mocked.mockResolvedValueOnce(response)
    const hook = renderHook(() => useApplication(query))
    await waitFor(() => expect(hook.result.current.state).not.toBeNull())
    const mutation = deferred<Record<string, unknown>>()
    mocked.mockReturnValueOnce(mutation.promise).mockResolvedValueOnce(response)
    let first!: Promise<boolean>, second!: Promise<boolean>
    act(() => {
      first = hook.result.current.action('/api/scan', { ids: ['project'] })
    })
    expect(hook.result.current.pending?.path).toBe('/api/scan')
    await act(async () => {
      second = hook.result.current.action('/api/scan', { ids: ['project'] })
    })
    expect(await second).toBe(false)
    expect(mocked).toHaveBeenCalledTimes(2)
    await act(async () => {
      mutation.resolve({})
      await first
    })
    expect(hook.result.current.pending).toBeNull()
    expect(mocked).toHaveBeenCalledTimes(3)
  })
})

describe('background error notifications', () => {
  const failed = {
    ...response,
    job: { ...response.job, id: 'old-login', error: 'Login browser failed' },
  }
  it('does not announce a historical failure on initial load or browser reload', async () => {
    mocked.mockResolvedValue(failed)
    const first = renderHook(() => useApplication(query))
    await waitFor(() => expect(first.result.current.state?.job.error).toBe('Login browser failed'))
    expect(toast.add).not.toHaveBeenCalled()
    first.unmount()
    const reloaded = renderHook(() => useApplication(query))
    await waitFor(() =>
      expect(reloaded.result.current.state?.job.error).toBe('Login browser failed'),
    )
    expect(toast.add).not.toHaveBeenCalled()
  })
  it('announces each newly failed operation once, including identical retry errors', async () => {
    const running = {
      ...failed,
      job: { ...failed.job, id: 'new-login', running: true, error: null },
    }
    const failure = {
      ...running,
      job: { ...running.job, running: false, error: 'Login browser failed' },
    }
    mocked.mockResolvedValueOnce(failed)
    const hook = renderHook(() => useApplication(query))
    await waitFor(() => expect(hook.result.current.state).not.toBeNull())
    for (const state of [running, failure, failure]) {
      mocked.mockResolvedValueOnce(state)
      await act(async () => {
        await hook.result.current.refresh()
      })
    }
    expect(toast.add).toHaveBeenCalledTimes(1)
    mocked.mockResolvedValueOnce({ ...failure, job: { ...failure.job, id: 'another-login' } })
    await act(async () => {
      await hook.result.current.refresh()
    })
    expect(toast.add).toHaveBeenCalledTimes(2)
  })
  it('does not replay the library failure when a download fails or recovers', async () => {
    mocked.mockResolvedValueOnce(failed)
    const hook = renderHook(() => useApplication(query))
    await waitFor(() => expect(hook.result.current.state).not.toBeNull())
    mocked.mockResolvedValueOnce({
      ...failed,
      download_job: { ...failed.download_job, id: 'batch', error: 'Download failed' },
    })
    await act(async () => {
      await hook.result.current.refresh()
    })
    expect(toast.add).toHaveBeenCalledExactlyOnceWith({
      title: 'Operation needs attention',
      description: 'Download failed',
      type: 'error',
    })
    mocked.mockResolvedValueOnce(failed)
    await act(async () => {
      await hook.result.current.refresh()
    })
    expect(toast.add).toHaveBeenCalledTimes(1)
  })
})
