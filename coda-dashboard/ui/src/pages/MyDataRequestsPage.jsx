import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { FilterTabs } from '@/components/requests/FilterTabs'
import { RequestCard } from '@/components/requests/RequestCard'
import { RequestDetailModal } from '@/components/requests/RequestDetailModal'
import { LoadingState } from '@/components/ui/LoadingState'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { useAuth } from '@/hooks/useAuth'
import { api, AuthError } from '@/lib/api'

export function MyDataRequestsPage() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  const [requests, setRequests] = useState([])
  const [state, setState] = useState('loading')
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('all')
  const [selectedRequestId, setSelectedRequestId] = useState(null)

  function handleAuthError(err) {
    window.alert(err.message)
    logout()
    navigate('/login', { replace: true })
  }

  useEffect(() => {
    let cancelled = false

    async function load() {
      setState('loading')
      setError(null)
      try {
        const response = await api.get('/datasets/access-requests/user/history?skip=0&limit=100')
        if (!response.ok) throw new Error('Failed to load requests')
        const data = await response.json()
        if (!cancelled) {
          setRequests(data.requests ?? [])
          setState('success')
        }
      } catch (err) {
        if (cancelled) return
        if (err instanceof AuthError) {
          handleAuthError(err)
          return
        }
        setState('error')
        setError(err.message)
      }
    }

    load()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const counts = useMemo(
    () => ({
      all: requests.length,
      pending: requests.filter((request) => request.status === 'pending').length,
      approved: requests.filter((request) => request.status === 'approved').length,
      rejected: requests.filter((request) => request.status === 'rejected').length,
    }),
    [requests],
  )

  const filteredRequests = filter === 'all' ? requests : requests.filter((request) => request.status === filter)

  return (
    <div>
      <PageHeader title="My Data Requests" subtitle="Track and manage your data access requests" />

      <FilterTabs
        tabs={[
          { value: 'all', label: 'All', count: counts.all },
          { value: 'pending', label: 'Pending', count: counts.pending },
          { value: 'approved', label: 'Approved', count: counts.approved },
          { value: 'rejected', label: 'Rejected', count: counts.rejected },
        ]}
        active={filter}
        onChange={setFilter}
      />

      {state === 'loading' && <LoadingState label="Loading your data requests…" />}
      {state === 'error' && <ErrorBanner message={error} />}

      {state === 'success' && filteredRequests.length === 0 && (
        <p className="rounded-md border border-border bg-surface p-6 text-center text-sm text-muted-foreground">
          You have no data access requests in this category yet.
        </p>
      )}

      {state === 'success' && filteredRequests.length > 0 && (
        <div className="space-y-3">
          {filteredRequests.map((request) => (
            <RequestCard key={request.id} request={request} onView={setSelectedRequestId} />
          ))}
        </div>
      )}

      <RequestDetailModal
        requestId={selectedRequestId}
        onClose={() => setSelectedRequestId(null)}
        onAuthError={handleAuthError}
      />
    </div>
  )
}
