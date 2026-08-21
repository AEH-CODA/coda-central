import { useEffect, useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { LoadingState } from '@/components/ui/LoadingState'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { SampleDataTable } from '@/components/query/SampleDataTable'
import { FullResultsTable } from '@/components/requests/FullResultsTable'
import { StatusBadge } from '@/components/requests/StatusBadge'
import { api, AuthError } from '@/lib/api'

const inputClass =
  'w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20'

export function AdminRequestDetailModal({ requestId, onClose, onAuthError, onDecided }) {
  const [request, setRequest] = useState(null)
  const [state, setState] = useState('loading')
  const [error, setError] = useState(null)
  const [reviewMode, setReviewMode] = useState(null) // null | 'confirmApprove' | 'reject'
  const [rejectReason, setRejectReason] = useState('')
  const [deciding, setDeciding] = useState(false)
  const [decideError, setDecideError] = useState(null)

  useEffect(() => {
    if (!requestId) return
    let cancelled = false

    setState('loading')
    setError(null)
    setReviewMode(null)
    setRejectReason('')
    setDecideError(null)

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

  async function handleApprove() {
    setDeciding(true)
    setDecideError(null)
    try {
      const response = await api.post(`/datasets/access-requests/${requestId}/approve`)
      if (!response.ok) throw new Error('Failed to approve request')
      onDecided()
      onClose()
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthError(err)
        return
      }
      setDecideError(err.message)
    } finally {
      setDeciding(false)
    }
  }

  async function handleReject(event) {
    event.preventDefault()
    setDeciding(true)
    setDecideError(null)
    try {
      const response = await api.post(`/datasets/access-requests/${requestId}/reject`, {
        action: 'reject',
        review_reason: rejectReason || null,
      })
      if (!response.ok) throw new Error('Failed to reject request')
      onDecided()
      onClose()
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthError(err)
        return
      }
      setDecideError(err.message)
    } finally {
      setDeciding(false)
    }
  }

  return (
    <Modal
      open={Boolean(requestId)}
      onClose={onClose}
      title={request ? `${request.project_name} · ${request.user_name}` : 'Request Details'}
      maxWidthClass="max-w-3xl"
    >
      {state === 'loading' && <LoadingState label="Loading request…" />}
      {state === 'error' && <ErrorBanner message={error} />}

      {state === 'success' && request && (
        <div className="space-y-5">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-muted-foreground">
              Requested on {new Date(request.created_at).toLocaleString()}
            </p>
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

          <Section title="Request Reason">
            <p className="text-sm text-foreground">{request.reason}</p>
          </Section>

          {request.supporting_doc_filename && (
            <Section title="Supporting Document">
              <p className="text-sm text-foreground">{request.supporting_doc_filename}</p>
            </Section>
          )}

          {request.data_preview && (
            <Section title="Data Preview (First 5 Rows)">
              <SampleDataTable columns={request.data_preview.columns} rows={request.data_preview.sample_rows} />
            </Section>
          )}

          {/* Unlike the requester's own view, the admin sees full results at
              every status — they need them to make the approve/reject call,
              not just after the fact. */}
          <Section title="Full Dataset Results">
            <FullResultsTable results={request.full_results} />
          </Section>

          {request.status !== 'pending' && (
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

          {request.status === 'pending' && (
            <Section title="Your Decision">
              {decideError && <ErrorBanner message={decideError} />}

              {reviewMode === 'reject' ? (
                <form onSubmit={handleReject} className="space-y-3">
                  <textarea
                    value={rejectReason}
                    onChange={(event) => setRejectReason(event.target.value)}
                    rows={3}
                    placeholder="Optional: explain why you're rejecting this request"
                    className={inputClass}
                  />
                  <div className="flex gap-2">
                    <Button type="submit" variant="destructive" disabled={deciding}>
                      {deciding ? 'Rejecting…' : 'Confirm Rejection'}
                    </Button>
                    <Button type="button" variant="secondary" onClick={() => setReviewMode(null)}>
                      Cancel
                    </Button>
                  </div>
                </form>
              ) : reviewMode === 'confirmApprove' ? (
                <div className="space-y-3">
                  <p className="text-sm text-foreground">
                    This will grant {request.user_name} access to the full dataset and notify them.
                  </p>
                  <div className="flex gap-2">
                    <Button onClick={handleApprove} disabled={deciding}>
                      {deciding ? 'Approving…' : 'Confirm Approve'}
                    </Button>
                    <Button variant="secondary" onClick={() => setReviewMode(null)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex gap-2">
                  <Button onClick={() => setReviewMode('confirmApprove')}>Approve Access</Button>
                  <Button variant="destructive" onClick={() => setReviewMode('reject')}>
                    Reject Request
                  </Button>
                </div>
              )}
            </Section>
          )}
        </div>
      )}
    </Modal>
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
