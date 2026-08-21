import { Button } from '@/components/ui/Button'
import { StatusBadge } from './StatusBadge'

export function RequestCard({ request, onView }) {
  const createdDate = new Date(request.created_at).toLocaleDateString()
  const title = request.nl_query.length > 90 ? `${request.nl_query.slice(0, 90)}…` : request.nl_query

  return (
    <div className="rounded-md border border-border bg-surface p-4 shadow-sm">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-foreground">{title}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {request.project_name} · Requested on {createdDate}
          </p>
        </div>
        <StatusBadge status={request.status} />
      </div>
      <div className="flex justify-end">
        <Button variant="secondary" onClick={() => onView(request.id)}>
          {request.status === 'approved' ? 'View & Export' : 'View Details'}
        </Button>
      </div>
    </div>
  )
}
