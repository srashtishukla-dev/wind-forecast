export default function MetricCard({ label, value, unit, detail, tone = 'blue' }) {
  return (
    <article className={`metric-card metric-card--${tone}`}>
      <div className="metric-card__top">
        <p className="eyebrow">{label}</p>
        <span className="metric-card__mark" aria-hidden="true" />
      </div>
      <p className="metric-card__value">{value}</p>
      <p className="metric-card__unit">{unit}</p>
      <p className="metric-card__detail">{detail}</p>
    </article>
  )
}
