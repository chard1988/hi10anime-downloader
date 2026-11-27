import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, errorText, mergeState } from '@/lib/api'
import { toast } from '@/components/ui/toast'
import type { ActionData, AppState, QueueQuery, StateResponse } from '@/types'

export function useApplication(query: QueueQuery) {
  const [state, setState] = useState<AppState | null>(null)
  const [locked, setLocked] = useState(false)
  const [connecting, setConnecting] = useState(true)
  const [connectionError, setConnectionError] = useState('')
  const [pending, setPending] = useState<{ path: string; ids: string[] } | null>(null)
  const stateRef = useRef(state),
    queryRef = useRef(query),
    controller = useRef<AbortController | null>(null)
  const inFlight = useRef<{
    key: string
    promise: Promise<void>
    controller: AbortController
  } | null>(null)
  const actionLock = useRef(false),
    mounted = useRef(true)
  stateRef.current = state
  queryRef.current = query
  const lock = useCallback(() => {
    controller.current?.abort()
    stateRef.current = null
    setState(null)
    setLocked(true)
  }, [])
  const refresh = useCallback(
    (force = false) => {
      const key = JSON.stringify(queryRef.current)
      if (!force && inFlight.current?.key === key && !inFlight.current.controller.signal.aborted)
        return inFlight.current.promise
      controller.current?.abort()
      const request = new AbortController()
      controller.current = request
      const q = queryRef.current
      const params = new URLSearchParams({
        grouped: '1',
        download_page: String(q.page),
        download_filter: q.filter,
        download_page_size: String(q.pageSize),
        group_page_size: String(q.groupSize),
        download_search: q.search,
        group_pages: JSON.stringify(q.groups),
      })
      if (stateRef.current) params.set('library_version', String(stateRef.current.library_version))
      const promise = (async () => {
        try {
          const result = await api<StateResponse>('/api/state?' + params, undefined, request.signal)
          if (!mounted.current || request.signal.aborted) return
          const previous = stateRef.current
          const next = mergeState(previous, result)
          stateRef.current = next
          setState(next)
          setLocked(false)
          setConnectionError('')
          // Initial snapshots include historical failures. Only announce a new
          // failure observed after loading, independently for each worker.
          if (previous) {
            for (const worker of ['job', 'download_job'] as const) {
              const job = next[worker],
                before = previous[worker]
              if (job.error && (job.id !== before.id || job.error !== before.error))
                toast.add({
                  title: 'Operation needs attention',
                  description: job.error,
                  type: 'error',
                })
            }
          }
        } catch (error) {
          if (request.signal.aborted || !mounted.current) return
          if (error instanceof ApiError && error.status === 401) lock()
          else setConnectionError(errorText(error))
        } finally {
          if (mounted.current && !request.signal.aborted) setConnecting(false)
          if (inFlight.current?.controller === request) inFlight.current = null
        }
      })()
      inFlight.current = { key, promise, controller: request }
      return promise
    },
    [lock],
  )
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      controller.current?.abort()
    }
  }, [])
  const signature = JSON.stringify(query)
  useEffect(() => {
    void refresh()
  }, [signature, refresh])
  useEffect(() => {
    if (locked) return
    const tick = () => {
      if (!document.hidden) void refresh()
    }
    const interval = setInterval(
      tick,
      state?.job.running || state?.download_job.running ? 1500 : 15000,
    )
    document.addEventListener('visibilitychange', tick)
    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [locked, state?.job.running, state?.download_job.running, refresh])
  const action = useCallback(
    async (path: string, data: ActionData = {}, message?: string) => {
      if (actionLock.current) return false
      actionLock.current = true
      setPending({
        path,
        ids: Array.isArray(data.ids)
          ? (data.ids as string[])
          : typeof data.id === 'string'
            ? [data.id]
            : [],
      })
      try {
        const result = await api<{ added?: number }>(path, data)
        if (path === '/api/lock') {
          lock()
          return true
        }
        toast.add({
          title:
            message ||
            (path === '/api/queue'
              ? `${result.added || 0} files added to the queue`
              : 'Changes saved'),
          type: 'success',
        })
        await refresh(true)
        return true
      } catch (error) {
        if (error instanceof ApiError && error.status === 401 && path !== '/api/unlock') lock()
        toast.add({
          title: 'Could not complete action',
          description: errorText(error),
          type: 'error',
        })
        return false
      } finally {
        actionLock.current = false
        setPending(null)
      }
    },
    [refresh, lock],
  )
  return {
    state,
    locked,
    connecting,
    connectionError,
    pending,
    action,
    refresh,
    busy: !!(state?.job.running || state?.download_job.running),
    canStart:
      !state?.download_job.running &&
      (!state?.job.running || ['scan', 'monitor'].includes(state.job.kind)),
  }
}
export type Application = ReturnType<typeof useApplication>
