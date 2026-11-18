import { LoaderCircle } from 'lucide-react'

const styles = {
  queued: 'bg-muted text-muted-foreground',
  running: 'bg-secondary/15 text-primary',
  succeeded: 'bg-success/15 text-success',
  failed: 'bg-destructive/15 text-destructive',
  cancelled: 'bg-muted text-muted-foreground',
}

const STAGE_LABELS = { queued: 'Queued', ingest: 'Reading', inference: 'Segmenting', quantify: 'Measuring', render: 'Rendering' }

export function JobStatusBadge({ job }) {
  const { status, progress, stage } = job
  const label = status === 'running' ? `${STAGE_LABELS[stage] ?? 'Running'} ${progress ?? 0}%` : status
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-sm px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${
        styles[status] ?? 'bg-muted text-muted-foreground'
      }`}
      title={job.error?.message ?? undefined}
    >
      {(status === 'running' || status === 'queued') && <LoaderCircle size={12} className="animate-spin" />}
      {label}
    </span>
  )
}
