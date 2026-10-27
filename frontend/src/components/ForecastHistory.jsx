import { formatTime } from '../utils/time'

export default function ForecastHistory({
  intervals,
  selectedInterval,
  onSelectInterval,
  records,
  quality,
  loading,
  error,
}) {
  return (
    <section className="panel history-panel" aria-labelledby="history-title">
      <div className="panel-heading panel-heading--stack">
        <div>
          <p className="eyebrow">Publication trail</p>
          <h2 id="history-title">Forecast version history</h2>
        </div>
        <label className="interval-picker">
          <span>Delivery interval</span>
          <select
            value={selectedInterval}
            onChange={(event) => onSelectInterval(event.target.value)}
            disabled={!intervals.length}
          >
            {intervals.map((interval) => (
              <option key={interval} value={interval}>
                {formatTime(interval)}
              </option>
            ))}
            {!intervals.length && <option value="">No delivery intervals</option>}
          </select>
        </label>
      </div>

      {error && <div className="inline-error" role="alert">{error}</div>}
      {loading && (
        <div className="table-state" role="status">
          <span className="spinner" aria-hidden="true" />
          Loading forecast vintages…
        </div>
      )}
      {!loading && !error && !records.length && (
        <div className="table-state">
          No forecast publications were returned for this interval and publication window.
        </div>
      )}
      {!loading && !error && records.length > 0 && (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Published (UTC)</th>
                  <th scope="col">Delivery start (UTC)</th>
                  <th scope="col" className="align-right">Forecast (source units)</th>
                </tr>
              </thead>
              <tbody>
                {records.map((record) => (
                  <tr key={`${record.startTime}-${record.publishTime}`}>
                    <td>{formatTime(record.publishTime)}</td>
                    <td>{formatTime(record.startTime)}</td>
                    <td className="align-right">
                      {record.forecastGeneration == null
                        ? <span className="missing-value">Missing</span>
                        : new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 })
                          .format(record.forecastGeneration)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="history-footer">
            <span>{records.length} publication versions</span>
            {quality && (
              <span>
                {quality.missing_generation_records} missing ·{' '}
                {quality.invalid_generation_records} invalid
              </span>
            )}
          </div>
        </>
      )}
    </section>
  )
}
