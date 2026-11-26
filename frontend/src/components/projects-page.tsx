import { useDeferredValue, useMemo, useState } from 'react'
import type { ColumnDef, RowSelectionState } from '@tanstack/react-table'
import {
  ArrowUpDown,
  Check,
  Download,
  Eye,
  EyeOff,
  FileSearch,
  Folder,
  Loader2,
  MoreHorizontal,
  RefreshCw,
  Settings2,
  ShieldOff,
} from 'lucide-react'
import type { Project } from '@/types'
import type { Application } from '@/hooks/use-application'
import { qualityOptions } from '@/lib/api'
import { DataTable } from '@/components/data-table'
import { SearchCombobox } from '@/components/search-combobox'
import { ProjectDetails } from '@/components/project-details'
import { MonitoringSheet } from '@/components/monitoring-sheet'
import { IconButton } from '@/components/icon-button'
import { Button } from '@/components/ui/button'
import { ButtonGroup } from '@/components/ui/button-group'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'

export function ProjectsPage({ app, onDownloads }: { app: Application; onDownloads: () => void }) {
  const state = app.state!,
    [search, setSearch] = useState(''),
    [filter, setFilter] = useState('all'),
    [selection, setSelection] = useState<RowSelectionState>({}),
    [detailId, setDetailId] = useState<string | null>(null),
    [monitorOpen, setMonitorOpen] = useState(false)
  const query = useDeferredValue(search.trim().toLowerCase())
  const rows = useMemo(
    () =>
      state.projects.filter(
        (p) =>
          p.title.toLowerCase().includes(query) &&
          (filter === 'all' ||
            (filter === 'excluded' && p.excluded) ||
            (filter === 'monitored' && p.monitored && !p.excluded) ||
            (filter === 'ready' && !p.excluded && (p.remaining || 0) > 0) ||
            (filter === 'unscanned' && !p.scanned) ||
            (filter === 'complete' && !!p.count && p.remaining === 0) ||
            (filter === 'issues' && !!(p.error || p.monitor_error) && !p.excluded)),
      ),
    [state.projects, query, filter],
  )
  const selected = state.projects.filter((p) => selection[p.id]),
    ids = selected.map((p) => p.id),
    included = selected.filter((p) => !p.excluded).map((p) => p.id)
  const pending = !!app.pending,
    mutating = app.busy || pending
  const columns = useMemo<ColumnDef<Project>[]>(
    () => [
      {
        id: 'select',
        header: ({ table }) => (
          <Checkbox
            aria-label="Select all projects on page"
            checked={table.getIsAllPageRowsSelected()}
            indeterminate={table.getIsSomePageRowsSelected()}
            onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            aria-label={`Select ${row.original.title}`}
            checked={row.getIsSelected()}
            onCheckedChange={(value) => row.toggleSelected(!!value)}
          />
        ),
      },
      {
        accessorKey: 'title',
        header: ({ column }) => (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Project
            <ArrowUpDown />
          </Button>
        ),
        cell: ({ row }) => {
          const p = row.original
          return (
            <div className="min-w-56 max-w-lg space-y-1 whitespace-normal">
              <a
                className="font-medium hover:text-primary hover:underline"
                href={p.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {p.title}
              </a>
              <p className="text-xs text-muted-foreground">
                {p.scanned
                  ? `${p.count || 0} files detected · ${p.complete} downloaded`
                  : 'Scan to discover files'}
                {p.section_count > 1
                  ? ` · ${p.selected_section_count}/${p.section_count} sections`
                  : ''}
              </p>
              {p.monitored && (
                <Badge variant="outline">
                  <Eye className="size-3" />
                  {p.excluded ? 'Monitoring suspended' : 'Monitored'}
                </Badge>
              )}
            </div>
          )
        },
      },
      {
        accessorKey: 'remaining',
        header: 'Remaining',
        cell: ({ row }) => row.original.remaining ?? '—',
      },
      {
        id: 'quality',
        header: 'Quality',
        cell: ({ row }) => (
          <div className="flex gap-1">
            {row.original.qualities.map((q) => (
              <Badge key={q} variant="secondary">
                {q || '?'}p
              </Badge>
            ))}
          </div>
        ),
      },
      {
        id: 'status',
        header: 'Status',
        cell: ({ row }) => {
          const p = row.original,
            scanning =
              state.job.running &&
              ['scan', 'monitor'].includes(state.job.kind) &&
              state.job.project_id === p.id
          return (
            <Badge
              variant={p.error || p.monitor_error ? 'destructive' : 'outline'}
              title={p.error || p.monitor_error || undefined}
            >
              {scanning ? (
                <>
                  <Loader2 className="size-3 animate-spin" />
                  Scanning
                </>
              ) : p.excluded ? (
                'Excluded'
              ) : p.restoring ? (
                'Restoring'
              ) : p.error || p.monitor_error ? (
                'Needs attention'
              ) : !p.scanned ? (
                'Not scanned'
              ) : !p.count ? (
                'No files'
              ) : p.remaining ? (
                'Ready'
              ) : (
                'Downloaded'
              )}
            </Badge>
          )
        },
      },
      {
        id: 'actions',
        header: 'Actions',
        cell: ({ row }) => {
          const p = row.original
          return (
            <div className="flex items-center gap-1">
              {p.scanned && !!p.qualities.length && !p.error ? (
                <>
                  <SearchCombobox
                    label={`Quality preference for ${p.title}`}
                    value={String(p.preferred)}
                    options={qualityOptions(p.qualities)}
                    disabled={mutating}
                    onChange={(value) =>
                      app.action('/api/project/settings', { id: p.id, quality: Number(value) })
                    }
                  />
                  <IconButton
                    label={`Review files for ${p.title}`}
                    onClick={() => setDetailId(p.id)}
                  >
                    <MoreHorizontal />
                  </IconButton>
                </>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={
                    !!state.job.running || pending || p.excluded || !state.session.connected
                  }
                  onClick={() => app.action('/api/scan', { ids: [p.id] }, 'Scan requested')}
                >
                  <FileSearch />
                  {p.error ? 'Retry scan' : 'Scan page'}
                </Button>
              )}
              <IconButton
                label={`${p.monitored ? 'Unmonitor' : 'Monitor'} project ${p.title}`}
                disabled={pending || (!p.monitored && p.excluded)}
                onClick={() =>
                  app.action('/api/monitoring/projects', { ids: [p.id], enabled: !p.monitored })
                }
              >
                {p.monitored ? <EyeOff /> : <Eye />}
              </IconButton>
            </div>
          )
        },
      },
    ],
    [
      mutating,
      pending,
      state.session.connected,
      state.job.running,
      state.job.kind,
      state.job.project_id,
      app.action,
    ],
  )
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium tracking-widest text-muted-foreground uppercase">
            Your next collection
          </p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">Project library</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Discover projects, choose your quality, and bring them home.
          </p>
        </div>
        <ButtonGroup className="max-w-full flex-wrap">
          <Button variant="outline" onClick={() => setMonitorOpen(true)}>
            <Settings2 />
            Monitoring{state.monitoring.count ? ` · ${state.monitoring.count}` : ''}
          </Button>
          <Button
            variant="outline"
            disabled={mutating || !state.session.connected}
            onClick={() => app.action('/api/refresh', {}, 'Refreshing projects')}
          >
            <RefreshCw />
            Refresh projects
          </Button>
        </ButtonGroup>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {[
          {
            label: 'Projects in library',
            value: state.projects.length,
            description: 'Your Hi10 collection',
            icon: Folder,
          },
          {
            label: 'Ready to download',
            value: state.projects
              .filter((p) => !p.excluded)
              .reduce((s, p) => s + (p.remaining || 0), 0),
            description: 'Files available across scanned projects',
            icon: Download,
          },
        ].map((card) => (
          <Card key={card.label}>
            <CardHeader>
              <CardDescription className="flex justify-between">
                {card.label}
                <card.icon className="size-4" />
              </CardDescription>
              <CardTitle className="text-3xl tabular-nums">{card.value.toLocaleString()}</CardTitle>
            </CardHeader>
            <CardContent className="text-xs text-muted-foreground">{card.description}</CardContent>
          </Card>
        ))}
        <Card>
          <CardHeader>
            <CardDescription>Default quality preference</CardDescription>
            <CardTitle>
              <SearchCombobox
                label="Default video quality"
                value={String(state.default_quality)}
                options={qualityOptions()}
                disabled={mutating}
                onChange={(value) => app.action('/api/preferences', { quality: Number(value) })}
                className="w-full"
              />
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            Falls back to highest if unavailable. File choices take priority.
          </CardContent>
        </Card>
      </div>
      <div className="space-y-4">
        <div className="flex flex-wrap gap-3">
          <Input
            aria-label="Search projects"
            placeholder="Search projects…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="min-w-40 flex-1"
          />
          <SearchCombobox
            label="Filter projects"
            value={filter}
            onChange={setFilter}
            options={[
              ['all', 'All projects'],
              ['ready', 'Ready to download'],
              ['unscanned', 'Not scanned'],
              ['complete', 'Downloaded'],
              ['issues', 'Needs attention'],
              ['monitored', 'Monitored'],
              ['excluded', 'Excluded'],
            ].map(([value, label]) => ({ value, label }))}
          />
          <Button
            variant="outline"
            disabled={
              !!state.job.running || pending || !state.projects.length || !state.session.connected
            }
            onClick={() =>
              app.action(
                '/api/scan',
                { ids: state.projects.map((p) => p.id) },
                'Scanning all included projects',
              )
            }
          >
            <FileSearch />
            Scan all pages
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-card p-3">
          <span className="mr-auto text-sm text-muted-foreground">
            {ids.length} projects selected
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={
              pending || !included.length || !!state.job.running || !state.session.connected
            }
            onClick={() => app.action('/api/scan', { ids: included }, 'Selected scan requested')}
          >
            <FileSearch />
            Scan selected pages
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={pending || !included.length}
            onClick={() => app.action('/api/monitoring/projects', { ids: included, enabled: true })}
          >
            <Eye />
            Monitor selected
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={pending || !selected.some((p) => p.monitored)}
            onClick={() => app.action('/api/monitoring/projects', { ids, enabled: false })}
          >
            <EyeOff />
            Unmonitor selected
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={mutating || !included.length}
            onClick={() => app.action('/api/projects/exclude', { ids: included, excluded: true })}
          >
            <ShieldOff />
            Exclude selected
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={mutating || !selected.some((p) => p.excluded)}
            onClick={() => app.action('/api/projects/exclude', { ids, excluded: false })}
          >
            <Check />
            Include selected
          </Button>
          <Button
            size="sm"
            disabled={mutating || !ids.length || selected.some((p) => p.excluded || !p.count)}
            onClick={async () => {
              if (await app.action('/api/queue', { ids })) onDownloads()
            }}
          >
            <Download />
            Add to queue
          </Button>
        </div>
        <DataTable
          data={rows}
          columns={columns}
          selection={selection}
          onSelectionChange={setSelection}
          empty={
            state.projects.length
              ? 'No projects match your filters.'
              : 'Connect your session, then refresh projects to build your library.'
          }
        />
      </div>
      <ProjectDetails id={detailId} onClose={() => setDetailId(null)} app={app} />
      <MonitoringSheet open={monitorOpen} onOpenChange={setMonitorOpen} app={app} />
    </div>
  )
}
