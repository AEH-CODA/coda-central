export function PageHeader({ title, subtitle }) {
  return (
    <header className="mb-6">
      <h1 className="text-xl font-bold text-foreground">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
    </header>
  )
}
