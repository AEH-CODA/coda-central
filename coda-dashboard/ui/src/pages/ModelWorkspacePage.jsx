import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { LoadingState } from '@/components/ui/LoadingState'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { useAuth } from '@/hooks/useAuth'
import { api, AuthError } from '@/lib/api'

// Mirrors OAuthAuthorizePage.jsx — cosmetic names/descriptions for the
// server-configured OAuth clients and scopes (auth-service's oauth_clients
// table is the source of truth).
const CLIENT_NAMES = {
  biomni: 'Biomni',
}

const SCOPE_DESCRIPTIONS = {
  'datasets:read': 'View and export your saved datasets',
}

export function ModelWorkspacePage() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  const [grants, setGrants] = useState([])
  const [state, setState] = useState('loading')
  const [error, setError] = useState(null)
  const [revokingId, setRevokingId] = useState(null)

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
        const response = await api.get('/oauth/grants')
        if (!response.ok) throw new Error('Failed to load connected apps')
        const data = await response.json()
        if (!cancelled) {
          setGrants(data.grants ?? [])
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

  async function handleRevoke(grant) {
    const clientName = CLIENT_NAMES[grant.client_id] || grant.client_id
    if (!window.confirm(`Revoke ${clientName}'s access to your datasets?`)) return

    setRevokingId(grant.id)
    try {
      const response = await api.delete(`/oauth/grants/${grant.id}`)
      if (!response.ok) throw new Error('Failed to revoke access')
      setGrants((prev) => prev.filter((g) => g.id !== grant.id))
    } catch (err) {
      if (err instanceof AuthError) return handleAuthError(err)
      window.alert(err.message)
    } finally {
      setRevokingId(null)
    }
  }

  return (
    <div>
      <PageHeader title="Model Workspace" subtitle="Manage tools connected to your CODA account" />

      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">Connected Apps</h2>

      {state === 'loading' && <LoadingState label="Loading connected apps…" />}
      {state === 'error' && <ErrorBanner message={error} />}

      {state === 'success' && grants.length === 0 && (
        <p className="rounded-md border border-border bg-surface p-6 text-center text-sm text-muted-foreground">
          No apps are connected yet. Connect a tool like Biomni to it to read your saved datasets — it will ask
          you to sign in and approve access here.
        </p>
      )}

      {state === 'success' && grants.length > 0 && (
        <div className="space-y-3">
          {grants.map((grant) => (
            <div
              key={grant.id}
              className="flex items-center justify-between rounded-md border border-border bg-surface p-4"
            >
              <div>
                <p className="text-sm font-semibold text-foreground">{CLIENT_NAMES[grant.client_id] || grant.client_id}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {grant.scope
                    .split(' ')
                    .map((s) => SCOPE_DESCRIPTIONS[s] || s)
                    .join(', ')}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Connected {new Date(grant.issued_at).toLocaleDateString()} · Expires{' '}
                  {new Date(grant.expires_at).toLocaleDateString()}
                </p>
              </div>
              <Button
                variant="destructive"
                disabled={revokingId === grant.id}
                onClick={() => handleRevoke(grant)}
              >
                {revokingId === grant.id ? 'Revoking…' : 'Revoke'}
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
