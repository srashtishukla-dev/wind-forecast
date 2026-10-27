import { describe, expect, it } from 'vitest'
import { buildChartData } from './chartData'

describe('buildChartData', () => {
  it('joins data on delivery start time, sorts intervals, and preserves missing values', () => {
    const chart = buildChartData(
      [
        { startTime: '2026-01-01T01:00:00Z', actualGeneration: null },
        { startTime: '2026-01-01T00:00:00Z', actualGeneration: 10 },
      ],
      [
        { startTime: '2026-01-01T01:00:00Z', forecastGeneration: 12 },
        { startTime: '2026-01-01T02:00:00Z', forecastGeneration: null },
      ],
    )

    expect(chart).toEqual([
      { startTime: '2026-01-01T00:00:00Z', actual: 10, forecast: null },
      { startTime: '2026-01-01T01:00:00Z', actual: null, forecast: 12 },
      { startTime: '2026-01-01T02:00:00Z', actual: null, forecast: null },
    ])
  })
})
