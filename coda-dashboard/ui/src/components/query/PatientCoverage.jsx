import { Users, Repeat, Percent } from 'lucide-react'
import { StatCard } from '@/components/ui/StatCard'
import { PatientAppearanceChart } from './PatientAppearanceChart'

export function PatientCoverage({ insights }) {
  return (
    <div className="mb-6">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">Patient Coverage</h3>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard icon={Users} label="Unique Patients" value={insights.unique_patients.toLocaleString()} />
        <StatCard icon={Repeat} label="Returning Patients" value={insights.returning_patients.toLocaleString()} />
        <StatCard icon={Percent} label="Return Rate" value={`${insights.return_rate_percentage.toFixed(1)}%`} />
      </div>

      {insights.appearance_distribution && (
        <div className="mt-3 rounded-md border border-border bg-surface p-3">
          <p className="mb-2 text-xs text-muted-foreground">Visits per Patient</p>
          <PatientAppearanceChart distribution={insights.appearance_distribution} />
        </div>
      )}
    </div>
  )
}
