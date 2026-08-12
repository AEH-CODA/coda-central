const variants = {
  primary: 'bg-accent text-accent-foreground hover:bg-accent/90',
  secondary: 'border border-border bg-surface text-foreground hover:border-primary hover:bg-muted',
  destructive: 'border border-destructive text-destructive hover:bg-destructive/10',
}

export function Button({ variant = 'primary', className = '', type = 'button', ...props }) {
  return (
    <button
      type={type}
      className={`inline-flex cursor-pointer items-center justify-center gap-2 rounded-sm px-4 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${variants[variant]} ${className}`}
      {...props}
    />
  )
}
