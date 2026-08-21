import { Hash, Calendar, Type, Fingerprint } from 'lucide-react'
import { DistributionChart } from './DistributionChart'

const typeIcon = { numeric: Hash, datetime: Calendar, categorical: Type, identifier: Fingerprint }

function formatNumber(value) {
  return value !== null && value !== undefined ? value.toFixed(2) : 'N/A'
}

export function ColumnCard({ column, rowCount }) {
  const Icon = typeIcon[column.dtype] ?? Type

  return (
    <div className="rounded-md border border-border bg-surface p-3 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <Icon size={16} strokeWidth={1.8} className="shrink-0 text-muted-foreground" />
        <span className="truncate text-sm font-semibold text-foreground">{column.name}</span>
        <span className="ml-auto shrink-0 rounded-sm bg-muted px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {column.dtype}
        </span>
      </div>

      <dl className="space-y-1 text-xs">
        <Row label="Unique" value={column.unique_values} />
        {column.missing_percentage > 0 && <Row label="Missing" value={`${column.missing_percentage.toFixed(2)}%`} />}

        {column.dtype === 'numeric' && (
          <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 border-t border-border pt-2">
            <Row label="Mean" value={formatNumber(column.mean)} />
            <Row label="Min" value={formatNumber(column.min)} />
            <Row label="Max" value={formatNumber(column.max)} />
            <Row label="Std Dev" value={formatNumber(column.std)} />
          </div>
        )}

        {column.dtype === 'datetime' && (
          <div className="mt-2 border-t border-border pt-2">
            <Row label="Date Range" value={`${column.min_date ?? 'N/A'} – ${column.max_date ?? 'N/A'}`} />
          </div>
        )}
      </dl>

      {(column.dtype === 'categorical' || column.dtype === 'identifier') && column.top_values && (
        <TopValues topValues={column.top_values} rowCount={rowCount} />
      )}

      {column.distribution && (
        <div className="mt-3">
          <DistributionChart column={column} />
        </div>
      )}
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium text-foreground">{value}</dd>
    </div>
  )
}

function TopValues({ topValues, rowCount }) {
  return (
    <div className="mt-3 space-y-1.5 border-t border-border pt-2">
      {Object.entries(topValues).map(([value, count]) => {
        const percentage = rowCount > 0 ? ((count / rowCount) * 100).toFixed(1) : '0'
        return (
          <div key={value} className="relative overflow-hidden rounded-sm bg-muted">
            <div className="absolute inset-y-0 left-0 bg-secondary/25" style={{ width: `${percentage}%` }} />
            <div className="relative flex items-center justify-between gap-2 px-2 py-1 text-xs">
              <span className="truncate text-foreground">{value}</span>
              <span className="shrink-0 text-muted-foreground">
                {count} ({percentage}%)
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
