export function ErrorBanner({ message }) {
  if (!message) return null

  return (
    <div className="mb-4 rounded-md border-l-4 border-destructive bg-destructive/10 p-3 text-sm text-destructive">
      {message}
    </div>
  )
}
