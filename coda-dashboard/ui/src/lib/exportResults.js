function downloadBlob(content, mimeType, filename) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export function exportResultsAsJSON(request) {
  const payload = {
    request_id: request.id,
    nl_query: request.nl_query,
    sparql_query: request.sparql_query,
    requested_at: request.created_at,
    approved_at: request.reviewed_at,
    status: request.status,
    full_results: request.full_results,
  }
  downloadBlob(JSON.stringify(payload, null, 2), 'application/json', `data-request_${request.id}_${Date.now()}.json`)
}

export function exportResultsAsCSV(request) {
  const results = request.full_results
  if (!results?.head?.vars || !results?.results?.bindings) return

  const columns = results.head.vars
  const rows = results.results.bindings
  const lines = [columns.join(',')]

  rows.forEach((row) => {
    const values = columns.map((col) => {
      const value = row[col]?.value ?? ''
      const escaped = String(value).replace(/"/g, '""')
      return escaped.includes(',') ? `"${escaped}"` : escaped
    })
    lines.push(values.join(','))
  })

  downloadBlob(lines.join('\n'), 'text/csv', `data-request_${request.id}_${Date.now()}.csv`)
}

// Doctors get direct dataset downloads (no access-request workflow), exporting
// the complete SPARQL results already returned by /query — same results shape
// as the access-request exports above.
export function exportQueryResultsAsJSON(queryData) {
  const payload = {
    nl_query: queryData.nl_query,
    sparql_query: queryData.sparql,
    results: queryData.results,
  }
  downloadBlob(JSON.stringify(payload, null, 2), 'application/json', `dataset_${Date.now()}.json`)
}

export function exportQueryResultsAsCSV(queryData) {
  const results = queryData.results
  if (!results?.head?.vars || !results?.results?.bindings) return

  const columns = results.head.vars
  const rows = results.results.bindings
  const lines = [columns.join(',')]

  rows.forEach((row) => {
    const values = columns.map((col) => {
      const value = row[col]?.value ?? ''
      const escaped = String(value).replace(/"/g, '""')
      return escaped.includes(',') ? `"${escaped}"` : escaped
    })
    lines.push(values.join(','))
  })

  downloadBlob(lines.join('\n'), 'text/csv', `dataset_${Date.now()}.csv`)
}
