const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
).replace(/\/+$/, '')

async function getJson(path, parameters, signal) {
  const query = new URLSearchParams(parameters)
  let response

  try {
    response = await fetch(`${API_BASE_URL}${path}?${query}`, {
      headers: { Accept: 'application/json' },
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new Error('Could not reach the backend. Check that FastAPI is running.')
  }

  let payload
  try {
    payload = await response.json()
  } catch {
    throw new Error(
      response.ok
        ? 'The backend returned an invalid response.'
        : `The backend request failed with HTTP ${response.status}.`,
    )
  }

  if (!response.ok) {
    const detail =
      typeof payload?.detail === 'string'
        ? payload.detail
        : `Request failed with HTTP ${response.status}.`
    throw new Error(detail)
  }

  return payload
}

function assertRecords(payload, endpoint) {
  if (!payload || !Array.isArray(payload.records)) {
    throw new Error(`${endpoint} returned an unexpected response shape.`)
  }
  return payload
}

export function toUtcTimestamp(date, endOfDate = false) {
  const [year, month, day] = date.split('-').map(Number)
  const value = new Date(Date.UTC(year, month - 1, day + Number(endOfDate)))
  return value.toISOString()
}

function publicationWindow(filters) {
  const deliveryStart = new Date(toUtcTimestamp(filters.startDate))
  const deliveryEnd = new Date(toUtcTimestamp(filters.endDate, true))
  const leadMilliseconds = Number(filters.decisionLeadHours) * 60 * 60 * 1000

  return {
    publish_from: new Date(deliveryStart.getTime() - leadMilliseconds).toISOString(),
    publish_to: new Date(deliveryEnd.getTime() - leadMilliseconds).toISOString(),
  }
}

export async function fetchDashboard(filters, signal) {
  const publication = publicationWindow(filters)
  const lead = String(Number(filters.decisionLeadHours))
  const accuracy = await getJson(
    '/api/forecast-accuracy',
    {
      start_time: toUtcTimestamp(filters.startDate),
      end_time: toUtcTimestamp(filters.endDate, true),
      ...publication,
      decision_lead_hours: lead,
    },
    signal,
  )
  if (!accuracy || !Array.isArray(accuracy.selected_forecasts)) {
    throw new Error('/api/forecast-accuracy returned no selected forecast series.')
  }
  if (!Array.isArray(accuracy.actual_records)) {
    throw new Error('/api/forecast-accuracy returned no actual series.')
  }
  const invalidActualGenerations =
    accuracy.excluded_records?.invalid_actual_generations || 0
  const incompleteIntervals = accuracy.actual_records.filter(
    (record) => record.actualGeneration == null,
  ).length
  const actuals = {
    records: accuracy.actual_records,
    incomplete_intervals: incompleteIntervals,
    quality: {
      invalid_timestamp_records:
        accuracy.excluded_records?.invalid_actual_timestamps || 0,
      invalid_generation_records: invalidActualGenerations,
      missing_generation_records: Math.max(
        0,
        incompleteIntervals - invalidActualGenerations,
      ),
    },
  }
  return { actuals, accuracy, publication }
}

export async function fetchForecastVersions(startTime, publication, signal) {
  const payload = await getJson(
    '/api/forecast-versions',
    {
      start_time: startTime,
      publish_from: publication.publish_from,
      publish_to: publication.publish_to,
    },
    signal,
  )
  return assertRecords(payload, '/api/forecast-versions')
}

export async function fetchHealth(signal) {
  const payload = await getJson('/health', {}, signal)
  if (payload?.status !== 'ok') {
    throw new Error('The backend health check returned an unexpected response.')
  }
  return payload
}

export const dashboardApiBaseUrl = API_BASE_URL
