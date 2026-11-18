import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Trash2 } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { DataTable } from '@/components/ui/DataTable'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { LoadingState } from '@/components/ui/LoadingState'
import { JobStatusBadge } from '@/components/oct/JobStatusBadge'
import { UploadDropzone } from '@/components/oct/UploadDropzone'
import { useAuthErrorHandler } from '@/components/oct/useOctHelpers'
import { useAuth } from '@/hooks/useAuth'
import { ACTIVE_STATUSES, formatNl, inference, uploadScan } from '@/lib/inference'

const POLL_MS = 2000

export function OctAnalysisPage() {
  const navigate = useNavigate()
  const handleAuthError = useAuthErrorHandler()
  const { isAdmin } = useAuth()

  const [models, setModels] = useState([])
  const [modelRef, setModelRef] = useState('')
  const [jobs, setJobs] = useState([])
  const [state, setState] = useState('loading')
  const [loadError, setLoadError] = useState(null)
  const [uploadError, setUploadError] = useState(null)
  const [uploadProgress, setUploadProgress] = useState(null)
  const [showAll, setShowAll] = useState(false)

  const fail = useCallback(
    (err, setter) => {
      if (!handleAuthError(err)) setter(err.message)
    },
    [handleAuthError],
  )

  const loadJobs = useCallback(async () => {
    try {
      const data = await inference.jobs({ all: showAll })
      setJobs(data.items ?? [])
      setState('success')
      setLoadError(null)
    } catch (err) {
      setState((s) => (s === 'loading' ? 'error' : s))
      fail(err, setLoadError)
    }
  }, [showAll, fail])

  useEffect(() => {
    inference
      .models()
      .then((list) => {
        setModels(list)
        setModelRef((current) => current || list[0]?.ref || '')
      })
      .catch((err) => fail(err, setLoadError))
  }, [fail])

  useEffect(() => {
    loadJobs()
  }, [loadJobs])

  // poll while anything is queued or running
  const hasActive = jobs.some((j) => ACTIVE_STATUSES.includes(j.status))
  useEffect(() => {
    if (!hasActive) return undefined
    const t = setInterval(loadJobs, POLL_MS)
    return () => clearInterval(t)
  }, [hasActive, loadJobs])

  async function handleFile(file) {
    setUploadError(null)
    setUploadProgress(0)
    try {
      await uploadScan(file, modelRef, setUploadProgress)
      await loadJobs()
    } catch (err) {
      fail(err, setUploadError)
    } finally {
      setUploadProgress(null)
    }
  }

  async function handleDelete(job) {
    const what = job.status === 'running' ? 'Cancel and delete' : 'Delete'
    if (!window.confirm(`${what} the analysis of "${job.filename}"? Its results will be removed.`)) return
    try {
      await inference.remove(job.id)
      setJobs((list) => list.filter((j) => j.id !== job.id))
    } catch (err) {
      fail(err, setLoadError)
    }
  }

  const model = models.find((m) => m.ref === modelRef)
  const classes = models[0]?.classes ?? [
    { name: 'IRF', color: '#E53935' },
    { name: 'SRF', color: '#FBC02D' },
    { name: 'PED', color: '#1E88E5' },
  ]

  const columns = [
    {
      key: 'filename',
      header: 'File',
      render: (j) => (
        <span className="inline-block max-w-56 truncate align-bottom font-medium" title={j.filename}>
          {j.filename}
        </span>
      ),
    },
    { key: 'laterality', header: 'Eye', render: (j) => j.laterality ?? '–' },
    { key: 'n_bscans', header: 'B-scans', render: (j) => j.n_bscans ?? '–' },
    { key: 'model', header: 'Model', render: (j) => <span className="text-xs text-muted-foreground">{j.model.version}</span> },
    { key: 'status', header: 'Status', render: (j) => <JobStatusBadge job={j} /> },
    { key: 'created', header: 'Uploaded', render: (j) => new Date(j.created_at).toLocaleString() },
    ...classes.map((c) => ({
      key: c.name,
      header: (
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: c.color }} />
          {c.name} nL
        </span>
      ),
      render: (j) => <span className="tabular-nums">{j.total_nl ? formatNl(j.total_nl[c.name]) : '–'}</span>,
    })),
    {
      key: 'actions',
      header: '',
      render: (j) => (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            handleDelete(j)
          }}
          aria-label={`Delete ${j.filename}`}
          title="Delete"
          className="cursor-pointer rounded-sm p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
        >
          <Trash2 size={16} />
        </button>
      ),
    },
  ]

  // DataTable has no row click; wrap cells so the whole row opens the report for finished jobs
  const clickable = columns.map((col) =>
    col.key === 'actions'
      ? col
      : {
          ...col,
          render: (j) => {
            const content = col.render ? col.render(j) : j[col.key]
            if (j.status !== 'succeeded') return <span title={j.error?.message ?? undefined}>{content}</span>
            return (
              <button
                type="button"
                className="cursor-pointer text-left hover:text-primary"
                onClick={() => navigate(`/oct-analysis/${j.id}`)}
              >
                {content}
              </button>
            )
          },
        },
  )

  const failed = jobs.filter((j) => j.status === 'failed')

  return (
    <div>
      <PageHeader
        title="OCT Fluid Analysis"
        subtitle="Segment intraretinal fluid (IRF), subretinal fluid (SRF) and pigment epithelial detachment (PED) in an OCT volume and measure their volumes."
      />

      <section className="mb-8 rounded-md border border-border bg-surface p-4 shadow-sm">
        {models.length > 1 && (
          <label className="mb-3 flex items-center gap-2 text-sm">
            <span className="font-medium text-foreground">Model</span>
            <select
              value={modelRef}
              onChange={(e) => setModelRef(e.target.value)}
              className="rounded-sm border border-border bg-surface px-2 py-1.5 text-sm"
            >
              {models.map((m) => (
                <option key={m.ref} value={m.ref}>
                  {m.display_name} ({m.version})
                </option>
              ))}
            </select>
          </label>
        )}
        <ErrorBanner message={uploadError} />
        <UploadDropzone onFile={handleFile} disabled={uploadProgress !== null || !modelRef} progress={uploadProgress} />
        {model && (
          <p className="mt-2 text-xs text-muted-foreground">
            {model.display_name}. Supported devices: {model.supported_manufacturers.join(', ')}{' '}
            {model.supported_models.join(', ')}. Research use only. Avoid patient names in file names.
          </p>
        )}
      </section>

      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-foreground">Analyses</h2>
        {isAdmin && (
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
            Show all users
          </label>
        )}
      </div>

      <ErrorBanner message={loadError} />
      {state === 'loading' && <LoadingState label="Loading analyses…" />}
      {state === 'success' && (
        <DataTable
          columns={clickable}
          rows={jobs}
          rowKey={(j) => j.id}
          emptyMessage="No analyses yet. Upload an OCT volume above to start."
        />
      )}
      {failed.length > 0 && (
        <div className="mt-3 space-y-1 text-xs text-muted-foreground">
          {failed.slice(0, 5).map((j) => (
            <p key={j.id}>
              <span className="font-medium text-destructive">{j.filename}:</span> {j.error?.message}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}
