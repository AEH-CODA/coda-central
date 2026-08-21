export function StatCard({ icon: Icon, label, value }) {
  return (
    <div className="rounded-md border border-border bg-surface p-3 shadow-sm">
      <div className="flex items-center gap-2 text-muted-foreground">
        {Icon && <Icon size={18} strokeWidth={1.8} />}
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p className="mt-2 text-2xl font-extrabold text-foreground">{value}</p>
    </div>
  )
}
