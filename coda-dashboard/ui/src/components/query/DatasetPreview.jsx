import { DatasetSummary } from './DatasetSummary'
import { PatientCoverage } from './PatientCoverage'
import { ColumnInformation } from './ColumnInformation'
import { SampleDataTable } from './SampleDataTable'
import { FullResultsTable } from '@/components/requests/FullResultsTable'
import { Button } from '@/components/ui/Button'
import { exportQueryResultsAsCSV, exportQueryResultsAsJSON } from '@/lib/exportResults'

// isDoctor + queryData together switch the row display from the standard
// 5-row sample to the full dataset with download actions — doctors aren't
// subject to the request-access workflow, so they get direct full access.
export function DatasetPreview({ preview, isDoctor = false, queryData = null }) {
  return (
    <div className="rounded-md border border-border bg-surface p-4">
      <DatasetSummary summary={preview.dataset_summary} />
      {preview.patient_insights && <PatientCoverage insights={preview.patient_insights} />}
      <ColumnInformation columns={preview.columns} rowCount={preview.dataset_summary.row_count} />
      {isDoctor ? (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Full Dataset</h3>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => exportQueryResultsAsCSV(queryData)}>
                Download CSV
              </Button>
              <Button variant="secondary" onClick={() => exportQueryResultsAsJSON(queryData)}>
                Download JSON
              </Button>
            </div>
          </div>
          <FullResultsTable results={queryData?.results} />
        </div>
      ) : (
        <SampleDataTable columns={preview.columns} rows={preview.sample_rows} />
      )}
    </div>
  )
}
