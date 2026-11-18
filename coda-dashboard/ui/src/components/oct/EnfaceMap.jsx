import { useRef } from 'react'
import { useAuthedImage } from './useOctHelpers'

const MIN_ALPHA = 0.25 // must match ENFACE_MIN_ALPHA in inference-service/core/render.py

/**
 * En-face fluid height map for one class, drawn in scan millimetres:
 * x = lateral position along the B-scans, y = slow-axis position (row 0 = first B-scan).
 * The ETDRS grid and the current B-scan line are SVG so they move without re-rendering the image.
 * Clicking moves the ETDRS centre.
 */
export function EnfaceMap({ jobId, cls, field, diameters, center, bscanY, scaleMaxUm, loadImage, onPick, busy }) {
  const svgRef = useRef(null)
  const url = useAuthedImage(loadImage, `/inference/jobs/${jobId}/enface/${cls.name}.png`)
  const { width: w, height: h } = field
  const pad = 0.12 // mm, keeps the outline visible at the edges
  const rMax = Math.max(...diameters) / 2
  const rMin = Math.min(...diameters) / 2

  function handleClick(e) {
    if (!onPick || busy) return
    const svg = svgRef.current
    const pt = svg.createSVGPoint()
    pt.x = e.clientX
    pt.y = e.clientY
    const p = pt.matrixTransform(svg.getScreenCTM().inverse())
    if (p.x < 0 || p.x > w || p.y < 0 || p.y > h) return
    onPick({ x: Math.round(p.x * 1000) / 1000, z: Math.round(p.y * 1000) / 1000 })
  }

  const diag = [45, 135, 225, 315].map((deg) => {
    const a = (deg * Math.PI) / 180
    return {
      x1: center.x + rMin * Math.cos(a),
      y1: center.z + rMin * Math.sin(a),
      x2: center.x + rMax * Math.cos(a),
      y2: center.z + rMax * Math.sin(a),
    }
  })

  return (
    <figure className="rounded-md border border-border bg-surface p-3 shadow-sm">
      <figcaption className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
        <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: cls.color }} />
        En-face view ({cls.name})
      </figcaption>
      <div className="flex gap-3">
        <svg
          ref={svgRef}
          viewBox={`${-pad} ${-pad} ${w + 2 * pad} ${h + 2 * pad}`}
          className={`min-w-0 flex-1 rounded-sm bg-slate-950 ${onPick && !busy ? 'cursor-crosshair' : ''}`}
          onClick={handleClick}
          role="img"
          aria-label={`${cls.label} thickness map with ETDRS grid`}
        >
          <defs>
            <clipPath id={`clip-${cls.name}`}>
              <rect x={0} y={0} width={w} height={h} />
            </clipPath>
          </defs>
          {url && <image href={url} x={0} y={0} width={w} height={h} preserveAspectRatio="none" />}
          <rect x={0} y={0} width={w} height={h} fill="none" stroke="#475569" strokeWidth={0.03} />
          <g clipPath={`url(#clip-${cls.name})`} stroke="#ffffff" strokeOpacity={0.8} fill="none" strokeWidth={0.025}>
            {diameters.map((d) => (
              <circle key={d} cx={center.x} cy={center.z} r={d / 2} strokeDasharray={d === Math.min(...diameters) ? '0.06 0.05' : undefined} />
            ))}
            {diag.map((l, i) => (
              <line key={i} {...l} />
            ))}
            <line x1={center.x - 0.1} y1={center.z} x2={center.x + 0.1} y2={center.z} />
            <line x1={center.x} y1={center.z - 0.1} x2={center.x} y2={center.z + 0.1} />
          </g>
          {bscanY !== null && bscanY !== undefined && (
            <line x1={0} y1={bscanY} x2={w} y2={bscanY} stroke="#60a5fa" strokeWidth={0.03} strokeOpacity={0.9} />
          )}
        </svg>
        <div className="flex shrink-0 flex-col items-center justify-between py-1 text-[10px] text-muted-foreground">
          <span>{scaleMaxUm}µm</span>
          <div
            className="my-1 w-3 flex-1 rounded-sm border border-border"
            style={{
              background: `linear-gradient(to top, ${hexA(cls.color, MIN_ALPHA)}, ${hexA(cls.color, 1)}), #0f172a`,
            }}
          />
          <span>0µm</span>
        </div>
      </div>
    </figure>
  )
}

function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`
}
