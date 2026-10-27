import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  dashboardApiBaseUrl,
  fetchDashboard,
  fetchForecastVersions,
  fetchHealth,
} from './api/client'
import ForecastHistory from './components/ForecastHistory'
import MetricCard from './components/MetricCard'
import { buildChartData } from './utils/chartData'
import { formatTime } from './utils/time'
import './App.css'

const GenerationChart = lazy(() => import('./components/GenerationChart'))

const INITIAL_FILTERS = {
  startDate: '2026-01-01',
  endDate: '2026-01-31',
  decisionLeadHours: '24',
}

function formatMetric(value) {
  return value == null
    ? 'N/A'
    : new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)
}

function dateSpan(startDate, endDate) {
  const start = Date.parse(`${startDate}T00:00:00Z`)
  const end = Date.parse(`${endDate}T00:00:00Z`)
  return (end - start) / 86_400_000
}

function validateFilters(filters) {
  if (!filters.startDate || !filters.endDate) {
    return 'Choose both a start date and an end date.'
  }
  if (filters.startDate > filters.endDate) {
    return 'The start date must be on or before the end date.'
  }
  if (dateSpan(filters.startDate, filters.endDate) >= 31) {
    return 'Choose a period of 31 days or less.'
  }
  const lead = Number(filters.decisionLeadHours)
  if (!Number.isFinite(lead) || lead < 0 || lead > 720) {
    return 'Decision lead must be between 0 and 720 hours.'
  }
  return ''
}

function Icon({ name }) {
  const paths = {
    wind: <><path d="M3 8h13a3 3 0 1 0-3-3" /><path d="M2 12h17a3 3 0 1 1-3 3" /><path d="M4 16h6" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    refresh: <><path d="M20 7v5h-5" /><path d="M4 17v-5h5" /><path d="M5.5 9A7 7 0 0 1 18 6l2 2M4 16l2 2a7 7 0 0 0 12.5-3" /></>,
    chart: <><path d="M3 3v18h18" /><path d="m7 14 4-4 4 3 6-7" /></>,
    layers: <><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5M3 16l9 5 9-5" /></>,
    check: <><path d="m5 12 4 4L19 6" /><circle cx="12" cy="12" r="10" /></>,
  }

  return (
    <svg
      aria-hidden="true"
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  )
}

