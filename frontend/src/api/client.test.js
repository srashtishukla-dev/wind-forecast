import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchDashboard, fetchForecastVersions, toUtcTimestamp } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

function jsonResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  }
}

describe('backend API client', () => {
  it('converts inclusive date filters into UTC interval boundaries', () => {
    expect(toUtcTimestamp('2026-01-31')).toBe('2026-01-31T00:00:00.000Z')
    expect(toUtcTimestamp('2026-01-31', true)).toBe('2026-02-01T00:00:00.000Z')
  })

  it('requests actuals and accuracy using backend parameter names and a matched cutoff window', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        actual_records: [],
        selected_forecasts: [],
        excluded_records: {},
      }))
    vi.stubGlobal('fetch', fetch)

    const result = await fetchDashboard(
      {
        startDate: '2026-01-01',
        endDate: '2026-01-31',
        decisionLeadHours: '24',
      },
      new AbortController().signal,
    )

    const accuracyUrl = new URL(fetch.mock.calls[0][0])
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(accuracyUrl.pathname).toBe('/api/forecast-accuracy')
    expect(accuracyUrl.searchParams.get('start_time')).toBe('2026-01-01T00:00:00.000Z')
    expect(accuracyUrl.searchParams.get('end_time')).toBe('2026-02-01T00:00:00.000Z')
    expect(accuracyUrl.searchParams.get('publish_from')).toBe('2025-12-31T00:00:00.000Z')
    expect(accuracyUrl.searchParams.get('publish_to')).toBe('2026-01-31T00:00:00.000Z')
    expect(accuracyUrl.searchParams.get('decision_lead_hours')).toBe('24')
    expect(result.actuals.records).toEqual([])
  })

  it('uses the forecast-version endpoint and its publication filters', async () => {
    const fetch = vi.fn().mockResolvedValue(
      jsonResponse({ records: [{ publishTime: '2025-12-31T00:00:00Z' }] }),
    )
    vi.stubGlobal('fetch', fetch)

    const result = await fetchForecastVersions(
      '2026-01-01T00:00:00Z',
      {
        publish_from: '2025-12-31T00:00:00Z',
        publish_to: '2026-01-31T00:00:00Z',
      },
      new AbortController().signal,
    )

    const url = new URL(fetch.mock.calls[0][0])
    expect(url.pathname).toBe('/api/forecast-versions')
    expect(url.searchParams.get('start_time')).toBe('2026-01-01T00:00:00Z')
    expect(url.searchParams.get('publish_from')).toBe('2025-12-31T00:00:00Z')
    expect(result.records).toHaveLength(1)
  })

  it('reports backend errors and unexpected response shapes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      jsonResponse({ detail: 'Elexon API returned HTTP 503' }, 502),
    ))
    await expect(
      fetchForecastVersions('2026-01-01T00:00:00Z', {
        publish_from: '2025-12-31T00:00:00Z',
        publish_to: '2026-01-31T00:00:00Z',
      }),
    ).rejects.toThrow('Elexon API returned HTTP 503')

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ records: 'invalid' })))
    await expect(
      fetchForecastVersions('2026-01-01T00:00:00Z', {
        publish_from: '2025-12-31T00:00:00Z',
        publish_to: '2026-01-31T00:00:00Z',
      }),
    ).rejects.toThrow('unexpected response shape')
  })
})
