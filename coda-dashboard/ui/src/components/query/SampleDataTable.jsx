import { DataTable } from '@/components/ui/DataTable'
import { ScanIdValue } from './ScanIdValue'

export function SampleDataTable({ columns, rows }) {
  const tableColumns = columns.map((column) => ({
    key: column.name,
    header: column.name,
    render: (row) => <ScanIdValue columnName={column.name} value={row[column.name]} />,
  }))

  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Sample Data (First 5 Rows)
      </h3>
      <DataTable columns={tableColumns} rows={rows} rowKey={(_, index) => index} emptyMessage="No sample data available" />
    </div>
  )
}
