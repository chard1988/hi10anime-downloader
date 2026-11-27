import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from 'react'
import type { ColumnDef, RowSelectionState } from '@tanstack/react-table'
import {
  ChevronDown,
  ChevronRight,
  ExternalLink,
  FileSearch,
  Link,
  Loader2,
  Play,
  RefreshCw,
  Save,
  Settings2,
  ShieldOff,
  Square,
  Trash2,
} from 'lucide-react'
import type { Application } from '@/hooks/use-application'
import type { QueueGroup, QueueItem, QueueQuery } from '@/types'
import { api, bytes, errorText } from '@/lib/api'
import { DataTable } from '@/components/data-table'
import { FormSheet } from '@/components/form-sheet'
import { IconButton } from '@/components/icon-button'
import { SearchCombobox } from '@/components/search-combobox'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ButtonGroup } from '@/components/ui/button-group'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { TableCell, TableRow } from '@/components/ui/table'
import { toast } from '@/components/ui/toast'

export function DownloadsPage({
  app,
  query,
  setQuery,
}: {
  app: Application
  query: QueueQuery
  setQuery: Dispatch<SetStateAction<QueueQuery>>
}) {
  const state = app.state!,
    [settings, setSettings] = useState(false),
    [selection, setSelection] = useState<RowSelectionState>({}),
    [groupSelection, setGroupSelection] = useState<RowSelectionState>({}),
    [expanded, setExpanded] = useState<Record<string, boolean>>({}),
    [link, setLink] = useState<{ id: string; url: string; editable: boolean } | null>(null),
    [loadingLink, setLoadingLink] = useState(''),
    [search, setSearch] = useState(query.search)
  useEffect(() => {
    if (search === query.search) return
    const timer = setTimeout(
      () => setQuery((old) => ({ ...old, search, page: 0, groups: {} })),
      300,
    )
    return () => clearTimeout(timer)
  }, [search, query.search, setQuery])
  const selected = Object.keys(selection).filter((id) => selection[id]),
    selectedGroups = Object.keys(groupSelection).filter((id) => groupSelection[id])
  const includedProjectIds = useMemo(
    () =>
      new Set(state.projects.filter((project) => !project.excluded).map((project) => project.id)),
    [state.projects],
  )
  const scanIds = selectedGroups.filter((id) => includedProjectIds.has(id))
  const busy = app.busy || !!app.pending,
    pending = !!app.pending
  const setPage = (page: number) => setQuery({ ...query, page, groups: {} })
  const openGroup = (id: string) => {
    const groups = { ...query.groups }
    if (id in groups) delete groups[id]
    else {
      if (Object.keys(groups).length >= 5) {
        toast.add({ title: 'Open up to five projects at a time', type: 'info' })
        return
      }
      groups[id] = 0
    }
    setQuery({ ...query, groups })
  }
  const viewLink = async (item: QueueItem) => {
    setLoadingLink(item.id)
    try {
      const result = await api<{ url: string }>(`/api/download-link/${encodeURIComponent(item.id)}`)
      setLink({
        id: item.id,
        url: result.url,
        editable: ['queued', 'failed', 'interrupted'].includes(item.status),
      })
    } catch (error) {
      toast.add({ title: 'Could not load link', description: errorText(error), type: 'error' })
    } finally {
      setLoadingLink('')
    }
  }
  const columns = useMemo<ColumnDef<QueueGroup>[]>(
    () => [
      {
        id: 'select',
        header: ({ table }) => (
          <Checkbox
            aria-label="Select all queue projects on page"
            checked={table.getIsAllPageRowsSelected()}
            indeterminate={table.getIsSomePageRowsSelected()}
            onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            aria-label={`Select project ${row.original.title} for exclusion`}
            checked={row.getIsSelected()}
            disabled={!state.projects.some((p) => p.id === row.id)}
            onCheckedChange={(value) => row.toggleSelected(!!value)}
          />
        ),
      },
      {
        accessorKey: 'title',
        header: 'Project',
        cell: ({ row }) => (
          <Button
            variant="ghost"
            className="h-auto max-w-lg justify-start whitespace-normal py-2 text-left"
            onClick={() => openGroup(row.id)}
            aria-expanded={row.id in query.groups}
          >
            {row.id in query.groups ? <ChevronDown /> : <ChevronRight />}
            {row.original.title}
          </Button>
        ),
      },
      { accessorKey: 'count', header: 'Files' },
      { accessorKey: 'complete', header: 'Completed' },
      {
        accessorKey: 'failed',
        header: 'Failed',
        cell: ({ row }) => (
          <Badge variant={row.original.failed ? 'destructive' : 'secondary'}>
            {row.original.failed}
          </Badge>
        ),
      },
    ],
    [state.projects, query, setQuery],
  )
  const fileColumns = useMemo<ColumnDef<QueueItem>[]>(
    () => [
      {
        id: 'select',
        header: ({ table }) => (
          <Checkbox
            aria-label="Select loaded queue items"
            checked={table.getIsAllPageRowsSelected()}
            indeterminate={table.getIsSomePageRowsSelected()}
            onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            aria-label={`Select ${row.original.filename}`}
            checked={row.getIsSelected()}
            onCheckedChange={(value) => row.toggleSelected(!!value)}
          />
        ),
      },
      {
        accessorKey: 'filename',
        header: 'Filename',
        cell: ({ row }) => (
          <Button
            variant="ghost"
            className="h-auto min-w-48 max-w-xl justify-start whitespace-normal break-all py-2 text-left"
            aria-expanded={!!expanded[row.id]}
            onClick={() => setExpanded((old) => ({ ...old, [row.id]: !old[row.id] }))}
          >
            {expanded[row.id] ? <ChevronDown /> : <ChevronRight />}
            {row.original.filename}
          </Button>
        ),
      },
      {
        accessorKey: 'status',
        header: 'Status',
        cell: ({ row }) => (
          <Badge variant={row.original.status === 'failed' ? 'destructive' : 'outline'}>
            {row.original.status === 'downloading' && <Loader2 className="size-3 animate-spin" />}
            {row.original.status}
          </Badge>
        ),
      },
      {
        id: 'actions',
        header: 'Actions',
        cell: ({ row }) => {
          const item = row.original
          return (
            <ButtonGroup className="max-w-full flex-wrap">
              <IconButton
                label="View download link"
                disabled={loadingLink === item.id}
                onClick={() => viewLink(item)}
              >
                {loadingLink === item.id ? <Loader2 className="animate-spin" /> : <Link />}
              </IconButton>
              <IconButton
                label="Open in new tab"
                render={
                  <a
                    href={`/api/download-link/${encodeURIComponent(item.id)}?open=1`}
                    target="_blank"
                    rel="noopener noreferrer"
                  />
                }
              >
                <ExternalLink />
              </IconButton>
              <IconButton
                label={item.status === 'queued' ? 'Start this item' : 'Retry download'}
                disabled={
                  !['queued', 'failed', 'interrupted'].includes(item.status) ||
                  !app.canStart ||
                  pending
                }
                onClick={() =>
                  app.action('/api/downloads/retry', { id: item.id }, 'Download requested')
                }
              >
                {app.pending?.path === '/api/downloads/retry' &&
                app.pending.ids.includes(item.id) ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <RefreshCw />
                )}
              </IconButton>
              <IconButton
                label="Remove from queue"
                disabled={busy || !['queued', 'failed', 'interrupted'].includes(item.status)}
                onClick={async () => {
                  if (
                    await app.action('/api/downloads/remove', { id: item.id }, 'Queue item removed')
                  )
                    setSelection((old) => {
                      const next = { ...old }
                      delete next[item.id]
                      return next
                    })
                }}
              >
                <Trash2 />
              </IconButton>
            </ButtonGroup>
          )
        },
      },
    ],
    [expanded, app.pending, app.canStart, busy, loadingLink, app.action],
  )
  const details = (item: QueueItem) =>
    expanded[item.id] ? (
      <TableRow>
        <TableCell colSpan={4} className="bg-muted/30">
          <div className="space-y-3 p-3 text-sm">
            <p>{item.project}</p>
            <div>
              <span className="font-medium">Destination</span>
              <p className="mt-1 break-all font-mono text-xs">
                {item.destination || 'Destination unavailable for this older queue entry.'}
              </p>
            </div>
            <p>
              {bytes(item.bytes)}
              {item.total ? ` / ${bytes(item.total)}` : ''}
            </p>
            {['downloading', 'complete'].includes(item.status) && (
              <Progress
                value={item.total ? (item.bytes / item.total) * 100 : 0}
                aria-label={`Download progress for ${item.filename}`}
              />
            )}{' '}
            {item.message && (
              <div>
                <span className="font-medium">
                  {item.status === 'failed' ? 'Failure reason' : 'Details'}
                </span>
                <p className="mt-1 whitespace-pre-wrap break-words text-muted-foreground">
                  {item.message}
                </p>
              </div>
            )}
          </div>
        </TableCell>
      </TableRow>
    ) : null
  const groupRows = (group: QueueGroup) =>
    !(group.id in query.groups) ? null : (
      <TableRow>
        <TableCell colSpan={5} className="bg-muted/20 p-3 sm:p-5">
          <DataTable
            data={state.downloads.filter((item) => item.group_id === group.id)}
            columns={fileColumns}
            selection={selection}
            onSelectionChange={setSelection}
            renderExpanded={details}
            loading={!group.loaded}
            manual={{
              page: group.page,
              size: query.pageSize,
              pages: Math.max(1, Math.ceil(group.count / query.pageSize)),
              total: group.count,
              onPage: (page) =>
                setQuery({ ...query, groups: { ...query.groups, [group.id]: page } }),
              onSize: (pageSize) =>
                setQuery({
                  ...query,
                  pageSize,
                  groups: Object.fromEntries(Object.keys(query.groups).map((id) => [id, 0])),
                }),
            }}
          />
        </TableCell>
      </TableRow>
    )
  const startLabel = (source: 'all' | 'selected', label: string) =>
    app.pending?.path ===
    (source === 'all' ? '/api/downloads/start' : '/api/downloads/start-selected') ? (
      <>
        <Loader2 className="animate-spin" />
        {label}
      </>
    ) : state.download_job.running &&
      (source === 'selected'
        ? state.download_job.source === 'selected'
        : state.download_job.source !== 'selected') ? (
      <>
        <Loader2 className="animate-spin" />
        {label} {state.download_job.done}/{state.download_job.total}
      </>
    ) : (
      <>
        <Play />
        {label}
      </>
    )
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium tracking-widest text-muted-foreground uppercase">
            From the web to your server
          </p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">Downloads</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {state.pending_count} files waiting · {state.download_total} queue entries
          </p>
        </div>
        <ButtonGroup className="max-w-full flex-wrap">
          <Button variant="outline" onClick={() => setSettings(true)}>
            <Settings2 />
            Settings
          </Button>
          <Button
            disabled={!app.canStart || pending || !state.pending_count}
            onClick={() => app.action('/api/downloads/start', {}, 'Downloads started')}
          >
            {startLabel('all', 'Start downloads')}
          </Button>
          <Button
            variant="outline"
            disabled={!state.download_job.running || pending}
            onClick={() => app.action('/api/stop', { target: 'download' }, 'Stop requested')}
          >
            <Square />
            Stop batch
          </Button>
        </ButtonGroup>
      </div>
      {state.schedule.starts_at && (
        <Badge variant="outline">
          Scheduled for {new Date(state.schedule.starts_at * 1000).toLocaleString()}
        </Badge>
      )}
      <div className="flex flex-wrap gap-3">
        <Input
          aria-label="Search queue"
          maxLength={200}
          placeholder="Search projects or filenames…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="min-w-40 flex-1"
        />
        <SearchCombobox
          label="Queue status"
          value={query.filter}
          onChange={(filter) => setQuery({ ...query, filter, page: 0, groups: {} })}
          options={['all', 'queued', 'downloading', 'failed', 'interrupted', 'complete'].map(
            (value) => ({
              value,
              label: value === 'all' ? 'All items' : value[0].toUpperCase() + value.slice(1),
            }),
          )}
        />
        <Button
          variant="outline"
          disabled={busy || !state.download_total}
          onClick={() =>
            app.action(
              '/api/downloads/clear-completed',
              {},
              'Completed entries cleared; files retained',
            )
          }
        >
          <Trash2 />
          Clear completed downloads
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-card p-3">
        <span className="mr-auto text-sm text-muted-foreground">
          {selected.length} files · {selectedGroups.length} projects selected
        </span>
        <Button
          size="sm"
          disabled={!selected.length || !app.canStart || pending}
          onClick={async () => {
            if (
              await app.action(
                '/api/downloads/start-selected',
                { ids: selected },
                'Selected downloads started',
              )
            )
              setSelection({})
          }}
        >
          {startLabel('selected', 'Start selected')}
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={!selected.length || busy}
          onClick={async () => {
            if (
              await app.action(
                '/api/downloads/remove-selected',
                { ids: selected },
                'Selected queue entries removed',
              )
            )
              setSelection({})
          }}
        >
          <Trash2 />
          Remove selected
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={!scanIds.length || state.job.running || pending || !state.session.connected}
          onClick={() =>
            app.action('/api/scan', { ids: scanIds }, 'Re-scanning selected project pages')
          }
        >
          {app.pending?.path === '/api/scan' ? (
            <Loader2 className="animate-spin" />
          ) : (
            <FileSearch />
          )}
          Re-scan selected projects
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={!selectedGroups.length || busy}
          onClick={async () => {
            if (
              await app.action(
                '/api/projects/exclude',
                { ids: selectedGroups, excluded: true },
                'Selected projects excluded; completed files retained',
              )
            ) {
              setGroupSelection({})
              setSelection({})
              setQuery({ ...query, groups: {} })
            }
          }}
        >
          <ShieldOff />
          Exclude selected projects
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={!selected.length && !selectedGroups.length}
          onClick={() => {
            setSelection({})
            setGroupSelection({})
          }}
        >
          Clear selection
        </Button>
      </div>
      <DataTable
        data={state.download_groups}
        columns={columns}
        selection={groupSelection}
        onSelectionChange={setGroupSelection}
        renderExpanded={groupRows}
        manual={{
          page: state.download_page,
          size: query.groupSize,
          pages: state.download_page_total,
          total: state.download_group_total,
          onPage: setPage,
          onSize: (groupSize) => setQuery({ ...query, groupSize, page: 0, groups: {} }),
        }}
        empty="No queue entries match. Add scanned projects from your library."
      />
      <DownloadSettings open={settings} onOpenChange={setSettings} app={app} />
      <FormSheet
        open={!!link}
        onOpenChange={(open) => {
          if (!open) setLink(null)
        }}
        title="Download link"
        description="View or replace the direct file URL. Saving retains the filename and destination and does not start a download."
      >
        {link && (
          <form
            className="space-y-5"
            onSubmit={async (e) => {
              e.preventDefault()
              if (
                await app.action(
                  '/api/downloads/edit-url',
                  { id: link.id, url: link.url },
                  'URL saved; use Retry when ready',
                )
              )
                setLink(null)
            }}
          >
            <Label htmlFor="file-url">File URL</Label>
            <Input
              id="file-url"
              type="url"
              required
              value={link.url}
              onChange={(e) => setLink({ ...link, url: e.target.value })}
              readOnly={!link.editable || app.busy}
            />
            <p className="text-sm text-muted-foreground">
              Links may require your Hi10 session and may expire. Stop running jobs before editing.
            </p>
            <Button disabled={!link.editable || busy} type="submit">
              {app.pending ? <Loader2 className="animate-spin" /> : <Save />}Save URL
            </Button>
          </form>
        )}
      </FormSheet>
    </div>
  )
}
function DownloadSettings({
  open,
  onOpenChange,
  app,
}: {
  open: boolean
  onOpenChange: (value: boolean) => void
  app: Application
}) {
  const [date, setDate] = useState(''),
    state = app.state!
  const [speed, setSpeed] = useState(0),
    [parallel, setParallel] = useState(1)
  useEffect(() => {
    if (open) {
      setSpeed(state.transfer_settings.speed_limit_kbps)
      setParallel(state.transfer_settings.parallel_downloads)
    }
  }, [open])
  return (
    <FormSheet
      open={open}
      onOpenChange={onOpenChange}
      title="Download settings"
      description="Set transfer limits and choose when queued downloads should start."
    >
      <div className="space-y-6">
        <div className="space-y-2">
          <Label>Download destination</Label>
          <p className="break-all rounded-lg border bg-muted p-3 font-mono text-xs">
            {state.output}
          </p>
          <p className="text-sm text-muted-foreground">
            Change the host destination using the container’s /downloads mapping in unRAID.
          </p>
        </div>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            void app.action(
              '/api/downloads/settings',
              { speed_limit_kbps: speed, parallel_downloads: parallel },
              'Transfer limits saved. Changes apply to the next batch.',
            )
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="download-speed">Download speed limit (kbps)</Label>
            <Input
              id="download-speed"
              type="number"
              min={0}
              max={10000000}
              step={1}
              required
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
            />
            <p className="text-xs text-muted-foreground">
              Total limit shared across all downloads. 0 is unlimited. 1,000 kbps is approximately
              125 KB/s.
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="parallel-downloads">Maximum parallel downloads</Label>
            <Input
              id="parallel-downloads"
              type="number"
              min={1}
              max={8}
              step={1}
              required
              value={parallel}
              onChange={(e) => setParallel(Number(e.target.value))}
            />
            <p className="text-xs text-muted-foreground">
              Download 1 to 8 files at a time. More downloads use more server resources.
            </p>
          </div>
          <p className="text-xs text-muted-foreground">
            Saved across restarts. Changes apply to the next batch, including scheduled and
            monitored downloads. Stop and restart a running batch to use new limits.
          </p>
          <Button type="submit" disabled={!!app.pending}>
            {app.pending?.path === '/api/downloads/settings' ? (
              <Loader2 className="animate-spin" />
            ) : (
              <Save />
            )}
            Save transfer settings
          </Button>
        </form>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            const target = new Date(date)
            if (!Number.isFinite(target.getTime()) || target.getTime() <= Date.now()) {
              toast.add({ title: 'Choose a future date and time', type: 'error' })
              return
            }
            void app.action(
              '/api/downloads/schedule',
              { starts_at: target.toISOString() },
              'Scheduled start saved',
            )
          }}
        >
          <Label htmlFor="schedule-time">Start at a later date and time</Label>
          <Input
            id="schedule-time"
            type="datetime-local"
            required
            value={date}
            onChange={(e) => setDate(e.target.value)}
            disabled={app.busy}
          />
          <p className="text-xs text-muted-foreground">
            Timezone: {Intl.DateTimeFormat().resolvedOptions().timeZone}. The container must be
            running at the scheduled time.
          </p>
          <Button type="submit" disabled={app.busy || !!app.pending || !state.pending_count}>
            Schedule start
          </Button>
        </form>
        {state.schedule.starts_at && (
          <Button
            variant="outline"
            disabled={app.busy || !!app.pending}
            onClick={() => app.action('/api/downloads/unschedule', {}, 'Scheduled start cancelled')}
          >
            Cancel schedule
          </Button>
        )}
      </div>
    </FormSheet>
  )
}
