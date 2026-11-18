import { useEffect, useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { LoadingState } from '@/components/ui/LoadingState'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { FullResultsTable } from '@/components/requests/FullResultsTable'
import { api, AuthError } from '@/lib/api'
import { exportQueryResultsAsCSV, exportQueryResultsAsJSON } from '@/lib/exportResults'

const NAME_MIN = 2
const NAME_MAX = 255

const inputClass =
  'w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20'

export function SavedDatasetDetailModal({ datasetId, onClose, onAuthError, onChanged }) {
  const [dataset, setDataset] = useState(null)
  const [state, setState] = useState('loading')
  const [error, setError] = useState(null)

  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [savingEdit, setSavingEdit] = useState(false)
  const [editError, setEditError] = useState(null)

  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState(null)

  useEffect(() => {
    if (!datasetId) return
    let cancelled = false

    setState('loading')
    setError(null)
    setDataset(null)
    setEditing(false)
    setConfirmingDelete(false)

    api
      .get(`/datasets/${datasetId}`)
      .then(async (response) => {
        if (!response.ok) throw new Error('Failed to load dataset')
        const data = await response.json()
        if (!cancelled) {
          setDataset(data)
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
  }, [datasetId, onAuthError])

  function startEditing() {
    setEditName(dataset.name)
    setEditDescription(dataset.description ?? '')
    setEditError(null)
    setEditing(true)
  }

  async function handleSaveEdit(event) {
    event.preventDefault()
    setEditError(null)

    const trimmedName = editName.trim()
    if (trimmedName.length < NAME_MIN || trimmedName.length > NAME_MAX) {
      setEditError(`Dataset name must be between ${NAME_MIN} and ${NAME_MAX} characters`)
      return
    }

    setSavingEdit(true)
    try {
      const response = await api.put(`/datasets/${datasetId}`, {
        name: trimmedName,
        description: editDescription.trim() || null,
      })
      if (!response.ok) {
        const err = await response.json().catch(() => null)
        setEditError(err?.detail || 'Failed to update dataset')
        setSavingEdit(false)
        return
      }

      setDataset((prev) => ({ ...prev, name: trimmedName, description: editDescription.trim() || null }))
      setEditing(false)
      onChanged?.()
    } catch (err) {
      if (err instanceof AuthError) return onAuthError(err)
      setEditError(err.message || 'Something went wrong')
    } finally {
      setSavingEdit(false)
    }
  }

  async function handleDelete() {
    setDeleting(true)
    setDeleteError(null)
    try {
      const response = await api.delete(`/datasets/${datasetId}`)
      if (!response.ok) throw new Error('Failed to delete dataset')
      onChanged?.()
      onClose()
    } catch (err) {
      if (err instanceof AuthError) return onAuthError(err)
      setDeleteError(err.message)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Modal
      open={Boolean(datasetId)}
      onClose={onClose}
      title={dataset ? dataset.name : 'Dataset Details'}
      maxWidthClass="max-w-4xl"
    >
      {state === 'loading' && <LoadingState label="Loading dataset…" />}
      {state === 'error' && <ErrorBanner message={error} />}

      {state === 'success' && dataset && (
        <div className="space-y-5">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-muted-foreground">
              Saved on {new Date(dataset.created_at).toLocaleString()}
              {dataset.updated_at !== dataset.created_at && ` · Updated ${new Date(dataset.updated_at).toLocaleString()}`}
            </p>
            {!editing && (
              <Button variant="secondary" onClick={startEditing}>
                Edit Name / Description
              </Button>
            )}
          </div>

          {editing ? (
            <form onSubmit={handleSaveEdit} className="space-y-3 rounded-md border border-border bg-muted/40 p-3">
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">
                  Dataset Name <span className="text-destructive">*</span>
                </label>
                <input
                  type="text"
                  value={editName}
                  onChange={(event) => setEditName(event.target.value)}
                  className={inputClass}
                  autoFocus
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Description</label>
                <textarea
                  value={editDescription}
                  onChange={(event) => setEditDescription(event.target.value)}
                  rows={3}
                  className={inputClass}
                />
              </div>
              {editError && <p className="text-sm text-destructive">{editError}</p>}
              <div className="flex justify-end gap-2">
                <Button type="button" variant="secondary" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={savingEdit}>
                  {savingEdit ? 'Saving…' : 'Save Changes'}
                </Button>
              </div>
            </form>
          ) : (
            dataset.description && (
              <Section title="Description">
                <p className="text-sm text-foreground">{dataset.description}</p>
              </Section>
            )
          )}

          <Section title="Natural Language Query">
            <p className="rounded-sm bg-muted p-2 text-sm text-foreground">{dataset.nl_query}</p>
          </Section>

          <Section title="SPARQL Query">
            <pre className="overflow-x-auto rounded-sm bg-muted p-2 font-mono text-xs text-foreground">
              {dataset.sparql_query}
            </pre>
          </Section>

          <Section title="Full Dataset">
            <div className="mb-2 flex justify-end gap-2">
              <Button
                variant="secondary"
                onClick={() =>
                  exportQueryResultsAsCSV({ nl_query: dataset.nl_query, sparql: dataset.sparql_query, results: dataset.results })
                }
              >
                Download CSV
              </Button>
              <Button
                variant="secondary"
                onClick={() =>
                  exportQueryResultsAsJSON({ nl_query: dataset.nl_query, sparql: dataset.sparql_query, results: dataset.results })
                }
              >
                Download JSON
              </Button>
            </div>
            <FullResultsTable results={dataset.results} />
          </Section>

          <Section title="Danger Zone">
            {deleteError && <ErrorBanner message={deleteError} />}
            {confirmingDelete ? (
              <div className="flex items-center gap-2">
                <p className="text-sm text-foreground">Delete this dataset permanently? This cannot be undone.</p>
                <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
                  {deleting ? 'Deleting…' : 'Confirm Delete'}
                </Button>
                <Button variant="secondary" onClick={() => setConfirmingDelete(false)} disabled={deleting}>
                  Cancel
                </Button>
              </div>
            ) : (
              <Button variant="destructive" onClick={() => setConfirmingDelete(true)}>
                Delete Dataset
              </Button>
            )}
          </Section>
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
