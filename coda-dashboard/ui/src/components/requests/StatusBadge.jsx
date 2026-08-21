const styles = {
  pending: 'bg-warning/15 text-warning',
  approved: 'bg-success/15 text-success',
  rejected: 'bg-destructive/15 text-destructive',
}

export function StatusBadge({ status }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-sm px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${
        styles[status] ?? 'bg-muted text-muted-foreground'
      }`}
    >
      {status}
    </span>
  )
}
