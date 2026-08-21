import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { LoadingState } from '@/components/ui/LoadingState'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { useAuth } from '@/hooks/useAuth'
import { api, AuthError } from '@/lib/api'

const ROLES = ['user', 'doctor', 'data-manager', 'admin']

const selectClass =
  'rounded-sm border border-border bg-surface px-2 py-1.5 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-40'

export function RoleManagementPage() {
  const { logout, userId } = useAuth()
  const navigate = useNavigate()

  const [users, setUsers] = useState([])
  const [changes, setChanges] = useState([])
  const [state, setState] = useState('loading')
  const [error, setError] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [savingId, setSavingId] = useState(null)
  const [rowError, setRowError] = useState(null)

  function handleAuthError(err) {
    window.alert(err.message)
    logout()
    navigate('/login', { replace: true })
  }

  const load = useCallback(async () => {
    setState('loading')
    setError(null)
    try {
      const [usersResponse, changesResponse] = await Promise.all([
        api.get('/users'),
        api.get('/role-changes?skip=0&limit=20'),
      ])

      if (!usersResponse.ok) throw new Error('Failed to load users')
      if (!changesResponse.ok) throw new Error('Failed to load role change history')

      const usersData = await usersResponse.json()
      const changesData = await changesResponse.json()

      setUsers(usersData.users ?? [])
      setChanges(changesData.changes ?? [])
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

  async function handleSave(user) {
    const newRole = drafts[user.id]
    if (!newRole || newRole === user.role) return

    setSavingId(user.id)
    setRowError(null)
    try {
      const response = await api.put(`/users/${user.id}/role`, { role: newRole })
      if (!response.ok) {
        const err = await response.json().catch(() => null)
        throw new Error(err?.detail || 'Failed to update role')
      }

      setUsers((prev) => prev.map((u) => (u.id === user.id ? { ...u, role: newRole } : u)))
      setDrafts((prev) => {
        const next = { ...prev }
        delete next[user.id]
        return next
      })
      load()
    } catch (err) {
      if (err instanceof AuthError) return handleAuthError(err)
      setRowError(`${user.email}: ${err.message}`)
    } finally {
      setSavingId(null)
    }
  }

  return (
    <div>
      <PageHeader title="Role Management" subtitle="Assign roles to users" />

      {state === 'loading' && <LoadingState label="Loading users…" />}
      {state === 'error' && <ErrorBanner message={error} />}
      {rowError && <ErrorBanner message={rowError} />}

      {state === 'success' && (
        <>
          <div className="overflow-x-auto rounded-md border border-border bg-surface">
            <table className="w-full min-w-max border-collapse text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40">
                  <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Name
                  </th>
                  <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Email
                  </th>
                  <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Role
                  </th>
                  <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground" />
                </tr>
              </thead>
              <tbody>
                {users.map((user) => {
                  const isSelf = user.id === userId
                  const draft = drafts[user.id] ?? user.role
                  const dirty = draft !== user.role

                  return (
                    <tr key={user.id} className="h-12 border-b border-border last:border-0 hover:bg-muted/40">
                      <td className="whitespace-nowrap px-3 py-2 text-foreground">{user.name ?? '-'}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-foreground">{user.email}</td>
                      <td className="whitespace-nowrap px-3 py-2">
                        <select
                          value={draft}
                          disabled={isSelf || savingId === user.id}
                          onChange={(event) =>
                            setDrafts((prev) => ({ ...prev, [user.id]: event.target.value }))
                          }
                          className={selectClass}
                        >
                          {ROLES.map((role) => (
                            <option key={role} value={role}>
                              {role}
                            </option>
                          ))}
                        </select>
                        {isSelf && <span className="ml-2 text-xs text-muted-foreground">(you)</span>}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2">
                        {dirty && (
                          <Button
                            variant="secondary"
                            disabled={savingId === user.id}
                            onClick={() => handleSave(user)}
                          >
                            {savingId === user.id ? 'Saving…' : 'Save'}
                          </Button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <h2 className="mb-3 mt-8 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Recent Role Changes
          </h2>
          {changes.length === 0 ? (
            <p className="rounded-md border border-border bg-surface p-6 text-center text-sm text-muted-foreground">
              No role changes yet.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-md border border-border bg-surface">
              <table className="w-full min-w-max border-collapse text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/40">
                    <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      User
                    </th>
                    <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Change
                    </th>
                    <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Changed By
                    </th>
                    <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      When
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {changes.map((change) => (
                    <tr key={change.id} className="h-9 border-b border-border last:border-0">
                      <td className="whitespace-nowrap px-3 py-2 text-foreground">{change.user_email}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-foreground">
                        {change.old_role} → {change.new_role}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-foreground">{change.changed_by_email}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-foreground">
                        {new Date(change.changed_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
