import { lazy, Suspense, useEffect, useState } from 'react'
import { Loader2, RefreshCw, Square } from 'lucide-react'
import { useApplication } from '@/hooks/use-application'
import type { QueueQuery } from '@/types'
import { AppSidebar, type View } from '@/components/app-sidebar'
import { ThemeSwitcher } from '@/components/theme-switcher'
import { LoginForm } from '@/components/login-form'
const ProjectsPage = lazy(() =>
  import('@/components/projects-page').then((module) => ({ default: module.ProjectsPage })),
)
const DownloadsPage = lazy(() =>
  import('@/components/downloads-page').then((module) => ({ default: module.DownloadsPage })),
)
const SessionPage = lazy(() =>
  import('@/components/session-page').then((module) => ({ default: module.SessionPage })),
)
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import { Separator } from '@/components/ui/separator'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from '@/components/ui/breadcrumb'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from '@/components/ui/toast'

export default function App() {
  const [view, setView] = useState<View>('projects'),
    [query, setQuery] = useState<QueueQuery>({
      page: 0,
      pageSize: 25,
      groupSize: 5,
      filter: 'all',
      search: '',
      groups: {},
    })
  const [visited, setVisited] = useState<Set<View>>(new Set(['projects']))
  const navigate = (next: View) => {
    setVisited((old) => new Set([...old, next]))
    setView(next)
  }
  const app = useApplication(query),
    state = app.state
  useEffect(() => {
    if (app.connectionError)
      toast.add({
        title: 'Connection unavailable',
        description: app.connectionError,
        type: 'error',
      })
  }, [app.connectionError])
  if (app.locked) return <LoginForm app={app} />
  if (!state)
    return (
      <main className="flex min-h-svh items-center justify-center p-6">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>
              {app.connectionError ? 'Could not connect' : 'Connecting to your library'}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {app.connectionError ? (
              <Button onClick={() => app.refresh()}>
                <RefreshCw />
                Retry connection
              </Button>
            ) : (
              <>
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
                <p className="flex gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  Restoring saved data…
                </p>
              </>
            )}
          </CardContent>
        </Card>
      </main>
    )
  return (
    <SidebarProvider>
      <AppSidebar view={view} onView={navigate} app={app} />
      <SidebarInset className="min-w-0">
        <header className="flex min-h-16 flex-wrap items-center gap-3 border-b px-4 lg:px-6">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-4" />
          <Breadcrumb className="mr-auto">
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbPage>
                  {view === 'projects'
                    ? 'Project library'
                    : view === 'downloads'
                      ? 'Downloads'
                      : 'Account & session'}
                </BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
          <Badge
            variant={app.connectionError ? 'destructive' : 'outline'}
            className="hidden sm:inline-flex"
          >
            {app.connectionError
              ? 'Reconnecting'
              : state.session.connected
                ? 'Session connected'
                : 'Session needs attention'}
          </Badge>
          <ThemeSwitcher />
        </header>
        {state.job.running && (
          <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2 text-sm lg:px-6">
            <Loader2 className="size-4 animate-spin text-primary" />
            <span className="min-w-0 flex-1 truncate">{state.job.message}</span>
            {state.job.total > 0 && (
              <Badge variant="secondary">
                {state.job.done}/{state.job.total}
              </Badge>
            )}
            {['scan', 'monitor'].includes(state.job.kind) && (
              <Button
                variant="outline"
                size="sm"
                disabled={!!app.pending}
                onClick={() => app.action('/api/stop', { target: 'scan' }, 'Stop requested')}
              >
                <Square />
                Stop scan
              </Button>
            )}
          </div>
        )}
        <main className="flex-1 p-4 md:p-6 lg:p-8">
          <Suspense fallback={<Skeleton className="h-64 w-full" />}>
            <section hidden={view !== 'projects'}>
              {visited.has('projects') && (
                <ProjectsPage app={app} onDownloads={() => navigate('downloads')} />
              )}
            </section>
            <section hidden={view !== 'downloads'}>
              {visited.has('downloads') && (
                <DownloadsPage app={app} query={query} setQuery={setQuery} />
              )}
            </section>
            <section hidden={view !== 'session'}>
              {visited.has('session') && <SessionPage app={app} active={view === 'session'} />}
            </section>
          </Suspense>
        </main>
        <footer className="border-t px-6 py-4 text-xs text-muted-foreground">
          Hi10 Download Manager · Your library, your server.
        </footer>
      </SidebarInset>
    </SidebarProvider>
  )
}
