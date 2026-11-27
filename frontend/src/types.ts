export type Project = {
  id: string
  title: string
  url: string
  scanned: boolean
  error?: string | null
  excluded?: boolean
  restoring?: boolean
  count: number | null
  remaining: number | null
  complete: number
  qualities: number[]
  preferred: number
  section_count: number
  selected_section_count: number
  monitored?: boolean
  monitor_last_checked?: number | null
  monitor_error?: string | null
}
export type Job = {
  id?: string
  kind: string
  running: boolean
  done: number
  total: number
  message: string
  error: string | null
  source?: string
  project_id?: string
  project_ids?: string[]
}
export type QueueItem = {
  id: string
  group_id: string
  filename: string
  project: string
  status: 'queued' | 'downloading' | 'complete' | 'failed' | 'interrupted'
  bytes: number
  total: number | null
  message: string
  destination?: string
}
export type QueueGroup = {
  id: string
  title: string
  count: number
  loaded: boolean
  page: number
  complete: number
  failed: number
}
export type Monitoring = {
  paused: boolean
  interval_minutes: number
  count: number
  active_count: number
  next_check: number | null
  last_run: number | null
  message: string
}
export type AppState = {
  projects: Project[]
  project_updates: Project[]
  library_version: number
  app_version: string
  job: Job
  download_job: Job
  downloads: QueueItem[]
  download_groups: QueueGroup[]
  download_page_total: number
  download_group_total: number
  download_filtered_total: number
  download_page: number
  download_total: number
  pending_count: number
  schedule: { starts_at: number | null; message: string }
  monitoring: Monitoring
  browser_active: boolean
  session: { saved: boolean; connected: boolean; status: string; message: string }
  transfer_settings: { version: number; speed_limit_kbps: number; parallel_downloads: number }
  default_quality: number
  output: string
}
export type StateResponse = Omit<AppState, 'projects'> & { projects: Project[] | null }
export type DetailFile = {
  key: string
  filename: string
  selected: number
  qualities: number[]
  section_id?: string
}
export type DetailSection = {
  id: string
  title: string
  enabled: boolean
  count: number
  preferred: number
  qualities: number[]
}
export type ProjectDetail = {
  id: string
  title: string
  files: DetailFile[]
  sections: DetailSection[]
  choices: Record<string, number>
}
export type QueueQuery = {
  page: number
  pageSize: number
  groupSize: number
  filter: string
  search: string
  groups: Record<string, number>
}
export type ActionData = Record<string, unknown>
