import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { api, AuthError } from '@/lib/api'

const NAME_MIN = 2
const NAME_MAX = 255

const inputClass =
  'w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20'

export function SaveDatasetModal({ open, onClose, queryData, onAuthError }) {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null)

  function reset() {
    setName('')
    setDescription('')
    setError(null)
    setSubmitting(false)
    setResult(null)
  }

  function handleClose() {
    reset()
    onClose()
  }

  function handleViewSaved() {
    handleClose()
    navigate('/saved-datasets')
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)

    const trimmedName = name.trim()
    if (trimmedName.length < NAME_MIN || trimmedName.length > NAME_MAX) {
      setError(`Dataset name must be between ${NAME_MIN} and ${NAME_MAX} characters`)
      return
    }
    if (!queryData?.results) {
      setError('No query results to save')
      return
    }

    setSubmitting(true)
    try {
      const response = await api.post('/datasets', {
        nl_query: queryData.nl_query,
        sparql_query: queryData.sparql,
        results: queryData.results,
        name: trimmedName,
        description: description.trim() || null,
      })

      if (!response.ok) {
        const err = await response.json().catch(() => null)
        setError(err?.detail || 'Failed to save dataset')
        setSubmitting(false)
        return
      }

      const data = await response.json()
      setResult({ datasetId: data.dataset_id })
    } catch (err) {
      if (err instanceof AuthError) return onAuthError(err)
      setError(err.message || 'Something went wrong')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal open={open} onClose={handleClose} title={result ? 'Dataset Saved' : 'Save Dataset'} maxWidthClass="max-w-lg">
      {result ? (
        <div>
          <p className="text-sm text-foreground">
            Your dataset has been saved. Dataset ID: <span className="font-mono text-xs">{result.datasetId}</span>
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            You can find it anytime on the Saved Datasets page.
          </p>
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="secondary" onClick={handleClose}>
              Close
            </Button>
            <Button onClick={handleViewSaved}>View Saved Datasets</Button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <p className="mb-1 text-xs font-medium text-muted-foreground">Query Preview</p>
            <div className="max-h-24 overflow-y-auto rounded-sm bg-muted p-2 text-sm text-foreground">
              {queryData?.nl_query}
            </div>
          </div>

          <div>
            <p className="mb-1 text-xs font-medium text-muted-foreground">Dataset Summary</p>
            <p className="text-sm text-foreground">
              Rows: {queryData?.preview_data?.dataset_summary?.row_count?.toLocaleString() ?? '-'} · Columns:{' '}
              {queryData?.preview_data?.dataset_summary?.column_count ?? '-'}
            </p>
          </div>

          <Field label="Dataset Name" required>
            <input
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Enter a name for this dataset (2-255 characters)"
              className={inputClass}
              autoFocus
            />
            <p className="mt-1 text-xs text-muted-foreground">{name.length}/255 characters</p>
          </Field>

          <Field label="Description">
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
              placeholder="Optional: add notes about this dataset"
              className={inputClass}
            />
          </Field>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={handleClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? 'Saving…' : 'Save Dataset'}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  )
}

function Field({ label, required, children }) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-foreground">
        {label} {required && <span className="text-destructive">*</span>}
      </label>
      {children}
    </div>
  )
}
