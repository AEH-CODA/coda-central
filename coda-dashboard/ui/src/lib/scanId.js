const SCAN_ID_COLUMN_NAMES = new Set(['scan_id', 'scanid', 'scaninstanceuid', 'studyinstanceuids'])

export function isScanIdColumn(columnName) {
  return SCAN_ID_COLUMN_NAMES.has(String(columnName).toLowerCase())
}

export function scanViewerUrl(scanId) {
  return `https://coda.innowave.asia/viewer?StudyInstanceUIDs=${encodeURIComponent(scanId)}`
}
