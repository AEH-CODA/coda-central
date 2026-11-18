import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronLeft, Download, Info, RotateCcw, TriangleAlert } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { LoadingState } from '@/components/ui/LoadingState'
import { BscanViewer } from '@/components/oct/BscanViewer'
import { EnfaceMap } from '@/components/oct/EnfaceMap'
import { JobStatusBadge } from '@/components/oct/JobStatusBadge'
import { VolumeTable } from '@/components/oct/VolumeTable'
import { useAuthedImages, useAuthErrorHandler } from '@/components/oct/useOctHelpers'
import { ACTIVE_STATUSES, downloadFile, inference } from '@/lib/inference'

const POLL_MS = 2000

export function OctReportPage() {
  const { jobId } = useParams()
  const handleAuthError = useAuthErrorHandler()
  const loadImage = useAuthedImages()

  const [job, setJob] = useState(null)
  const [error, setError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [z, setZ] = useState(null)
  const [layout, setLayout] = useState('split')
  const [showOverlay, setShowOverlay] = useState(true)
  const [recentering, setRecentering] = useState(false)

  const fail = useCallback(
    (err, setter) => {
      if (!handleAuthError(err)) setter(err.message)
    },
    [handleAuthError],
  )

  const load = useCallback(async () => {
    try {
      setJob(await inference.job(jobId))
      setError(null)
    } catch (err) {
      fail(err, setError)
    }
  }, [jobId, fail])

  useEffect(() => {
    load()
  }, [load])

  const active = job && ACTIVE_STATUSES.includes(job.status)
  useEffect(() => {
    if (!active) return undefined
    const t = setInterval(load, POLL_MS)
    return () => clearInterval(t)
  }, [active, load])

  const result = job?.result
  // start on the B-scan with the most fluid
  useEffect(() => {
    if (!result || z !== null) return
    const names = result.classes.map((c) => c.name)
    let best = Math.floor(result.bscans.length / 2)
    let bestArea = 0
    result.bscans.forEach((b, i) => {
      const a = names.reduce((s, n) => s + (b.area_mm2[n] ?? 0), 0)
      if (a > bestArea) {
        bestArea = a
        best = i
      }
    })
    setZ(best)
  }, [result, z])

  async function recenter(centerMm) {
    setRecentering(true)
    setActionError(null)
    try {
      const update = await inference.setEtdrsCenter(jobId, centerMm)
      setJob((j) => ({ ...j, result: { ...j.result, ...update } }))
    } catch (err) {
      fail(err, setActionError)
    } finally {
      setRecentering(false)
    }
  }

  async function download(kind) {
    setActionError(null)
    const stem = job.filename.replace(/\.[^.]+$/, '')
    try {
      await downloadFile(`/inference/jobs/${jobId}/${kind}`, `${stem}_${kind}`)
    } catch (err) {
      fail(err, setActionError)
    }
  }

  const back = (
    <Link to="/oct-analysis" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary">
      <ChevronLeft size={16} /> All analyses
    </Link>
  )

  if (error && !job)
    return (
      <div>
        {back}
        <ErrorBanner message={error} />
      </div>
    )
  if (!job) return <LoadingState label="Loading report…" />

  if (job.status !== 'succeeded') {
    return (
      <div>
        {back}
        <div className="rounded-md border border-border bg-surface p-6 shadow-sm">
          <div className="mb-2 flex items-center gap-3">
            <h1 className="truncate text-xl font-bold text-foreground">{job.filename}</h1>
            <JobStatusBadge job={job} />
          </div>
          {active && (
            <>
              <p className="mb-3 text-sm text-muted-foreground">
                The analysis is {job.status === 'queued' ? 'waiting in the queue' : 'running'}. This page updates
                automatically.
              </p>
              <div className="h-1.5 w-full max-w-md overflow-hidden rounded-full bg-muted">
                <div className="h-full bg-primary transition-all" style={{ width: `${job.progress ?? 0}%` }} />
              </div>
            </>
          )}
          {job.status === 'failed' && <ErrorBanner message={job.error?.message ?? 'The analysis failed.'} />}
        </div>
      </div>
    )
  }

  const { scan, classes, volumes_nl: volumes, etdrs_center_mm: center, enface, model } = result
  const field = { width: scan.field_mm.width, height: scan.field_mm.height }
  const diameters = Object.keys(volumes)
    .filter((k) => k.startsWith('etdrs_'))
    .map((k) => parseFloat(k.slice(6)))
  const zi = z ?? 0
  const bscanY = scan.bscan_positions_mm?.[zi] ?? result.bscans[zi]?.position_mm
  const spacingUm = scan.spacing_mm.bscan ? Math.round(scan.spacing_mm.bscan * 1000) : null

  return (
    <div>
      {back}

      {/* header */}
      <header className="mb-4 rounded-md border border-border bg-surface p-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-foreground">Fluid Report ({scan.laterality ?? 'eye unknown'})</h1>
            <p className="mt-0.5 truncate text-sm text-muted-foreground" title={job.filename}>
              {job.filename}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => download('result.json')}>
              <Download size={16} /> result.json
            </Button>
            <Button variant="secondary" onClick={() => download('labels.npz')}>
              <Download size={16} /> labels.npz
            </Button>
          </div>
        </div>
        <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-[1fr_1.7fr_0.6fr_1fr]">
          <Meta label="Device" value={`${scan.manufacturer} / ${scan.device_model}`} />
          <Meta
            label="Scan pattern"
            value={`${field.width.toFixed(1)} mm × ${field.height.toFixed(1)} mm, ${scan.n_bscans} B-scans${
              spacingUm ? `, distance ${spacingUm} µm` : ''
            }`}
          />
          <Meta label="Study date" value={scan.study_date ?? '–'} />
          <Meta label="Model" value={`${model.id} ${model.version} · ${model.device}`} />
        </dl>
      </header>

      <ErrorBanner message={actionError} />

      {/* volumes */}
      <section className="mb-4">
        <VolumeTable classes={classes} volumes={volumes} coverage={result.etdrs_coverage} />
      </section>

      {/* en-face */}
      <section className="mb-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <Info size={14} />
            ETDRS centre {center.source === 'user' ? 'set manually' : 'at the scan centre'} ({center.x.toFixed(2)},{' '}
            {center.z.toFixed(2)}) mm. Click a map to move it. Top = B-scan 1; blue line = current B-scan.
          </p>
          <Button variant="secondary" onClick={() => recenter(null)} disabled={recentering || center.source !== 'user'}>
            <RotateCcw size={16} /> Reset to scan centre
          </Button>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {classes.map((cls) => (
            <EnfaceMap
              key={cls.name}
              jobId={jobId}
              cls={cls}
              field={field}
              diameters={diameters}
              center={center}
              bscanY={bscanY}
              scaleMaxUm={enface.scale_max_um}
              loadImage={loadImage}
              onPick={recenter}
              busy={recentering}
            />
          ))}
        </div>
      </section>

      {/* B-scans */}
      <section className="mb-4">
        <BscanViewer
          jobId={jobId}
          bscans={result.bscans}
          classes={classes}
          z={zi}
          onChange={setZ}
          loadImage={loadImage}
          layout={layout}
          onLayout={setLayout}
          showOverlay={showOverlay}
          onOverlay={setShowOverlay}
        />
      </section>

      {/* footer */}
      <footer className="space-y-2 rounded-md border border-border bg-surface p-4 text-sm">
        {result.warnings.map((w) => (
          <p key={w} className="flex gap-2 text-muted-foreground">
            <TriangleAlert size={16} className="mt-0.5 shrink-0 text-warning" />
            {w}
          </p>
        ))}
        <p className="font-semibold text-foreground">{result.disclaimer}</p>
      </footer>
    </div>
  )
}

function Meta({ label, value }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="truncate text-foreground" title={value}>
        {value}
      </dd>
    </div>
  )
}
