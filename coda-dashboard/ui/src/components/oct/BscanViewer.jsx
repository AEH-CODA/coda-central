import { useEffect } from 'react'
import { ChevronLeft, ChevronRight, Columns2, Square } from 'lucide-react'
import { useAuthedImage } from './useOctHelpers'

/** Side-by-side (or single large) B-scan view, with/without segmentation, plus a strip of B-scans with fluid. */
export function BscanViewer({ jobId, bscans, classes, z, onChange, loadImage, layout, onLayout, showOverlay, onOverlay }) {
  const n = bscans.length
  const bscanUrl = useAuthedImage(loadImage, `/inference/jobs/${jobId}/bscan/${z}.png`)
  const overlayUrl = useAuthedImage(loadImage, `/inference/jobs/${jobId}/overlay/${z}.png`)

  // prefetch neighbours so stepping through feels instant
  useEffect(() => {
    for (const k of [z - 1, z + 1, z + 2]) {
      if (k >= 0 && k < n) {
        loadImage(`/inference/jobs/${jobId}/bscan/${k}.png`).catch(() => {})
        loadImage(`/inference/jobs/${jobId}/overlay/${k}.png`).catch(() => {})
      }
    }
  }, [z, n, jobId, loadImage])

  // arrow keys step through B-scans
  useEffect(() => {
    function onKey(e) {
      // a focused form control (including the slider) handles its own keys
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName) || e.altKey || e.ctrlKey || e.metaKey) return
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') onChange(Math.max(0, z - 1))
      else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') onChange(Math.min(n - 1, z + 1))
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [z, n, onChange])

  const current = bscans[z]
  const fluidArea = (b) => classes.reduce((s, c) => s + (b.area_mm2[c.name] ?? 0), 0)
  const maxArea = Math.max(1e-9, ...bscans.map(fluidArea))

  const plain = (
    <Panel title={`B-scan ${z + 1}/${n} without segmentation`}>
      {bscanUrl ? <img src={bscanUrl} alt={`B-scan ${z + 1}`} className="block w-full" /> : <Placeholder />}
    </Panel>
  )
  const segmented = (
    <Panel title={`B-scan ${z + 1}/${n} with segmentation`}>
      {bscanUrl ? (
        <div className="relative">
          <img src={bscanUrl} alt={`B-scan ${z + 1}`} className="block w-full" />
          {overlayUrl && showOverlay && (
            <img src={overlayUrl} alt="" aria-hidden className="pointer-events-none absolute inset-0 h-full w-full" />
          )}
        </div>
      ) : (
        <Placeholder />
      )}
    </Panel>
  )

  return (
    <section className="rounded-md border border-border bg-surface p-3 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1">
          <IconButton label="Previous B-scan" onClick={() => onChange(Math.max(0, z - 1))} disabled={z === 0}>
            <ChevronLeft size={16} />
          </IconButton>
          <IconButton label="Next B-scan" onClick={() => onChange(Math.min(n - 1, z + 1))} disabled={z === n - 1}>
            <ChevronRight size={16} />
          </IconButton>
        </div>
        <input
          type="range"
          min={0}
          max={n - 1}
          value={z}
          onChange={(e) => onChange(Number(e.target.value))}
          className="min-w-40 flex-1 accent-primary"
          aria-label="B-scan"
        />
        <span className="w-28 text-right text-sm tabular-nums text-muted-foreground">
          {z + 1} / {n} · {current.position_mm.toFixed(2)} mm
        </span>
        <div className="flex items-center gap-1">
          <IconButton label="Side by side" active={layout === 'split'} onClick={() => onLayout('split')}>
            <Columns2 size={16} />
          </IconButton>
          <IconButton label="Single large view" active={layout === 'single'} onClick={() => onLayout('single')}>
            <Square size={16} />
          </IconButton>
        </div>
        {layout === 'single' && (
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input type="checkbox" checked={showOverlay} onChange={(e) => onOverlay(e.target.checked)} />
            Segmentation
          </label>
        )}
      </div>

      {/* B-scan strip: bar height = total fluid area of each B-scan */}
      <div className="mb-3 flex h-8 items-end gap-px" aria-label="B-scans with fluid">
        {bscans.map((b, i) => {
          const area = fluidArea(b)
          return (
            <button
              key={i}
              type="button"
              title={`B-scan ${i + 1}: ${area.toFixed(3)} mm² fluid`}
              onClick={() => onChange(i)}
              className={`flex h-full flex-1 cursor-pointer items-end rounded-[1px] ${i === z ? 'bg-primary/20 ring-1 ring-primary' : 'bg-muted'}`}
            >
              <span
                className="block w-full rounded-[1px] bg-destructive/70"
                style={{ height: area > 0 ? `${Math.max(12, (area / maxArea) * 100)}%` : 0 }}
              />
            </button>
          )
        })}
      </div>

      {layout === 'split' ? (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {plain}
          {segmented}
        </div>
      ) : (
        segmented
      )}

      <div className="mt-3 flex flex-wrap gap-4 text-sm">
        {classes.map((c) => (
          <span key={c.name} className="inline-flex items-center gap-1.5 text-muted-foreground">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: c.color }} />
            {c.name}: <span className="font-semibold tabular-nums text-foreground">{(current.area_mm2[c.name] ?? 0).toFixed(3)}</span> mm²
          </span>
        ))}
      </div>
    </section>
  )
}

function Panel({ title, children }) {
  return (
    <figure>
      <figcaption className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</figcaption>
      <div className="overflow-hidden rounded-sm bg-black">{children}</div>
    </figure>
  )
}

function Placeholder() {
  return <div className="flex aspect-[3/2] items-center justify-center text-xs text-slate-400">Loading…</div>
}

function IconButton({ label, onClick, disabled, active, children }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-sm border transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
        active ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:bg-muted hover:text-foreground'
      }`}
    >
      {children}
    </button>
  )
}
