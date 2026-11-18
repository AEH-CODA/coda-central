import { formatNl } from '@/lib/inference'

/** RetInSight-style compartment table: rows = fluid classes, columns = ETDRS circles + whole scan (nL). */
export function VolumeTable({ classes, volumes, coverage }) {
  const etdrsKeys = Object.keys(volumes)
    .filter((k) => k.startsWith('etdrs_'))
    .sort((a, b) => parseFloat(a.slice(6)) - parseFloat(b.slice(6)))
  const cols = [
    ...etdrsKeys.map((k) => {
      const d = k.slice(6).replace('mm', '')
      return {
        key: k,
        label: `ETDRS ${d} mm`,
        title: `Fluid inside the ${d} mm diameter ETDRS circle around the grid centre`,
        partial: coverage?.[k] === false,
      }
    }),
    { key: 'total', label: 'Total scan', title: 'Fluid in the whole scanned area' },
  ]

  return (
    <div className="overflow-x-auto rounded-md border border-border bg-surface">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/40">
            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Compartment
            </th>
            {cols.map((c) => (
              <th
                key={c.key}
                title={c.title}
                className="whitespace-nowrap px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground"
              >
                {c.label}
                {c.partial && (
                  <span className="ml-1 normal-case text-warning" title="The scan does not cover this whole circle">
                    (partial)
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {classes.map((cls) => (
            <tr key={cls.name} className="border-b border-border last:border-0">
              <td className="px-3 py-2">
                <div className="flex items-center gap-3">
                  <span
                    className="inline-flex w-11 justify-center rounded-sm px-1.5 py-0.5 text-xs font-bold text-white"
                    style={{ backgroundColor: cls.color }}
                  >
                    {cls.name}
                  </span>
                  <span className="text-foreground">{cls.label}</span>
                </div>
              </td>
              {cols.map((c) => (
                <td key={c.key} className="px-3 py-2 text-right font-semibold tabular-nums text-foreground">
                  {formatNl(volumes[c.key]?.[cls.name])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-border px-3 py-1.5 text-xs text-muted-foreground">Volumes in nanolitres (nL = 0.001 mm³)</p>
    </div>
  )
}