function App() {
  const [draftFilters, setDraftFilters] = useState(INITIAL_FILTERS)
  const [appliedFilters, setAppliedFilters] = useState(null)
  const [actuals, setActuals] = useState(null)
  const [accuracy, setAccuracy] = useState(null)
  const [selectedInterval, setSelectedInterval] = useState('')
  const [versions, setVersions] = useState([])
  const [versionQuality, setVersionQuality] = useState(null)
  const [loading, setLoading] = useState(false)
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [error, setError] = useState('')
  const [versionsError, setVersionsError] = useState('')
  const [filterError, setFilterError] = useState('')
  const [apiStatus, setApiStatus] = useState('checking')
  const [apiStatusMessage, setApiStatusMessage] = useState('')
  const dashboardController = useRef(null)
  const versionController = useRef(null)
  const requestId = useRef(0)

  const loadVersions = useCallback(async (interval, publication) => {
    versionController.current?.abort()
    if (!interval || !publication) {
      setVersions([])
      setVersionQuality(null)
      setVersionsError('')
      setVersionsLoading(false)
      return
    }

    const controller = new AbortController()
    versionController.current = controller
    setVersionsLoading(true)
    setVersionsError('')
    try {
      const result = await fetchForecastVersions(interval, publication, controller.signal)
      setVersions(result.records)
      setVersionQuality(result.quality)
    } catch (loadError) {
      if (loadError.name !== 'AbortError') {
        setVersions([])
        setVersionQuality(null)
        setVersionsError(loadError.message)
      }
    } finally {
      if (!controller.signal.aborted) setVersionsLoading(false)
    }
  }, [])

  const refreshDashboard = useCallback(async (filters) => {
    const validationMessage = validateFilters(filters)
    if (validationMessage) {
      setFilterError(validationMessage)
      return
    }

    setFilterError('')
    dashboardController.current?.abort()
    versionController.current?.abort()
    const controller = new AbortController()
    dashboardController.current = controller
    const currentRequest = ++requestId.current
    setLoading(true)
    setError('')
    setActuals(null)
    setAccuracy(null)
    setVersions([])
    setSelectedInterval('')
    setVersionQuality(null)
    setVersionsError('')

    try {
      const result = await fetchDashboard(filters, controller.signal)
      if (currentRequest !== requestId.current) return
      setActuals(result.actuals)
      setAccuracy(result.accuracy)
      setAppliedFilters(filters)
      const intervals = buildChartData(
        result.actuals.records,
        result.accuracy.selected_forecasts,
      )
      const initialInterval =
        result.accuracy.selected_forecasts[0]?.startTime ||
        intervals[0]?.startTime ||
        ''
      setSelectedInterval(initialInterval)
      if (initialInterval) {
        void loadVersions(initialInterval, result.publication)
      }
    } catch (loadError) {
      if (loadError.name !== 'AbortError' && currentRequest === requestId.current) {
        setError(loadError.message)
      }
    } finally {
      if (currentRequest === requestId.current) setLoading(false)
    }
  }, [loadVersions])

  useEffect(() => {
    void refreshDashboard(INITIAL_FILTERS)
    return () => {
      dashboardController.current?.abort()
      versionController.current?.abort()
    }
  }, [refreshDashboard])

  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal)
      .then(() => {
        setApiStatus('online')
        setApiStatusMessage('')
      })
      .catch((healthError) => {
        if (healthError.name !== 'AbortError') {
          setApiStatus('offline')
          setApiStatusMessage(healthError.message)
        }
      })
    return () => controller.abort()
  }, [])

  const chartIntervals = useMemo(
    () => buildChartData(actuals?.records || [], accuracy?.selected_forecasts || []),
    [actuals, accuracy],
  )

  const handleApply = (event) => {
    event.preventDefault()
    void refreshDashboard(draftFilters)
  }

  const updateDraftFilter = (key, value) => {
    setDraftFilters((current) => ({ ...current, [key]: value }))
    setFilterError('')
  }

  const handleIntervalSelect = (interval) => {
    setSelectedInterval(interval)
    if (accuracy) {
      loadVersions(interval, {
        publish_from: accuracy.publication_window_start,
        publish_to: accuracy.publication_window_end,
      })
    }
  }

  const metricUnits = accuracy?.units || 'Elexon generation units'
  const excluded = accuracy?.excluded_records
  const validActuals = actuals
    ? Math.max(0, actuals.records.length - actuals.incomplete_intervals)
    : 0
  const validSelectedForecasts = accuracy
    ? accuracy.selected_forecasts.filter((record) => record.forecastGeneration != null).length
    : 0
  const periodLabel = appliedFilters
    ? `${appliedFilters.startDate} — ${appliedFilters.endDate}`
    : 'January 2026'

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#" aria-label="UK Wind Forecast Analytics home">
          <span className="brand__mark"><Icon name="wind" /></span>
          <span className="brand__name">Grid<span>bricks</span></span>
        </a>
        <div className="topbar__right">
          <span className="topbar__product">Wind analytics</span>
          <span className={`connection connection--${apiStatus}`}>
            <span className="connection__dot" />
            {apiStatus === 'checking'
              ? 'Checking API'
              : apiStatus === 'online'
                ? 'Backend connected'
                : 'Backend unavailable'}
          </span>
        </div>
      </header>

      <main className="page">
        <section className="intro">
          <div className="intro__copy">
            <div className="breadcrumb"><span>Analytics</span><span>/</span><strong>Wind forecast</strong></div>
            <div className="intro__title-row">
              <span className="intro__icon"><Icon name="wind" /></span>
              <div>
                <h1>UK Wind Forecast Analytics</h1>
                <p>Compare published wind forecasts with actual generation across delivery intervals.</p>
              </div>
            </div>
          </div>
          <div className="period-summary">
            <span className="eyebrow">Analysis period</span>
            <strong><Icon name="calendar" />{periodLabel}</strong>
            <span>All timestamps shown in UTC</span>
          </div>
        </section>

        <form className="filter-panel" onSubmit={handleApply} noValidate>
          <div className="filter-panel__heading">
            <div>
              <p className="eyebrow">Analysis controls</p>
              <h2>Choose a delivery period</h2>
            </div>
            <span className="filter-note"><Icon name="check" /> Up to 31 days per request</span>
          </div>
          <div className="filter-controls">
            <label className="field">
              <span>Start date</span>
              <input
                type="date"
                value={draftFilters.startDate}
                onChange={(event) => updateDraftFilter('startDate', event.target.value)}
                required
              />
            </label>
            <span className="date-arrow" aria-hidden="true">→</span>
            <label className="field">
              <span>End date <small>(inclusive)</small></span>
              <input
                type="date"
                value={draftFilters.endDate}
                onChange={(event) => updateDraftFilter('endDate', event.target.value)}
                required
              />
            </label>
            <label className="field field--lead">
              <span>Decision lead</span>
              <span className="input-suffix">
                <input
                  type="number"
                  min="0"
                  max="720"
                  step="0.5"
                  value={draftFilters.decisionLeadHours}
                  onChange={(event) => updateDraftFilter('decisionLeadHours', event.target.value)}
                  required
                />
                <span>hours</span>
              </span>
            </label>
            <button className="apply-button" type="submit" disabled={loading}>
              {loading ? <span className="spinner spinner--light" /> : <Icon name="refresh" />}
              {loading ? 'Loading data' : 'Apply filters'}
            </button>
          </div>
          <p className="filter-help">
            Date boundaries are sent as UTC. The cutoff is an analysis assumption, not an official market deadline.
          </p>
          {filterError && <p className="form-error" role="alert">{filterError}</p>}
        </form>

        {apiStatus === 'offline' && (
          <div className="alert alert--error" role="alert">
            <strong>Backend connection failed.</strong> {apiStatusMessage}
          </div>
        )}
        {error && (
          <div className="alert alert--error" role="alert">
            <strong>Could not load analytics.</strong> {error}
            <span> No sample values are being displayed. Check the backend and Elexon connection, then retry.</span>
          </div>
        )}

        <section className="metrics-section" aria-labelledby="accuracy-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Forecast performance</p>
              <h2 id="accuracy-title">Accuracy at decision time</h2>
            </div>
            <span className="unit-tag">{metricUnits}</span>
          </div>
          <div className="metric-grid">
            <MetricCard
              label="Mean absolute error"
              value={accuracy ? formatMetric(accuracy.mae) : '—'}
              unit={metricUnits}
              detail="Average size of forecast error"
              tone="blue"
            />
            <MetricCard
              label="Root mean squared error"
              value={accuracy ? formatMetric(accuracy.rmse) : '—'}
              unit={metricUnits}
              detail="Penalizes larger forecast misses"
              tone="teal"
            />
            <MetricCard
              label="Forecast bias"
              value={accuracy ? formatMetric(accuracy.bias) : '—'}
              unit={metricUnits}
              detail={
                accuracy?.bias == null
                  ? 'Mean forecast − actual'
                  : accuracy.bias > 0
                    ? 'Positive: overforecasting'
                    : accuracy.bias < 0
                      ? 'Negative: underforecasting'
                      : 'No average directional error'
              }
              tone="amber"
            />
            <MetricCard
              label="Matched intervals"
              value={accuracy ? new Intl.NumberFormat().format(accuracy.matched_observations) : '—'}
              unit="valid forecast / actual pairs"
              detail="Same delivery start, both values present"
              tone="green"
            />
          </div>
          {accuracy && accuracy.matched_observations === 0 && (
            <p className="notice" role="status">
              No valid matched observations were available for the selected period and cutoff. Metrics are shown as N/A, not zero.
            </p>
          )}
        </section>

        <section className="panel chart-panel" aria-labelledby="chart-title">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Generation profile</p>
              <h2 id="chart-title">Actual vs. decision-time forecast</h2>
              <p className="panel-subtitle">
                Delivery intervals matched by start time · latest forecast published by cutoff
              </p>
            </div>
            {accuracy && (
              <div className="lead-badge">
                <span>Cutoff</span>
                <strong>{accuracy.decision_lead_hours}h before delivery</strong>
              </div>
            )}
          </div>
          {loading && !actuals ? (
            <div className="table-state table-state--large" role="status">
              <span className="spinner" /> Fetching actuals and eligible forecast vintages…
            </div>
          ) : (
            <Suspense fallback={<div className="table-state table-state--large" role="status">Loading chart…</div>}>
              <GenerationChart
                actuals={actuals?.records || []}
                forecasts={accuracy?.selected_forecasts || []}
                onSelectInterval={handleIntervalSelect}
              />
            </Suspense>
          )}
          <div className="chart-footnote">
            <span>FUELHH actuals are documented as half-hour average MW. WINDFOR does not state its unit in the verified schema; chart values use source units and are not labelled MW.</span>
          </div>
        </section>

        <div className="lower-grid">
          <ForecastHistory
            intervals={chartIntervals.map((record) => record.startTime)}
            selectedInterval={selectedInterval}
            onSelectInterval={handleIntervalSelect}
            records={versions}
            quality={versionQuality}
            loading={versionsLoading}
            error={versionsError}
          />

          <section className="panel quality-panel" aria-labelledby="quality-title">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Source reliability</p>
                <h2 id="quality-title">Data quality & coverage</h2>
              </div>
              <span className="quality-icon"><Icon name="layers" /></span>
            </div>
            <div className="quality-list">
              <div className="quality-row">
                <span><i className="quality-dot quality-dot--good" />Valid actual records</span>
                <strong>{actuals ? validActuals.toLocaleString() : '—'}</strong>
              </div>
              <div className="quality-row">
                <span><i className="quality-dot quality-dot--good" />Valid selected forecasts</span>
                <strong>{accuracy ? validSelectedForecasts.toLocaleString() : '—'}</strong>
              </div>
              <div className="quality-row">
                <span><i className="quality-dot quality-dot--warn" />Missing actual generations</span>
                <strong>{actuals?.quality.missing_generation_records ?? '—'}</strong>
              </div>
              <div className="quality-row">
                <span><i className="quality-dot quality-dot--bad" />Invalid actual generations</span>
                <strong>{excluded?.invalid_actual_generations ?? '—'}</strong>
              </div>
              <div className="quality-row">
                <span><i className="quality-dot quality-dot--warn" />Missing selected forecasts</span>
                <strong>
                  {accuracy
                    ? accuracy.selected_forecasts.filter((record) => record.forecastGeneration == null).length
                      - excluded.invalid_forecast_generations
                    : '—'}
                </strong>
              </div>
              <div className="quality-row">
                <span><i className="quality-dot quality-dot--bad" />Invalid selected forecasts</span>
                <strong>{excluded?.invalid_forecast_generations ?? '—'}</strong>
              </div>
              <div className="quality-row">
                <span><i className="quality-dot quality-dot--warn" />Incomplete matched intervals</span>
                <strong>{excluded?.incomplete_matched_intervals ?? '—'}</strong>
              </div>
              <div className="quality-row">
                <span><i className="quality-dot quality-dot--bad" />Invalid source timestamps</span>
                <strong>
                  {excluded
                    ? (excluded.invalid_actual_timestamps + excluded.invalid_forecast_timestamps).toLocaleString()
                    : '—'}
                </strong>
              </div>
              <div className="quality-row">
                <span><i className="quality-dot quality-dot--muted" />Unmatched actual / forecast</span>
                <strong>
                  {excluded
                    ? `${excluded.unmatched_actual_records} / ${excluded.unmatched_forecast_records}`
                    : '—'}
                </strong>
              </div>
            </div>
            <p className="quality-note">
              Zero is a valid measurement. Missing values stay missing; chart gaps are not interpolated.
            </p>
          </section>
        </div>

        {accuracy && (
          <aside className="coverage-note">
            <span className="coverage-note__icon"><Icon name="chart" /></span>
            <p>
              <strong>Forecast history coverage</strong>
              {' '}This view includes vintages published from{' '}
              <code>{formatTime(accuracy.publication_window_start)}</code> through{' '}
              <code>{formatTime(accuracy.publication_window_end)}</code> (end exclusive).
              Forecasts outside this requested window are not included. Decision-time forecasts are selected by the backend.
            </p>
          </aside>
        )}

        <footer className="page-footer">
          <span>UK Wind Forecast Analytics</span>
          <span>API: {dashboardApiBaseUrl}</span>
          <span>Data displayed as returned by the backend · timestamps in UTC</span>
        </footer>
      </main>
    </div>
  )
}

export default App
