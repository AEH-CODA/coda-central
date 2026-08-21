import { isScanIdColumn, scanViewerUrl } from '@/lib/scanId'

export function ScanIdValue({ columnName, value }) {
  if (value === null || value === undefined) return '-'

  if (isScanIdColumn(columnName)) {
    return (
      <a
        href={scanViewerUrl(String(value))}
        target="_blank"
        rel="noopener noreferrer"
        className="font-medium text-primary underline hover:text-primary/80"
      >
        {value}
      </a>
    )
  }

  return String(value)
}
