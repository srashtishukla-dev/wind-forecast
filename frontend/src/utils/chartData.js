export function buildChartData(actuals, forecasts) {
  const intervals = new Map()
  for (const record of actuals) {
    intervals.set(record.startTime, {
      startTime: record.startTime,
      actual: record.actualGeneration,
      forecast: null,
    })
  }
  for (const record of forecasts) {
    const interval = intervals.get(record.startTime) || {
      startTime: record.startTime,
      actual: null,
      forecast: null,
    }
    interval.forecast = record.forecastGeneration
    intervals.set(record.startTime, interval)
  }
  return [...intervals.values()].sort(
    (left, right) => new Date(left.startTime) - new Date(right.startTime),
  )
}
