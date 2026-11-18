import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { AuthError } from '@/lib/api'
import { fetchObjectUrl } from '@/lib/inference'

/** Same behaviour as the other pages: an expired session alerts, signs out and goes to /login. */
export function useAuthErrorHandler() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  return useCallback(
    (err) => {
      if (!(err instanceof AuthError)) return false
      window.alert(err.message)
      logout()
      navigate('/login', { replace: true })
      return true
    },
    [logout, navigate],
  )
}

/**
 * Authenticated images can't use <img src> (no bearer header), so they are fetched as blobs.
 * The cache keeps object URLs for the lifetime of the component and revokes them on unmount.
 */
export function useAuthedImages() {
  const cache = useRef(new Map()) // path -> Promise<url>
  useEffect(() => {
    const current = cache.current
    return () => {
      for (const p of current.values()) p.then((url) => URL.revokeObjectURL(url)).catch(() => {})
      current.clear()
    }
  }, [])
  return useCallback((path) => {
    if (!cache.current.has(path)) {
      const p = fetchObjectUrl(path)
      p.catch(() => cache.current.delete(path)) // allow a retry after a failure
      cache.current.set(path, p)
    }
    return cache.current.get(path)
  }, [])
}

/** Object URL for one authenticated image path (null while loading or on error). */
export function useAuthedImage(load, path) {
  const [state, setState] = useState({ path: null, url: null })
  useEffect(() => {
    if (!path) return undefined
    let alive = true
    load(path)
      .then((url) => alive && setState({ path, url }))
      .catch(() => alive && setState({ path, url: null }))
    return () => {
      alive = false
    }
  }, [load, path])
  return state.path === path ? state.url : null
}
