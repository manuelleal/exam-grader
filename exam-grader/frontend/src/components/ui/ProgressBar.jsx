import { clsx } from 'clsx'

export function ProgressBar({ value = 0, max = 100, label, showPercent = true, color = 'blue', size = 'md' }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))

  const colors = {
    blue: 'bg-blue-500',
    green: 'bg-green-500',
    yellow: 'bg-yellow-400',
    red: 'bg-red-500',
    purple: 'bg-purple-500',
  }

  const heights = {
    sm: 'h-1.5',
    md: 'h-2.5',
    lg: 'h-4',
  }

  return (
    <div className="w-full space-y-1.5">
      {(label || showPercent) && (
        <div className="flex justify-between items-center">
          {label && <span className="text-sm text-gray-600">{label}</span>}
          {showPercent && (
            <span className="text-sm font-medium text-gray-800">{Math.round(pct)}%</span>
          )}
        </div>
      )}
      <div className={clsx('w-full bg-gray-200 rounded-full overflow-hidden', heights[size])}>
        <div
          className={clsx('rounded-full transition-all duration-300 ease-out', colors[color], heights[size])}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
