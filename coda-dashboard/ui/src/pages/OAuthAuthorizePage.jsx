import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { useAuth } from '@/hooks/useAuth'
import { api, AuthError } from '@/lib/api'

// Connected apps are configured server-side (auth-service's oauth_clients
// table); this is just cosmetic — a friendlier name/description than raw
// client_id/scope strings for the consent screen.
const CLIENT_NAMES = {
  biomni: 'Biomni',
}

const SCOPE_DESCRIPTIONS = {
  'datasets:read': 'View and export your saved datasets',
}

export function OAuthAuthorizePage() {
  const { userName } = useAuth()
  const [searchParams] = useSearchParams()
  const [state, setState] = useState('idle') // idle | working | denied | error
  const [error, setError] = useState(null)

  const clientId = searchParams.get('client_id')
  const redirectUri = searchParams.get('redirect_uri')
  const scope = searchParams.get('scope')
  const oauthState = searchParams.get('state')

  const missingParams = !clientId || !redirectUri || !scope || !oauthState
  const clientName = CLIENT_NAMES[clientId] || clientId
  const scopes = scope ? scope.split(' ') : []

  async function handleAllow() {
    setState('working')
    setError(null)
    try {
      const response = await api.post('/oauth/authorize', {
        client_id: clientId,
        redirect_uri: redirectUri,
        scope,
        state: oauthState,
      })

      if (!response.ok) {
        const err = await response.json().catch(() => null)
        throw new Error(err?.detail || 'Failed to authorize this app')
      }

      const data = await response.json()
      window.location.href = data.redirect_url
    } catch (err) {
      if (err instanceof AuthError) {
        setError(err.message)
        setState('error')
        return
      }
      setError(err.message)
      setState('error')
    }
  }

  function handleDeny() {
    setState('denied')
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm rounded-md border border-border bg-surface p-8 shadow-sm">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <ShieldCheck size={20} strokeWidth={1.8} />
          </div>
          <h1 className="text-xl font-bold text-foreground">Connect an app</h1>
        </div>

        {missingParams ? (
          <ErrorBanner message="This authorization link is missing required information. Go back to the app you're connecting from and try again." />
        ) : state === 'denied' ? (
          <p className="text-center text-sm text-muted-foreground">
            You didn't grant access. You can close this window and return to {clientName}.
          </p>
        ) : (
          <>
            <p className="mb-4 text-sm text-foreground">
              <span className="font-semibold">{clientName}</span> wants to connect to your CODA account
              {userName ? <> ({userName})</> : null}. It will be able to:
            </p>
            <ul className="mb-6 space-y-2">
              {scopes.map((s) => (
                <li key={s} className="flex items-start gap-2 text-sm text-foreground">
                  <span className="mt-0.5 text-primary">•</span>
                  {SCOPE_DESCRIPTIONS[s] || s}
                </li>
              ))}
            </ul>

            {error && <ErrorBanner message={error} />}

            <div className="flex gap-3">
              <Button variant="secondary" className="flex-1" onClick={handleDeny} disabled={state === 'working'}>
                Deny
              </Button>
              <Button variant="primary" className="flex-1" onClick={handleAllow} disabled={state === 'working'}>
                {state === 'working' ? 'Connecting…' : 'Allow'}
              </Button>
            </div>

            <p className="mt-6 text-center text-xs text-muted-foreground">
              You can revoke this access at any time from Model Workspace → Connected Apps.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
