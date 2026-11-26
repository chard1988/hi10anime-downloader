import { Download, Library, LockKeyhole, Radio, ShieldCheck } from 'lucide-react'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import type { Application } from '@/hooks/use-application'
export type View = 'projects' | 'downloads' | 'session'
export function AppSidebar({
  view,
  onView,
  app,
}: {
  view: View
  onView: (view: View) => void
  app: Application
}) {
  const state = app.state!,
    { setOpenMobile } = useSidebar()
  const navigation = [
    {
      id: 'projects' as const,
      label: 'Project library',
      icon: Library,
      count: state.projects.length,
    },
    { id: 'downloads' as const, label: 'Downloads', icon: Download, count: state.pending_count },
    { id: 'session' as const, label: 'Account & session', icon: ShieldCheck },
  ]
  return (
    <Sidebar collapsible="icon" variant="inset">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" onClick={() => onView('projects')}>
              <div className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Download className="size-5" />
              </div>
              <div className="grid flex-1 text-left">
                <span className="font-semibold">Hi10</span>
                <span className="text-xs text-muted-foreground">Download manager</span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Workspace</SidebarGroupLabel>
          <SidebarMenu>
            {navigation.map((item) => (
              <SidebarMenuItem key={item.id}>
                <SidebarMenuButton
                  tooltip={item.label}
                  isActive={view === item.id}
                  onClick={() => {
                    onView(item.id)
                    setOpenMobile(false)
                  }}
                >
                  <item.icon />
                  <span>{item.label}</span>
                  {item.count !== undefined && (
                    <Badge
                      variant="secondary"
                      className="ml-auto tabular-nums group-data-[collapsible=icon]:hidden"
                    >
                      {item.count.toLocaleString()}
                    </Badge>
                  )}
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <div className="space-y-3 p-2 group-data-[collapsible=icon]:hidden">
          <div className="flex items-center gap-2 text-sm">
            <Radio className="size-4 text-primary" />
            {state.session.connected ? 'Session connected' : 'Session needs attention'}
          </div>
          <p className="text-xs text-muted-foreground">Your library. Your server.</p>
          <Separator />
          <Button
            variant="ghost"
            className="w-full justify-start"
            disabled={!!app.pending}
            onClick={() => app.action('/api/lock')}
          >
            <LockKeyhole />
            Lock interface
          </Button>
          <p className="text-xs text-muted-foreground">v{state.app_version}</p>
        </div>
      </SidebarFooter>
    </Sidebar>
  )
}
