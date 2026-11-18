import { api, API_BASE_URL, AuthError } from './api'
import { getToken } from './auth'

/**
 * Client for the OCT inference service (proxied by the gateway under /inference).
 * Errors from the service are {"detail": "<user-safe message>", "code": "<stable code>"};
 * they surface here as InferenceError so pages can show `message` and branch on `code`.
 */
export class InferenceError extends Error {
  constructor(message, code, status) {
    super(message)
    this.name = 'InferenceError'
    this.code = code
    this.status = status
  }
}

async function errorFrom(response, fallback) {
  const body = await response.json().catch(() => null)
  const detail = typeof body?.detail === 'string' ? body.detail : body?.detail?.detail
  return new InferenceError(detail || fallback, body?.code, response.status)
}

async function json(promise, fallback) {
  const response = await promise
  if (!response.ok) throw await errorFrom(response, fallback)
  if (response.status === 204) return null
  return response.json()
}

export const inference = {
  models: () => json(api.get('/inference/models'), 'Failed to load models'),
  jobs: ({ all = false, limit = 100 } = {}) =>
    json(api.get(`/inference/jobs?limit=${limit}${all ? '&all=true' : ''}`), 'Failed to load analyses'),
  job: (id) => json(api.get(`/inference/jobs/${id}`), 'Failed to load the analysis'),
  remove: (id) => json(api.delete(`/inference/jobs/${id}`), 'Failed to delete the analysis'),
  setEtdrsCenter: (id, centerMm) =>
    json(api.post(`/inference/jobs/${id}/etdrs`, { center_mm: centerMm }), 'Failed to move the ETDRS grid'),
}

/** Multipart upload with progress (fetch has no upload progress, so this uses XHR). */
export function uploadScan(file, modelId, onProgress) {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    if (modelId) form.append('model_id', modelId)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE_URL}/inference/jobs`)
    const token = getToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total)
    }
    xhr.onload = () => {
      let body = null
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        /* non-JSON error page (e.g. nginx 413) */
      }
      if (xhr.status === 401) {
        reject(new AuthError(body?.detail?.action || 'Session expired. Please sign out and sign in again.'))
      } else if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body)
      } else if (xhr.status === 413) {
        reject(new InferenceError(body?.detail || 'The file is too large to upload.', 'file_too_large', 413))
      } else {
        const detail = typeof body?.detail === 'string' ? body.detail : null
        reject(new InferenceError(detail || `Upload failed (HTTP ${xhr.status}).`, body?.code, xhr.status))
      }
    }
    xhr.onerror = () => reject(new InferenceError('Upload failed: the server could not be reached.', 'network'))
    xhr.send(form)
  })
}

/** Fetches an authenticated file (images, downloads) and returns an object URL. Caller revokes it. */
export async function fetchObjectUrl(path) {
  const response = await api.get(path)
  if (!response.ok) throw await errorFrom(response, 'Failed to load file')
  return URL.createObjectURL(await response.blob())
}

export async function downloadFile(path, filename) {
  const url = await fetchObjectUrl(path)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export const ACTIVE_STATUSES = ['queued', 'running']

export function formatNl(value) {
  if (value === null || value === undefined) return '–'
  if (value === 0) return '0.00'
  return value < 10 ? value.toFixed(2) : value.toFixed(1)
}

export function eyeLabel(laterality) {
  return laterality === 'OD' ? 'OD (right)' : laterality === 'OS' ? 'OS (left)' : '–'
}
