import { getToken } from './auth'

// Same runtime-hostname pattern the original static app used, so the API
// gateway is reachable the same way in dev and in the container.
export const API_BASE_URL = `${window.location.protocol}//${window.location.hostname}:8000`

export class AuthError extends Error {
  constructor(message) {
    super(message)
    this.name = 'AuthError'
  }
}

async function request(path, { method = 'GET', body, isFormData = false } = {}) {
  const token = getToken()
  const headers = {}
  if (!isFormData) headers['Content-Type'] = 'application/json'
  if (token) headers['Authorization'] = `Bearer ${token}`

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (response.status === 401) {
    const err = await response.json().catch(() => null)
    throw new AuthError(err?.action || 'Session expired. Please sign out and sign in again.')
  }

  return response
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body }),
  put: (path, body) => request(path, { method: 'PUT', body }),
  postForm: (path, formData) => request(path, { method: 'POST', body: formData, isFormData: true }),
}
