import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { FilterTabs } from '@/components/requests/FilterTabs'
import { StatusBadge } from '@/components/requests/StatusBadge'
import { Button } from '@/components/ui/Button'
import { LoadingState } from '@/components/ui/LoadingState'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { AdminRequestDetailModal } from '@/components/admin/AdminRequestDetailModal'
import { useAuth } from '@/hooks/useAuth'
import { api, AuthError } from '@/lib/api'

export function DataAccessRequestsPage() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  const [requests, setRequests] = useState([])
  const [state, setState] = useState('loading')
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('pending')
  const [selectedRequestId, setSelectedRequestId] = useState(null)

  function handleAuthError(err) {
    window.alert(err.message)
    logout()
    navigate('/login', { replace: true })
  }

  const loadRequests = useCallback(async () => {
    setState('loading')
    setError(null)
    try {
      const response = await api.get('/datasets/access-requests/all?skip=0&limit=100')
      if (!response.ok) throw new Error('Failed to load requests')
      const data = await response.json()
      setRequests(data.requests ?? [])
      setState('success')
    } catch (err) {
      if (err instanceof AuthError) {
        handleAuthError(err)
        return
      }
      setState('error')
      setError(err.message)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    loadRequests()
  }, [loadRequests])

  const counts = useMemo(
    () => ({
      pending: requests.filter((request) => request.status === 'pending').length,
      approved: requests.filter((request) => request.status === 'approved').length,
      rejected: requests.filter((request) => request.status === 'rejected').length,
    }),
    [requests],
  )

  const filteredRequests = requests.filter((request) => request.status === filter)

  return (
    <div>
      <PageHeader title="Data Access Requests" subtitle="Review and manage user requests for data access" />

      <div className="mb-4 flex items-center justify-between gap-3">
        <FilterTabs
          tabs={[
            { value: 'pending', label: 'Pending', count: counts.pending },
            { value: 'approved', label: 'Approved', count: counts.approved },
            { value: 'rejected', label: 'Rejected', count: counts.rejected },
          ]}
          active={filter}
          onChange={setFilter}
        />
        <Button variant="secondary" onClick={loadRequests}>
          Refresh
        </Button>
      </div>

      {state === 'loading' && <LoadingState label="Loading requests…" />}
      {state === 'error' && <ErrorBanner message={error} />}

      {state === 'success' && filteredRequests.length === 0 && (
        <p className="rounded-md border border-border bg-surface p-6 text-center text-sm text-muted-foreground">
          No requests found in this category.
        </p>
      )}

      {state === 'success' && filteredRequests.length > 0 && (
        <div className="space-y-3">
          {filteredRequests.map((request) => (
            <AdminRequestCard key={request.id} request={request} onView={setSelectedRequestId} />
          ))}
        </div>
      )}

      <AdminRequestDetailModal
        requestId={selectedRequestId}
        onClose={() => setSelectedRequestId(null)}
        onAuthError={handleAuthError}
        onDecided={loadRequests}
      />
    </div>
  )
}

function AdminRequestCard({ request, onView }) {
  const createdDate = new Date(request.created_at).toLocaleDateString()
  const preview = request.nl_query.length > 100 ? `${request.nl_query.slice(0, 100)}…` : request.nl_query

  return (
    <button
      type="button"
      onClick={() => onView(request.id)}
      className="w-full cursor-pointer rounded-md border border-border bg-surface p-4 text-left shadow-sm transition-colors hover:border-primary"
    >
      <div className="mb-2 flex items-start justify-between gap-3">
        <p className="text-sm font-semibold text-foreground">
          {request.project_name} · {request.user_name} · {createdDate}
        </p>
        <StatusBadge status={request.status} />
      </div>
      <p className="mb-2 truncate text-sm text-muted-foreground">{preview}</p>
      <p className="text-right text-xs font-medium text-primary">View Details →</p>
    </button>
  )
}
