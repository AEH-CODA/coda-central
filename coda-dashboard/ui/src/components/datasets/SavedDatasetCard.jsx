import { Button } from '@/components/ui/Button'

export function SavedDatasetCard({ dataset, onView }) {
  const createdDate = new Date(dataset.created_at).toLocaleDateString()
  const queryPreview = dataset.nl_query.length > 90 ? `${dataset.nl_query.slice(0, 90)}…` : dataset.nl_query

  return (
    <div className="rounded-md border border-border bg-surface p-4 shadow-sm">
      <div className="mb-2">
        <p className="truncate text-sm font-semibold text-foreground">{dataset.name}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">Saved on {createdDate}</p>
      </div>

      {dataset.description && <p className="mb-2 line-clamp-2 text-sm text-muted-foreground">{dataset.description}</p>}

      <p className="mb-3 truncate rounded-sm bg-muted px-2 py-1 text-xs text-muted-foreground">{queryPreview}</p>

      <div className="flex justify-end">
        <Button variant="secondary" onClick={() => onView(dataset.id)}>
          View & Manage
        </Button>
      </div>
    </div>
  )
}
