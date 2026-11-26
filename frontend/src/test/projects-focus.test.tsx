import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ProjectsPage } from '@/components/projects-page'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { Application } from '@/hooks/use-application'
import type { AppState, Project } from '@/types'
const project: Project = {
  id: 'p1',
  title: 'Example project',
  url: 'https://hi10anime.com/example',
  scanned: true,
  count: 1,
  remaining: 1,
  complete: 0,
  qualities: [1080, 720],
  preferred: 0,
  section_count: 0,
  selected_section_count: 0,
}
const state = {
  projects: [project],
  job: { running: false, kind: '', done: 0, total: 0, error: null },
  download_job: { running: false, kind: '', done: 0, total: 0, error: null },
  session: { connected: true },
  monitoring: { count: 0, active_count: 0, paused: false, interval_minutes: 60 },
  default_quality: 0,
} as AppState
describe('project table polling', () => {
  it('preserves quality combobox input and focus when unrelated state updates arrive', async () => {
    const user = userEvent.setup()
    const app = {
      state,
      busy: false,
      pending: null,
      canStart: true,
      action: vi.fn(),
    } as unknown as Application
    const { rerender } = render(
      <TooltipProvider>
        <ProjectsPage app={app} onDownloads={() => {}} />
      </TooltipProvider>,
    )
    const input = screen.getByRole('combobox', { name: 'Quality preference for Example project' })
    await user.click(input)
    await user.clear(input)
    await user.type(input, '1080')
    expect(input).toHaveFocus()
    rerender(
      <TooltipProvider>
        <ProjectsPage
          app={{ ...app, state: { ...state, download_job: { ...state.download_job, done: 4 } } }}
          onDownloads={() => {}}
        />
      </TooltipProvider>,
    )
    expect(input).toHaveFocus()
    expect(input).toHaveValue('1080')
    expect(screen.getByRole('option', { name: 'Prefer 1080p' })).toBeVisible()
  })
})

describe('project summary metrics', () => {
  it('counts projects separately from files and updates after polling', () => {
    const projects = [
      { ...project, id: 'ready', count: 10, remaining: 7, complete: 3 },
      { ...project, id: 'done', count: 10, remaining: 0, complete: 10 },
      { ...project, id: 'excluded-ready', excluded: true, count: 5, remaining: 5 },
      { ...project, id: 'excluded-done', excluded: true, count: 2, remaining: 0 },
      { ...project, id: 'empty', count: 0, remaining: 0 },
      { ...project, id: 'unscanned', scanned: false, count: null, remaining: null },
    ]
    const app = {
      state: { ...state, projects },
      busy: false,
      pending: null,
      action: vi.fn(),
    } as unknown as Application
    const metric = (label: string) =>
      within(screen.getByText(label, { exact: true }).closest('[data-slot="card"]')!).getByText(
        /^\d+$/,
      ).textContent
    const { rerender } = render(
      <TooltipProvider>
        <ProjectsPage app={app} onDownloads={() => {}} />
      </TooltipProvider>,
    )
    expect(metric('Projects in library')).toBe('6')
    expect(metric('Downloaded projects')).toBe('2')
    expect(metric('Ready for download projects')).toBe('1')
    expect(metric('Ready to download')).toBe('7')
    rerender(
      <TooltipProvider>
        <ProjectsPage
          app={{
            ...app,
            state: {
              ...app.state!,
              projects: projects.map((p) =>
                p.id === 'ready' ? { ...p, remaining: 0, complete: 10 } : p,
              ),
            },
          }}
          onDownloads={() => {}}
        />
      </TooltipProvider>,
    )
    expect(metric('Downloaded projects')).toBe('3')
    expect(metric('Ready for download projects')).toBe('0')
    expect(metric('Ready to download')).toBe('0')
  })
})
