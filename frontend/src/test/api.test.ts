import { describe, expect, it } from 'vitest'
import { mergeState } from '@/lib/api'
import type { AppState, StateResponse, Project } from '@/types'
describe('state merging', () => {
  it('preserves unchanged projects and merges only changed summaries', () => {
    const first = {
      projects: [
        { id: 'a', title: 'First' },
        { id: 'b', title: 'Second' },
      ],
    } as AppState
    const next = mergeState(first, {
      projects: null,
      project_updates: [{ id: 'a', title: 'Changed' }],
    } as StateResponse)
    expect(next.projects.map((p) => p.title)).toEqual(['Changed', 'Second'])
    expect(next.projects[1]).toBe(first.projects[1])
  })
  it('replaces catalog after full refresh and respects empty catalogs', () => {
    const first = { projects: [{ id: 'a' }] } as AppState
    expect(
      mergeState(first, { projects: [], project_updates: [] } as unknown as StateResponse).projects,
    ).toEqual([])
  })
})
