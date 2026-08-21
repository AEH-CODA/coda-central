import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { LoadingState } from '@/components/ui/LoadingState'
import { DatasetPreview } from '@/components/query/DatasetPreview'
import { RequestAccessModal } from '@/components/query/RequestAccessModal'
import { useAuth } from '@/hooks/useAuth'
import { api, AuthError } from '@/lib/api'

const STORAGE_QUERY_DATA = 'currentQueryData'
const STORAGE_LAST_QUERY = 'lastQuery'

export function QueryDataPage() {
  const { logout, hasFullDatasetAccess } = useAuth()
  const navigate = useNavigate()

  const [query, setQuery] = useState('')
  const [queryData, setQueryData] = useState(null)
  const [queryState, setQueryState] = useState('idle')
  const [queryError, setQueryError] = useState(null)
  const [previewState, setPreviewState] = useState('idle')
  const [previewError, setPreviewError] = useState(null)
  const [modalOpen, setModalOpen] = useState(false)

  // Restore the last session's results on mount, so a page refresh doesn't
  // lose an in-progress query — same behavior as the previous static app.
  useEffect(() => {
    const savedData = localStorage.getItem(STORAGE_QUERY_DATA)
    if (!savedData) return

    try {
      const parsed = JSON.parse(savedData)
      setQueryData(parsed)
      if (!parsed.error) setQueryState('success')
      if (parsed.preview_data) setPreviewState('success')

      const savedQuery = localStorage.getItem(STORAGE_LAST_QUERY)
      if (savedQuery) setQuery(savedQuery)
    } catch {
      // Corrupted or outdated session data — ignore and start fresh.
    }
  }, [])

  function persist(data, queryText) {
    localStorage.setItem(STORAGE_QUERY_DATA, JSON.stringify(data))
    localStorage.setItem(STORAGE_LAST_QUERY, queryText)
  }

  function handleAuthError(err) {
    window.alert(err.message)
    logout()
    navigate('/login', { replace: true })
  }

  async function loadPreview(baseQueryData, queryText) {
    if (!baseQueryData?.sparql) return

    setPreviewState('loading')
    setPreviewError(null)

    try {
      const response = await api.post('/datasets/preview', { sparql_query: baseQueryData.sparql })
      if (!response.ok) throw new Error(`Error: ${response.status} ${response.statusText}`)

      const preview = await response.json()
      const updated = { ...baseQueryData, preview_data: preview }
      setQueryData(updated)
      setPreviewState('success')
      persist(updated, queryText)
    } catch (err) {
      if (err instanceof AuthError) return handleAuthError(err)
      setPreviewState('error')
      setPreviewError(err.message)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!query.trim()) return

    setQueryState('loading')
    setQueryError(null)
    setPreviewState('idle')
    setPreviewError(null)

    try {
      const response = await api.post('/query', { query })
      const data = await response.json()

      if (data.error) {
        setQueryState('error')
        setQueryError(data.error)
        setQueryData(null)
        return
      }

      setQueryData(data)
      setQueryState('success')
      persist(data, query)
      await loadPreview(data, query)
    } catch (err) {
      if (err instanceof AuthError) return handleAuthError(err)
      setQueryState('error')
      setQueryError(err.message)
    }
  }

  const hasResults = Boolean(queryData && !queryData.error)

  return (
    <div>
      <PageHeader title="Query Data" subtitle="Discover insights with natural language queries" />

      <form onSubmit={handleSubmit} className="mb-8 flex gap-3">
        <div className="relative flex-1">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
            size={18}
            strokeWidth={1.8}
          />
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Enter natural language query (e.g., 'Show me all patients with diabetes')"
            className="w-full rounded-sm border border-border bg-surface py-2.5 pl-10 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
        </div>
        <Button type="submit" disabled={queryState === 'loading'}>
          {queryState === 'loading' ? 'Searching…' : 'Search'}
        </Button>
      </form>

      {queryState === 'error' && <ErrorBanner message={queryError} />}

      {hasResults && (
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-foreground">Results</h2>
            {!hasFullDatasetAccess && <Button onClick={() => setModalOpen(true)}>Request Access</Button>}
          </div>

          {!hasFullDatasetAccess && (
            <div className="mb-6 rounded-md border-l-4 border-accent bg-accent/10 p-3 text-sm text-foreground">
              <strong className="font-semibold">Preview Only:</strong> This is a preview of the data you queried. To
              access the full dataset, click "Request Access" above. Your request will be reviewed by an
              Admin or Data Manager.
            </div>
          )}

          {previewState === 'loading' && <LoadingState label="Loading preview…" />}
          {previewState === 'error' && <ErrorBanner message={previewError} />}
          {previewState === 'success' && queryData.preview_data && (
            <DatasetPreview preview={queryData.preview_data} hasFullDatasetAccess={hasFullDatasetAccess} queryData={queryData} />
          )}
        </section>
      )}

      {!hasFullDatasetAccess && (
        <RequestAccessModal open={modalOpen} onClose={() => setModalOpen(false)} queryData={queryData} />
      )}
    </div>
  )
}
