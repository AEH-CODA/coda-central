import { useEffect, useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { LoadingState } from '@/components/ui/LoadingState'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { DatasetPreview } from '@/components/query/DatasetPreview'
import { StatusBadge } from './StatusBadge'
import { FullResultsTable } from './FullResultsTable'
import { api, AuthError } from '@/lib/api'
import { exportResultsAsCSV, exportResultsAsJSON } from '@/lib/exportResults'

export function RequestDetailModal({ requestId, onClose, onAuthError }) {
  const [request, setRequest] = useState(null)
  const [state, setState] = useState('loading')
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!requestId) return
    let cancelled = false

    setState('loading')
    setError(null)
    setRequest(null)

    api
      .get(`/datasets/access-requests/${requestId}`)
      .then(async (response) => {
        if (!response.ok) throw new Error('Failed to load request details')
        const data = await response.json()
        if (!cancelled) {
          setRequest(data)
          setState('success')
        }
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof AuthError) {
          onAuthError(err)
          return
        }
        setState('error')
        setError(err.message)
      })

    return () => {
      cancelled = true
    }
  }, [requestId, onAuthError])

  return (
    <Modal
      open={Boolean(requestId)}
      onClose={onClose}
      title={request ? request.project_name : 'Request Details'}
      maxWidthClass="max-w-3xl"
    >
      {state === 'loading' && <LoadingState label="Loading request…" />}
      {state === 'error' && <ErrorBanner message={error} />}
      {state === 'success' && request && <RequestDetailContent request={request} />}
    </Modal>
  )
}

function RequestDetailContent({ request }) {
  const isPending = request.status === 'pending'

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm text-muted-foreground">{request.user_name}</p>
          <p className="text-xs text-muted-foreground">Requested on {new Date(request.created_at).toLocaleString()}</p>
        </div>
        <StatusBadge status={request.status} />
      </div>

      <Section title="Natural Language Query">
        <p className="rounded-sm bg-muted p-2 text-sm text-foreground">{request.nl_query}</p>
      </Section>

      <Section title="SPARQL Query">
        <pre className="overflow-x-auto rounded-sm bg-muted p-2 font-mono text-xs text-foreground">
          {request.sparql_query}
        </pre>
      </Section>

      <Section title="Access Reason">
        <p className="text-sm text-foreground">{request.reason}</p>
      </Section>

      {request.supporting_doc_filename && (
        <Section title="Supporting Document">
          <p className="text-sm text-foreground">{request.supporting_doc_filename}</p>
        </Section>
      )}

      {request.data_preview && (
        <Section title="Data Preview">
          <DatasetPreview preview={request.data_preview} />
        </Section>
      )}

      {!isPending && (
        <Section title="Review History">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <ReviewRow label="Decision" value={request.status.toUpperCase()} />
            <ReviewRow
              label="Reviewed At"
              value={request.reviewed_at ? new Date(request.reviewed_at).toLocaleString() : 'N/A'}
            />
            <ReviewRow label="Reviewed By" value={request.reviewed_by_id ?? 'System'} />
            {request.status === 'rejected' && request.review_reason && (
              <ReviewRow label="Reason" value={request.review_reason} span />
            )}
          </dl>
        </Section>
      )}

      {request.status === 'approved' && request.full_results && (
        <Section title="Full Dataset Results">
          <FullResultsTable results={request.full_results} />
          <div className="mt-3 flex gap-2">
            <Button variant="secondary" onClick={() => exportResultsAsCSV(request)}>
              Export as CSV
            </Button>
            <Button variant="secondary" onClick={() => exportResultsAsJSON(request)}>
              Export as JSON
            </Button>
          </div>
        </Section>
      )}
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {children}
    </div>
  )
}

function ReviewRow({ label, value, span }) {
  return (
    <div className={span ? 'col-span-2' : undefined}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-foreground">{value}</dd>
    </div>
  )
}
