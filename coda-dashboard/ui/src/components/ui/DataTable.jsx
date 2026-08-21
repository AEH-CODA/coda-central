/**
 * Generic table shell shared by every results grid in the app (Sample Data
 * now; My Data Requests / Data Access Requests results later). Column header
 * cells and the footer are built as extension points so sorting and
 * pagination can be added later without restructuring callers.
 */
export function DataTable({ columns, rows, rowKey, emptyMessage = 'No data available', footer }) {
  if (!rows || rows.length === 0) {
    return (
      <div className="rounded-md border border-border bg-surface p-6 text-center text-sm text-muted-foreground">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-md border border-border bg-surface">
      <table className="w-full min-w-max border-collapse text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/40">
            {columns.map((col) => (
              <th
                key={col.key}
                className="whitespace-nowrap px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
              >
                {/* trailing span reserved for a future sort caret */}
                <span className="inline-flex items-center gap-1">{col.header}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={rowKey ? rowKey(row, index) : index} className="h-9 border-b border-border last:border-0 hover:bg-muted/40">
              {columns.map((col) => (
                <td key={col.key} className="whitespace-nowrap px-3 py-2 text-foreground">
                  {col.render ? col.render(row) : (row[col.key] ?? '-')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {/* reserved for a future pagination control */}
      {footer && <div className="border-t border-border px-3 py-2">{footer}</div>}
    </div>
  )
}
