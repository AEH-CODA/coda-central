import { ColumnCard } from './ColumnCard'

export function ColumnInformation({ columns, rowCount }) {
  return (
    <div className="mb-6">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">Column Information</h3>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {columns.map((column) => (
          <ColumnCard key={column.name} column={column} rowCount={rowCount} />
        ))}
      </div>
    </div>
  )
}
