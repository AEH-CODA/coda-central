import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { SavedDatasetCard } from '@/components/datasets/SavedDatasetCard'
import { SavedDatasetDetailModal } from '@/components/datasets/SavedDatasetDetailModal'
import { LoadingState } from '@/components/ui/LoadingState'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { useAuth } from '@/hooks/useAuth'
import { api, AuthError } from '@/lib/api'

export function SavedDatasetsPage() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  const [datasets, setDatasets] = useState([])
  const [state, setState] = useState('loading')
  const [error, setError] = useState(null)
  const [selectedDatasetId, setSelectedDatasetId] = useState(null)

  function handleAuthError(err) {
    window.alert(err.message)
    logout()
    navigate('/login', { replace: true })
  }

  const load = useCallback(async () => {
    setState('loading')
    setError(null)
    try {
      const response = await api.get('/datasets?skip=0&limit=100')
      if (!response.ok) throw new Error('Failed to load saved datasets')
      const data = await response.json()
      setDatasets(data.datasets ?? [])
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
    load()
  }, [load])

  return (
    <div>
      <PageHeader title="Saved Datasets" subtitle="Datasets you've saved from your queries" />

      {state === 'loading' && <LoadingState label="Loading your saved datasets…" />}
      {state === 'error' && <ErrorBanner message={error} />}

      {state === 'success' && datasets.length === 0 && (
        <p className="rounded-md border border-border bg-surface p-6 text-center text-sm text-muted-foreground">
          You haven't saved any datasets yet. Run a query and click "Save Dataset" to keep it here.
        </p>
      )}

      {state === 'success' && datasets.length > 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {datasets.map((dataset) => (
            <SavedDatasetCard key={dataset.id} dataset={dataset} onView={setSelectedDatasetId} />
          ))}
        </div>
      )}

      <SavedDatasetDetailModal
        datasetId={selectedDatasetId}
        onClose={() => setSelectedDatasetId(null)}
        onAuthError={handleAuthError}
        onChanged={load}
      />
    </div>
  )
}
