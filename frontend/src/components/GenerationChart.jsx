import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatTime } from '../utils/time'
import { buildChartData } from '../utils/chartData'

function formatGeneration(value) {
  return value == null
    ? 'No reading'
    : new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip__time">{formatTime(label)}</p>
      {payload.map((item) => (
        <p className="chart-tooltip__row" key={item.dataKey}>
          <span className={`chart-tooltip__dot chart-tooltip__dot--${item.dataKey}`} />
          {item.name}
          <strong>{formatGeneration(item.value)}</strong>
        </p>
      ))}
    </div>
  )
}

export default function GenerationChart({
  actuals,
  forecasts,
  onSelectInterval,
}) {
  const data = buildChartData(actuals, forecasts)

  if (!data.length) {
    return (
      <div className="empty-chart">
        <span className="empty-chart__icon" aria-hidden="true">⌁</span>
        <strong>No interval data for this period</strong>
        <span>Try another date range or check the backend connection.</span>
      </div>
    )
  }

  return (
    <div className="chart-wrap">
      <div
        className="chart-canvas"
        role="img"
        aria-label="Actual wind generation compared with the forecast selected by the backend decision cutoff. Missing observations are shown as gaps."
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={data}
            margin={{ top: 8, right: 12, bottom: 4, left: 0 }}
            onClick={(event) => {
              const time = event?.activePayload?.[0]?.payload?.startTime
              if (time) onSelectInterval(time)
            }}
          >
            <CartesianGrid stroke="#e8edf2" vertical={false} />
            <XAxis
              dataKey="startTime"
              tickFormatter={(value) => formatTime(value, { hour: '2-digit' })}
              minTickGap={34}
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#718096', fontSize: 11 }}
            />
            <YAxis
              width={64}
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#718096', fontSize: 11 }}
              tickFormatter={(value) =>
                new Intl.NumberFormat(undefined, { notation: 'compact' }).format(value)
              }
              label={{
                value: 'Source generation units',
                angle: -90,
                position: 'insideLeft',
                fill: '#718096',
                fontSize: 11,
              }}
            />
            <Tooltip
              content={<ChartTooltip />}
              labelFormatter={(value) => formatTime(value)}
            />
            <Legend
              verticalAlign="top"
              align="right"
              iconType="circle"
              iconSize={7}
              wrapperStyle={{ paddingBottom: 18, fontSize: 12 }}
            />
            <Line
              type="linear"
              dataKey="actual"
              name="Actual generation"
              stroke="#16866a"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, onClick: (_event, payload) => {
                if (payload?.payload?.startTime) onSelectInterval(payload.payload.startTime)
              } }}
              connectNulls={false}
              isAnimationActive={false}
            />
            <Line
              type="linear"
              dataKey="forecast"
              name="Decision-time forecast"
              stroke="#3b75d1"
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="chart-hint">
        Click a chart interval to inspect its forecast publication history.
      </p>
    </div>
  )
}
