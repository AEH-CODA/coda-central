import { useMemo, useState } from 'react'
import { DataTable } from '@/components/ui/DataTable'
import { ScanIdValue } from '@/components/query/ScanIdValue'
import { ColumnFilterDropdown } from './ColumnFilterDropdown'

const PAGE_SIZE_OPTIONS = [10, 50, 100]
const DEFAULT_PAGE_SIZE = 50
// Stable references so useMemo below doesn't see a "new" empty array (and
// therefore recompute) on every render when results are absent/invalid.
const EMPTY_COLUMNS = []
const EMPTY_BINDINGS = []

export function FullResultsTable({ results }) {
  const columnNames = results?.head?.vars ?? EMPTY_COLUMNS
  const bindings = results?.results?.bindings ?? EMPTY_BINDINGS

  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [page, setPage] = useState(0)
  // { [columnName]: Set<value> } — a column only appears here while it has an
  // active (partial) selection; "select all" removes the entry entirely.
  const [columnFilters, setColumnFilters] = useState({})

  const columnValues = useMemo(() => {
    const map = {}
    for (const name of columnNames) {
      const set = new Set()
      for (const binding of bindings) {
        set.add(binding[name]?.value ?? null)
      }
      map[name] = Array.from(set).sort((a, b) => {
        if (a === null) return 1
        if (b === null) return -1
        return String(a).localeCompare(String(b), undefined, { numeric: true })
      })
    }
    return map
  }, [bindings, columnNames])

  const filteredBindings = useMemo(() => {
    const activeColumns = Object.keys(columnFilters)
    if (activeColumns.length === 0) return bindings
    return bindings.filter((binding) =>
      activeColumns.every((name) => columnFilters[name].has(binding[name]?.value ?? null)),
    )
  }, [bindings, columnFilters])

  if (!results?.head?.vars || !results?.results?.bindings) {
    return <p className="text-sm text-muted-foreground">No full results available</p>
  }

  const totalRows = filteredBindings.length
  const totalPages = Math.max(1, Math.ceil(totalRows / pageSize))
  const currentPage = Math.min(page, totalPages - 1)

  const start = currentPage * pageSize
  const end = Math.min(start + pageSize, totalRows)

  const rows = filteredBindings
    .slice(start, end)
    .map((binding) => Object.fromEntries(columnNames.map((name) => [name, binding[name]?.value ?? null])))

  const columns = columnNames.map((name) => ({
    key: name,
    header: (
      <>
        {name}
        <ColumnFilterDropdown
          columnName={name}
          values={columnValues[name]}
          selected={columnFilters[name] ?? new Set(columnValues[name])}
          onChange={(nextSet) => handleFilterChange(name, nextSet)}
        />
      </>
    ),
    render: (row) => <ScanIdValue columnName={name} value={row[name]} />,
  }))

  function handleFilterChange(name, nextSet) {
    setColumnFilters((prev) => {
      const next = { ...prev }
      if (nextSet.size === columnValues[name].length) delete next[name]
      else next[name] = nextSet
      return next
    })
    setPage(0)
  }

  function handlePageSizeChange(event) {
    setPageSize(Number(event.target.value))
    setPage(0)
  }

  function clearAllFilters() {
    setColumnFilters({})
    setPage(0)
  }

  const hasActiveFilters = Object.keys(columnFilters).length > 0

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          Showing {totalRows === 0 ? 0 : start + 1}–{end} of {totalRows.toLocaleString()} rows
          {hasActiveFilters && ` (filtered from ${bindings.length.toLocaleString()})`} × {columnNames.length} columns
        </p>
        <div className="flex items-center gap-3">
          {hasActiveFilters && (
            <button
              type="button"
              onClick={clearAllFilters}
              className="cursor-pointer text-xs font-medium text-primary hover:underline"
            >
              Clear all filters
            </button>
          )}
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            Rows per page
            <select
              value={pageSize}
              onChange={handlePageSizeChange}
              className="rounded-sm border border-border bg-surface px-2 py-1 text-xs text-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            >
              {PAGE_SIZE_OPTIONS.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(_, index) => start + index}
        emptyMessage={hasActiveFilters ? 'No rows match the current filters' : 'No data available'}
        footer={
          totalPages > 1 && (
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                Page {currentPage + 1} of {totalPages}
              </span>
              <div className="flex gap-1">
                <PageButton label="First page" symbol="<<" disabled={currentPage === 0} onClick={() => setPage(0)} />
                <PageButton
                  label="Previous page"
                  symbol="<"
                  disabled={currentPage === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                />
                <PageButton
                  label="Next page"
                  symbol=">"
                  disabled={currentPage >= totalPages - 1}
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                />
                <PageButton
                  label="Last page"
                  symbol=">>"
                  disabled={currentPage >= totalPages - 1}
                  onClick={() => setPage(totalPages - 1)}
                />
              </div>
            </div>
          )
        }
      />
    </div>
  )
}

function PageButton({ label, symbol, disabled, onClick }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="flex h-7 min-w-7 cursor-pointer items-center justify-center rounded-sm border border-border px-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
    >
      {symbol}
    </button>
  )
}
