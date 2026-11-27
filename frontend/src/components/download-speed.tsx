import { Gauge } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { bytes } from '@/lib/api'

export function DownloadSpeed({
  running,
  bytesPerSecond,
}: {
  running: boolean
  bytesPerSecond: number
}) {
  const speed = running && Number.isFinite(bytesPerSecond) ? Math.max(0, bytesPerSecond) : 0
  return (
    <Badge
      variant="secondary"
      className="gap-2 whitespace-nowrap py-1 tabular-nums"
      aria-label="Overall download speed"
      title="Combined video transfer rate across all downloads, averaged over the last 5 seconds. Updates about every 1.5 seconds while downloading."
    >
      <Gauge className="size-3.5" />
      <span>Overall speed</span>
      <span>{bytes(speed)}/s</span>
    </Badge>
  )
}
