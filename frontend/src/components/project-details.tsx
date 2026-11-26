import { useEffect, useMemo, useState } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { Loader2, Save } from 'lucide-react'
import { api, errorText, qualityOptions } from '@/lib/api'
import type { Application } from '@/hooks/use-application'
import type { DetailFile, ProjectDetail } from '@/types'
import { FormSheet } from '@/components/form-sheet'
import { DataTable } from '@/components/data-table'
import { SearchCombobox } from '@/components/search-combobox'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { toast } from '@/components/ui/toast'

export function ProjectDetails({
  id,
  onClose,
  app,
}: {
  id: string | null
  onClose: () => void
  app: Application
}) {
  const [detail, setDetail] = useState<ProjectDetail | null>(null),
    [choices, setChoices] = useState<Record<string, number>>({}),
    [sections, setSections] = useState<string[]>([]),
    [qualities, setQualities] = useState<Record<string, number>>({}),
    [search, setSearch] = useState('')
  useEffect(() => {
    if (!id) return
    const controller = new AbortController()
    setDetail(null)
    setSearch('')
    api<ProjectDetail>(`/api/project/${encodeURIComponent(id)}`, undefined, controller.signal)
      .then((data) => {
        setDetail(data)
        setChoices(data.choices)
        setSections(data.sections.filter((s) => s.enabled).map((s) => s.id))
        setQualities(Object.fromEntries(data.sections.map((s) => [s.id, s.preferred])))
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          toast.add({ title: 'Could not load files', description: errorText(error), type: 'error' })
          onClose()
        }
      })
    return () => controller.abort()
  }, [id])
  const files = useMemo(
    () =>
      (detail?.files || [])
        .filter((f) => f.filename.toLowerCase().includes(search.toLowerCase()))
        .map((f) => ({ ...f, id: f.key })),
    [detail, search],
  )
  const columns: ColumnDef<DetailFile & { id: string }>[] = [
    {
      accessorKey: 'filename',
      header: 'File',
      cell: ({ row }) => (
        <div className="max-w-md whitespace-normal break-all">
          <span className="font-medium">{row.original.filename}</span>
          <p className="mt-1 text-xs text-muted-foreground">
            Selected: {row.original.selected || 'Unknown'}p
          </p>
        </div>
      ),
    },
    {
      id: 'quality',
      header: 'Quality preference',
      cell: ({ row }) => (
        <SearchCombobox
          label={`Quality for ${row.original.filename}`}
          value={String(choices[row.original.key] || 0)}
          options={qualityOptions(
            row.original.qualities,
            row.original.section_id ? 'Section preference' : 'Project preference',
          )}
          onChange={(value) => setChoices((old) => ({ ...old, [row.original.key]: Number(value) }))}
          disabled={
            app.busy ||
            !!app.pending ||
            (!!row.original.section_id && !sections.includes(row.original.section_id))
          }
        />
      ),
    },
  ]
  const save = async () => {
    if (
      detail &&
      (await app.action(
        '/api/project/settings',
        {
          id: detail.id,
          choices,
          ...(detail.sections.length ? { sections, section_qualities: qualities } : {}),
        },
        'Download selection saved',
      ))
    )
      onClose()
  }
  return (
    <FormSheet
      open={!!id}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      title={detail?.title || 'Project files'}
      description="Choose included sections and preferred quality. Per-file preferences override section and project settings."
      wide
    >
      {!detail ? (
        <Loader2 className="animate-spin" aria-label="Loading files" />
      ) : (
        <div className="space-y-6">
          {detail.sections.length > 0 && (
            <>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  disabled={app.busy}
                  onClick={() => setSections(detail.sections.map((s) => s.id))}
                >
                  Include all sections
                </Button>
                <Button variant="outline" disabled={app.busy} onClick={() => setSections([])}>
                  Clear sections
                </Button>
              </div>
              {detail.sections.map((section) => (
                <Card key={section.id}>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-3">
                      <Checkbox
                        id={`section-${section.id}`}
                        aria-label={`Include ${section.title}`}
                        checked={sections.includes(section.id)}
                        disabled={app.busy}
                        onCheckedChange={(checked) =>
                          setSections((old) =>
                            checked ? [...old, section.id] : old.filter((id) => id !== section.id),
                          )
                        }
                      />
                      <Label htmlFor={`section-${section.id}`}>{section.title}</Label>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-wrap items-center justify-between gap-3">
                    <span className="text-muted-foreground">{section.count} files</span>
                    <SearchCombobox
                      label={`Quality preference for section ${section.title}`}
                      value={String(qualities[section.id] || 0)}
                      options={qualityOptions(section.qualities, 'Project preference')}
                      disabled={app.busy || !sections.includes(section.id)}
                      onChange={(value) =>
                        setQualities((old) => ({ ...old, [section.id]: Number(value) }))
                      }
                    />
                  </CardContent>
                </Card>
              ))}
            </>
          )}
          <Input
            aria-label="Search project files"
            placeholder="Search files…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <DataTable data={files} columns={columns} />
          <div className="sticky bottom-0 flex items-center justify-between gap-3 border-t bg-popover py-4">
            <span className="text-sm text-muted-foreground">
              {
                detail.files.filter(
                  (f) => !detail.sections.length || sections.includes(f.section_id || ''),
                ).length
              }{' '}
              files selected
            </span>
            <Button disabled={app.busy || !!app.pending} onClick={save}>
              {app.pending ? <Loader2 className="animate-spin" /> : <Save />}Save choices
            </Button>
          </div>
        </div>
      )}
    </FormSheet>
  )
}
