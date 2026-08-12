import { Rows3, Columns3 } from 'lucide-react'
import { StatCard } from '@/components/ui/StatCard'

export function DatasetSummary({ summary }) {
  return (
    <div className="mb-6">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">Dataset Summary</h3>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard icon={Rows3} label="Row Count" value={summary.row_count.toLocaleString()} />
        <StatCard icon={Columns3} label="Column Count" value={summary.column_count} />
      </div>
    </div>
  )
}
