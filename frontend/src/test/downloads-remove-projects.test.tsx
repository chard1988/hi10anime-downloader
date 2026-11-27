import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DownloadsPage } from '@/components/downloads-page'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { Application } from '@/hooks/use-application'
import type { AppState, QueueQuery } from '@/types'

const query: QueueQuery = {
  page: 0,
  pageSize: 25,
  groupSize: 5,
  filter: 'all',
  search: '',
  groups: {},
}
function setup(overrides: Partial<AppState> = {}, pending: Application['pending'] = null) {
  const action = vi.fn().mockResolvedValue(true)
  const state = {
    projects: [
      { id: 'included', title: 'Included' },
      { id: 'excluded', title: 'Excluded', excluded: true },
    ],
    downloads: [],
    download_groups: [
      {
        id: 'included',
        title: 'Included',
        count: 1,
        complete: 0,
        failed: 1,
        page: 0,
        loaded: false,
      },
      {
        id: 'excluded',
        title: 'Excluded',
        count: 1,
        complete: 0,
        failed: 1,
        page: 0,
        loaded: false,
      },
      { id: 'unknown', title: 'Unknown', count: 1, complete: 0, failed: 1, page: 0, loaded: false },
    ],
    job: { running: false, kind: '' },
    download_job: { running: false, source: 'all', done: 1, total: 3 },
    session: { connected: true },
    schedule: { starts_at: null },
    pending_count: 3,
    download_total: 3,
    download_page: 0,
    download_page_total: 1,
    download_group_total: 3,
    transfer_settings: { version: 1, speed_limit_kbps: 0, parallel_downloads: 1 },
    ...overrides,
  } as AppState
  const app = {
    state,
    action,
    pending,
    busy: !!(state.job.running || state.download_job.running),
    canStart: false,
  } as unknown as Application
  render(
    <TooltipProvider>
      <DownloadsPage app={app} query={query} setQuery={vi.fn()} />
    </TooltipProvider>,
  )
  return { action, button: screen.getByRole('button', { name: 'Remove selected projects' }) }
}
describe('removing selected queue projects', () => {
  it('removes selected groups across all item pages, including excluded and orphan groups', async () => {
    const user = userEvent.setup(),
      { action, button } = setup()
    expect(button).toBeDisabled()
    expect(
      screen.queryByRole('button', { name: 'Re-scan selected projects' }),
    ).not.toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: 'Select all queue projects on page' }))
    expect(button).toBeEnabled()
    await user.click(button)
    expect(action).toHaveBeenCalledExactlyOnceWith(
      '/api/downloads/remove-projects',
      { ids: ['included', 'excluded', 'unknown'] },
      'Selected projects removed from queue; downloaded files retained',
    )
    expect(button).toBeDisabled()
  })
  it('allows removing queue groups for projects no longer present in the library without a session', async () => {
    const user = userEvent.setup(),
      { button, action } = setup({ session: { connected: false } as AppState['session'] })
    await user.click(screen.getByRole('checkbox', { name: 'Select project Unknown' }))
    expect(button).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Exclude selected projects' })).toBeDisabled()
    await user.click(button)
    expect(action).toHaveBeenCalledWith(
      '/api/downloads/remove-projects',
      { ids: ['unknown'] },
      expect.any(String),
    )
  })
  it.each(['scan', 'monitor', 'session'])('blocks removal during %s', async (kind) => {
    const user = userEvent.setup(),
      { button } = setup({ job: { kind, running: true } as AppState['job'] })
    await user.click(screen.getByRole('checkbox', { name: 'Select all queue projects on page' }))
    expect(button).toBeDisabled()
  })
  it('blocks removal while downloading', async () => {
    const user = userEvent.setup(),
      { button } = setup({ download_job: { running: true } as AppState['download_job'] })
    await user.click(screen.getByRole('checkbox', { name: 'Select all queue projects on page' }))
    expect(button).toBeDisabled()
  })
  it('shows immediate feedback and blocks duplicate removal requests', async () => {
    const user = userEvent.setup(),
      { button } = setup({}, { path: '/api/downloads/remove-projects', ids: ['included'] })
    await user.click(screen.getByRole('checkbox', { name: 'Select all queue projects on page' }))
    expect(button).toBeDisabled()
    expect(button.querySelector('.animate-spin')).not.toBeNull()
  })
})
