import { useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { api, AuthError } from '@/lib/api'

const PROJECT_NAME_MIN = 2
const PROJECT_NAME_MAX = 255
const REASON_MIN = 10
const REASON_MAX = 500
const MAX_FILE_SIZE = 10 * 1024 * 1024

const inputClass =
  'w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20'

export function RequestAccessModal({ open, onClose, queryData }) {
  const [projectName, setProjectName] = useState('')
  const [reason, setReason] = useState('')
  const [file, setFile] = useState(null)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null)

  function reset() {
    setProjectName('')
    setReason('')
    setFile(null)
    setError(null)
    setSubmitting(false)
    setResult(null)
  }

  function handleClose() {
    reset()
    onClose()
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)

    const trimmedName = projectName.trim()
    if (trimmedName.length < PROJECT_NAME_MIN || trimmedName.length > PROJECT_NAME_MAX) {
      setError(`Project name must be between ${PROJECT_NAME_MIN} and ${PROJECT_NAME_MAX} characters`)
      return
    }
    if (reason.length < REASON_MIN || reason.length > REASON_MAX) {
      setError(`Reason must be between ${REASON_MIN} and ${REASON_MAX} characters`)
      return
    }
    if (file) {
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        setError('Supporting document must be a PDF file')
        return
      }
      if (file.size > MAX_FILE_SIZE) {
        setError('PDF file size must not exceed 10MB')
        return
      }
    }
    if (!queryData) {
      setError('No query results to request')
      return
    }

    setSubmitting(true)
    try {
      const formData = new FormData()
      formData.append('project_name', trimmedName)
      formData.append('reason', reason)
      formData.append('nl_query', queryData.nl_query)
      formData.append('sparql_query', queryData.sparql)
      if (queryData.preview_data) formData.append('data_preview', JSON.stringify(queryData.preview_data))
      if (file) formData.append('supporting_document', file)

      const createResponse = await api.postForm('/datasets/access-requests/create', formData)
      if (!createResponse.ok) {
        const err = await createResponse.json().catch(() => null)
        setError(err?.detail || 'Failed to create request')
        setSubmitting(false)
        return
      }

      const { request_id: requestId } = await createResponse.json()

      if (queryData.results) {
        try {
          await api.post(`/datasets/access-requests/${requestId}/full-results`, queryData.results)
        } catch {
          // Best-effort — the request itself already succeeded, so don't
          // block the confirmation on this secondary write.
        }
      }

      setResult({ requestId })
    } catch (err) {
      setError(err instanceof AuthError ? err.message : err.message || 'Something went wrong')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={result ? 'Request Submitted' : 'Request Data Access'}
      maxWidthClass="max-w-lg"
    >
      {result ? (
        <div>
          <p className="text-sm text-foreground">
            Your data access request has been submitted. Request ID:{' '}
            <span className="font-mono text-xs">{result.requestId}</span>
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            You'll be notified once an Admin or Data Manager approves or rejects your request.
          </p>
          <div className="mt-6 flex justify-end">
            <Button onClick={handleClose}>Done</Button>
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

          <Field label="Project Name" required>
            <input
              type="text"
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
              placeholder="Enter the name of your project (2-255 characters)"
              className={inputClass}
            />
            <p className="mt-1 text-xs text-muted-foreground">{projectName.length}/255 characters</p>
          </Field>

          <Field label="Supporting Document (PDF)">
            <input
              type="file"
              accept=".pdf"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className="block w-full cursor-pointer text-sm text-muted-foreground file:mr-3 file:cursor-pointer file:rounded-sm file:border-0 file:bg-muted file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-foreground"
            />
            <p className="mt-1 text-xs text-muted-foreground">Optional — max 10MB</p>
          </Field>

          <Field label="Reason for Access" required>
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows={4}
              placeholder="Please explain your reason for requesting access to this data (10-500 characters)"
              className={inputClass}
            />
            <p className="mt-1 text-xs text-muted-foreground">{reason.length}/500 characters</p>
          </Field>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={handleClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? 'Sending…' : 'Send Request'}
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
