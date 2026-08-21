import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Filter } from 'lucide-react'

const BLANK_LABEL = '(Blank)'
const VIEWPORT_MARGIN = 8

/**
 * Excel AutoFilter-style column header dropdown. Checkbox changes only edit a
 * local draft — nothing is applied to the table until "OK" is clicked
 * (mirroring Excel's own filter dropdown), so toggling "(Select All)" or a
 * handful of values doesn't yank the table around after every click.
 * "Cancel"/outside-click/Escape discard the draft; "Clear filter" is the one
 * action that applies immediately, since it's already unambiguous.
 * Portaled to <body> and position:fixed so it isn't clipped by the table's
 * own overflow-x scroll container. Position is measured against the popover's
 * actual rendered size and flipped above the trigger (or clamped
 * horizontally) whenever it would otherwise run off the edge of the screen —
 * columns near the bottom/edge of the table would otherwise push the dropdown
 * (and its OK/Cancel buttons) off-screen.
 */
export function ColumnFilterDropdown({ columnName, values, selected, onChange }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [position, setPosition] = useState(null)
  const [draftSelected, setDraftSelected] = useState(selected)
  const triggerRef = useRef(null)
  const popoverRef = useRef(null)

  const isFiltered = selected.size < values.length

  // Pass 1: place the popover below the trigger as a first guess and render
  // it (invisibly, until pass 2 confirms/corrects the position) so its real
  // size can be measured.
  useLayoutEffect(() => {
    if (!open) {
      setPosition(null)
      return
    }
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    setPosition({ top: rect.bottom + 4, left: rect.left, ready: false })
  }, [open])

  // Pass 2: now that the popover has actually rendered, measure it and flip
  // above the trigger / clamp horizontally if it would overflow the
  // viewport. Runs before paint, so there's no visible flicker.
  useLayoutEffect(() => {
    if (!open || !position || position.ready) return
    const popoverEl = popoverRef.current
    const triggerRect = triggerRef.current?.getBoundingClientRect()
    if (!popoverEl || !triggerRect) return

    const popoverRect = popoverEl.getBoundingClientRect()
    const viewportHeight = window.innerHeight
    const viewportWidth = window.innerWidth

    let top = triggerRect.bottom + 4
    if (top + popoverRect.height + VIEWPORT_MARGIN > viewportHeight) {
      const above = triggerRect.top - popoverRect.height - 4
      top = above >= VIEWPORT_MARGIN ? above : Math.max(VIEWPORT_MARGIN, viewportHeight - popoverRect.height - VIEWPORT_MARGIN)
    }

    let left = triggerRect.left
    if (left + popoverRect.width + VIEWPORT_MARGIN > viewportWidth) {
      left = Math.max(VIEWPORT_MARGIN, viewportWidth - popoverRect.width - VIEWPORT_MARGIN)
    }

    setPosition({ top, left, ready: true })
  }, [open, position])

  useEffect(() => {
    if (!open) return

    function handleClickOutside(event) {
      if (popoverRef.current?.contains(event.target) || triggerRef.current?.contains(event.target)) return
      setOpen(false)
    }
    // Scroll events fire on window during the capture phase for descendant
    // scrolls too (including the popover's own scrollable value list), so
    // ignore anything that originated inside the popover — otherwise
    // scrolling the value list itself closes the dropdown.
    function handleScroll(event) {
      if (popoverRef.current?.contains(event.target)) return
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

  const allFilteredSelected = filteredValues.length > 0 && filteredValues.every((value) => draftSelected.has(value))

  function handleTriggerClick() {
    if (open) {
      setOpen(false)
      return
    }
    setDraftSelected(new Set(selected))
    setSearch('')
    setOpen(true)
  }

  function toggleValue(value) {
    setDraftSelected((prev) => {
      const next = new Set(prev)
      if (next.has(value)) next.delete(value)
      else next.add(value)
      return next
    })
  }

  function toggleSelectAllFiltered() {
    setDraftSelected((prev) => {
      const next = new Set(prev)
      if (allFilteredSelected) filteredValues.forEach((value) => next.delete(value))
      else filteredValues.forEach((value) => next.add(value))
      return next
    })
  }

  function applyAndClose() {
    onChange(draftSelected)
    setOpen(false)
  }

  function clearFilter() {
    onChange(new Set(values))
    setOpen(false)
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={handleTriggerClick}
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
            style={{
              position: 'fixed',
              top: position.top,
              left: position.left,
              visibility: position.ready ? 'visible' : 'hidden',
            }}
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
                  <input type="checkbox" checked={draftSelected.has(value)} onChange={() => toggleValue(value)} />
                  <span className="truncate">{value === null ? BLANK_LABEL : String(value)}</span>
                </label>
              ))}
            </div>

            <div className="mt-2 flex items-center justify-between gap-2 border-t border-border pt-2">
              <button
                type="button"
                onClick={clearFilter}
                className="cursor-pointer text-xs font-medium text-primary hover:underline"
              >
                Clear filter
              </button>
              <div className="flex gap-1.5">
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="cursor-pointer rounded-sm border border-border px-2 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={applyAndClose}
                  className="cursor-pointer rounded-sm bg-primary px-2 py-1 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
                >
                  OK
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  )
}
