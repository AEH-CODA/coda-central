import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Filter } from 'lucide-react'

const BLANK_LABEL = '(Blank)'

/**
 * Excel AutoFilter-style column header dropdown: search box to narrow a long
 * value list, checkboxes to multi-select which values stay, "(Select All)"
 * and a one-click "Clear filter". Portaled to <body> and position:fixed so it
 * isn't clipped by the table's own overflow-x scroll container.
 */
export function ColumnFilterDropdown({ columnName, values, selected, onChange }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [position, setPosition] = useState(null)
  const triggerRef = useRef(null)
  const popoverRef = useRef(null)

  const isFiltered = selected.size < values.length

  useEffect(() => {
    if (!open) return

    function updatePosition() {
      const rect = triggerRef.current?.getBoundingClientRect()
      if (!rect) return
      setPosition({ top: rect.bottom + 4, left: rect.left })
    }
    updatePosition()

    function handleClickOutside(event) {
      if (popoverRef.current?.contains(event.target) || triggerRef.current?.contains(event.target)) return
      setOpen(false)
    }
    // Simplest robust option: close on scroll rather than re-tracking
    // position, since the trigger can scroll inside the table too.
    function handleScroll() {
      setOpen(false)
    }
    function handleKeyDown(event) {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', handleClickOutside)
    window.addEventListener('scroll', handleScroll, true)
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      window.removeEventListener('scroll', handleScroll, true)
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  const filteredValues = useMemo(() => {
    if (!search.trim()) return values
    const needle = search.trim().toLowerCase()
    return values.filter((value) => (value === null ? BLANK_LABEL : String(value)).toLowerCase().includes(needle))
  }, [values, search])

  const allFilteredSelected = filteredValues.length > 0 && filteredValues.every((value) => selected.has(value))

  function toggleOpen() {
    setOpen((prev) => !prev)
    setSearch('')
  }

  function toggleValue(value) {
    const next = new Set(selected)
    if (next.has(value)) next.delete(value)
    else next.add(value)
    onChange(next)
  }

  function toggleSelectAllFiltered() {
    const next = new Set(selected)
    if (allFilteredSelected) filteredValues.forEach((value) => next.delete(value))
    else filteredValues.forEach((value) => next.add(value))
    onChange(next)
  }

  function clearFilter() {
    onChange(new Set(values))
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={toggleOpen}
        aria-label={`Filter ${columnName}`}
        title={`Filter ${columnName}`}
        className={`flex h-5 w-5 shrink-0 cursor-pointer items-center justify-center rounded-sm normal-case tracking-normal transition-colors hover:bg-muted ${
          isFiltered ? 'text-primary' : 'text-muted-foreground'
        }`}
      >
        <Filter size={12} strokeWidth={isFiltered ? 2.5 : 1.8} fill={isFiltered ? 'currentColor' : 'none'} />
      </button>

      {open &&
        position &&
        createPortal(
          <div
            ref={popoverRef}
            style={{ position: 'fixed', top: position.top, left: position.left }}
            className="z-50 w-64 rounded-md border border-border bg-surface p-2 text-left normal-case tracking-normal shadow-lg"
          >
            <input
              type="text"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search values…"
              autoFocus
              className="mb-2 w-full rounded-sm border border-border bg-background px-2 py-1 text-xs text-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            />

            <label className="mb-1 flex cursor-pointer items-center gap-2 border-b border-border px-1 pb-2 text-xs font-medium text-foreground">
              <input type="checkbox" checked={allFilteredSelected} onChange={toggleSelectAllFiltered} />
              (Select All)
            </label>

            <div className="max-h-48 overflow-y-auto">
              {filteredValues.length === 0 && (
                <p className="px-1 py-2 text-xs text-muted-foreground">No matching values</p>
              )}
              {filteredValues.map((value) => (
                <label
                  key={value === null ? '__blank__' : value}
                  className="flex cursor-pointer items-center gap-2 rounded-sm px-1 py-1 text-xs font-normal text-foreground hover:bg-muted"
                >
                  <input type="checkbox" checked={selected.has(value)} onChange={() => toggleValue(value)} />
                  <span className="truncate">{value === null ? BLANK_LABEL : String(value)}</span>
                </label>
              ))}
            </div>

            {isFiltered && (
              <button
                type="button"
                onClick={clearFilter}
                className="mt-2 w-full cursor-pointer border-t border-border pt-2 text-left text-xs font-medium text-primary hover:underline"
              >
                Clear filter
              </button>
            )}
          </div>,
          document.body,
        )}
    </>
  )
}
