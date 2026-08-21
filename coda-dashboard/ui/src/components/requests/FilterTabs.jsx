export function FilterTabs({ tabs, active, onChange }) {
  return (
    <div className="mb-4 flex gap-1 border-b border-border">
      {tabs.map((tab) => (
        <button
          key={tab.value}
          type="button"
          onClick={() => onChange(tab.value)}
          className={`flex cursor-pointer items-center gap-2 border-b-2 px-3 py-2.5 text-sm font-medium transition-colors ${
            active === tab.value
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          {tab.label}
          {tab.count !== undefined && (
            <span className="rounded-full bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{tab.count}</span>
          )}
        </button>
      ))}
    </div>
  )
}
