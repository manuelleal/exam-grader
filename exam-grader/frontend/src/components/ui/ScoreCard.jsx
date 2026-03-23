import { clsx } from 'clsx'

function scoreColor(pct) {
  if (pct >= 90) return { bar: 'bg-green-500', text: 'text-green-700', bg: 'bg-green-50', border: 'border-green-200' }
  if (pct >= 70) return { bar: 'bg-blue-500', text: 'text-blue-700', bg: 'bg-blue-50', border: 'border-blue-200' }
  if (pct >= 50) return { bar: 'bg-yellow-400', text: 'text-yellow-700', bg: 'bg-yellow-50', border: 'border-yellow-200' }
  return { bar: 'bg-red-500', text: 'text-red-700', bg: 'bg-red-50', border: 'border-red-200' }
}

export function ScoreCard({ label, score, maxScore, className }) {
  const pct = maxScore > 0 ? Math.round((score / maxScore) * 100) : 0
  const c = scoreColor(pct)

  return (
    <div className={clsx('rounded-xl border p-4', c.bg, c.border, className)}>
      <div className="flex items-start justify-between mb-2">
        <span className="text-sm font-medium text-gray-700">{label}</span>
        <span className={clsx('text-sm font-bold', c.text)}>
          {score}/{maxScore}
        </span>
      </div>
      <div className="h-2 bg-white/60 rounded-full overflow-hidden">
        <div
          className={clsx('h-2 rounded-full transition-all duration-500', c.bar)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className={clsx('text-xs mt-1.5 font-semibold', c.text)}>{pct}%</p>
    </div>
  )
}

export function ScoreGrid({ sections = [] }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
      {sections.map((s, i) => (
        <ScoreCard
          key={i}
          label={s.label || s.name || `Section ${i + 1}`}
          score={s.score ?? s.earned ?? 0}
          maxScore={s.maxScore ?? s.total ?? s.max ?? 1}
        />
      ))}
    </div>
  )
}
