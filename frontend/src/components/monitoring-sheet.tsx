import { useEffect, useState } from 'react'
import { Activity, Loader2, Save } from 'lucide-react'
import type { Application } from '@/hooks/use-application'
import { FormSheet } from '@/components/form-sheet'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
export function MonitoringSheet({
  open,
  onOpenChange,
  app,
}: {
  open: boolean
  onOpenChange: (value: boolean) => void
  app: Application
}) {
  const monitor = app.state!.monitoring
  const [interval, setInterval] = useState(60),
    [paused, setPaused] = useState(false)
  useEffect(() => {
    if (open) {
      setInterval(monitor.interval_minutes)
      setPaused(monitor.paused)
    }
  }, [open])
  return (
    <FormSheet
      open={open}
      onOpenChange={onOpenChange}
      title="Project monitoring"
      description="Automatically download existing missing files and future additions from monitored projects."
    >
      <div className="space-y-6">
        <Badge variant="secondary">
          {monitor.count} monitored · {monitor.active_count} active ·{' '}
          {monitor.paused ? 'Paused' : 'Enabled'}
        </Badge>
        <p className="text-sm text-muted-foreground">{monitor.message}</p>
        {!!monitor.next_check && !monitor.paused && (
          <p className="text-sm">
            Next check: {new Date(monitor.next_check * 1000).toLocaleString()}
          </p>
        )}
        <form
          className="space-y-5"
          onSubmit={(e) => {
            e.preventDefault()
            void app.action(
              '/api/monitoring/settings',
              { paused, interval_minutes: interval },
              'Monitoring settings saved',
            )
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="monitoring-interval">Check interval (minutes)</Label>
            <Input
              id="monitoring-interval"
              type="number"
              min={15}
              max={10080}
              required
              value={interval}
              onChange={(e) => setInterval(Number(e.target.value))}
            />
          </div>
          <Label className="flex items-center gap-3">
            <Checkbox checked={paused} onCheckedChange={(value) => setPaused(!!value)} />
            Pause automatic checks and downloads
          </Label>
          <Button type="submit" disabled={!!app.pending}>
            {app.pending ? <Loader2 className="animate-spin" /> : <Save />}Save settings
          </Button>
        </form>
        <p className="text-sm text-muted-foreground">
          Your container must stay running. Existing manual queue entries stay manual. Failed or
          interrupted attempts need Retry. Saved download schedules take priority over automatic
          starts; excluded projects are skipped.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={
              !!app.pending ||
              monitor.paused ||
              !monitor.active_count ||
              !app.state!.session.connected
            }
            onClick={() => app.action('/api/monitoring/check', {}, 'Monitoring check requested')}
          >
            <Activity />
            Check now
          </Button>
          <Button
            variant="destructive"
            disabled={!!app.pending || !monitor.count}
            onClick={() =>
              app.action(
                '/api/monitoring/clear',
                {},
                'All projects unmonitored; files and queue retained',
              )
            }
          >
            Unmonitor all
          </Button>
        </div>
      </div>
    </FormSheet>
  )
}
