import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  BarChart3, Download, ChevronRight, AlertCircle, Loader2,
  TrendingUp, TrendingDown, Users, Award, ArrowUpRight,
  CheckCircle2, XCircle, Clock, AlertTriangle,
} from 'lucide-react'
import Navbar from '../components/Navbar'
import { Card, CardHeader, CardBody } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { sessionsService } from '../services/sessions'

const STATUS_CONFIG = {
  graded: { label: 'Graded', icon: CheckCircle2, color: 'text-green-600 bg-green-50' },
  review_needed: { label: 'Needs Review', icon: AlertTriangle, color: 'text-amber-600 bg-amber-50' },
  pending: { label: 'Pending', icon: Clock, color: 'text-gray-500 bg-gray-100' },
  processing: { label: 'Processing', icon: Loader2, color: 'text-blue-600 bg-blue-50' },
  failed: { label: 'Failed', icon: XCircle, color: 'text-red-600 bg-red-50' },
  error: { label: 'Error', icon: XCircle, color: 'text-red-600 bg-red-50' },
}

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending
  const Icon = cfg.icon
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color}`}>
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  )
}

function ScoreBadge({ score, maxScore }) {
  if (score == null) return <span className="text-gray-400 text-sm">—</span>
  const pct = maxScore > 0 ? (score / maxScore) * 100 : 0
  const color = pct >= 90 ? 'text-green-700' : pct >= 70 ? 'text-blue-700' : pct >= 50 ? 'text-amber-700' : 'text-red-700'
  return (
    <span className={`font-semibold text-sm ${color}`}>
      {score}/{maxScore}
      <span className="font-normal text-gray-400 ml-1">({Math.round(pct)}%)</span>
    </span>
  )
}

function StatCard({ icon: Icon, label, value, sub, color = 'blue' }) {
  const colors = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    amber: 'bg-amber-50 text-amber-600',
    red: 'bg-red-50 text-red-600',
    purple: 'bg-purple-50 text-purple-600',
  }
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-start gap-3">
      <div className={`p-2 rounded-lg ${colors[color]}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-xs text-gray-500">{label}</p>
        <p className="text-xl font-bold text-gray-900">{value ?? '—'}</p>
        {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

export default function SessionResults() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [session, setSession] = useState(null)
  const [exams, setExams] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [exporting, setExporting] = useState(false)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const [sessionData, examsData] = await Promise.all([
          sessionsService.get(id),
          sessionsService.getExams(id),
        ])
        setSession(sessionData)
        const list = Array.isArray(examsData) ? examsData : examsData?.exams ?? examsData?.items ?? []
        setExams(list)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [id])

  const handleExportExcel = async () => {
    setExporting(true)
    try {
      const response = await sessionsService.exportExcel(id)
      const url = URL.createObjectURL(new Blob([response.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `session-${id}-results.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.message)
    } finally {
      setExporting(false)
    }
  }

  const scored = exams.filter((e) => e.score_preview != null)
  const scores = scored.map((e) => {
    const max = e.max_score ?? 100
    return (e.score_preview / max) * 100
  })
  const avg = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null
  const highest = scores.length ? Math.round(Math.max(...scores)) : null
  const lowest = scores.length ? Math.round(Math.min(...scores)) : null

  const reviewNeededCount = exams.filter((e) => e.status === 'review_needed').length
  const errorCount = exams.filter((e) => e.status === 'error').length

  const filtered = exams.filter((e) => {
    const name = (e.student_name ?? '').toLowerCase()
    const matchesSearch = name.includes(search.toLowerCase())
    const matchesStatus = statusFilter === 'all' || e.status === statusFilter
    return matchesSearch && matchesStatus
  })

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Navbar />
        <div className="flex items-center justify-center py-32">
          <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="max-w-5xl mx-auto px-4 py-10">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-8">
          <div>
            <div className="flex items-center gap-2 text-sm text-gray-400 mb-1">
              <Link to="/dashboard" className="hover:text-blue-600 transition-colors">Dashboard</Link>
              <ChevronRight className="w-3.5 h-3.5" />
              <span>Results</span>
            </div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <BarChart3 className="w-6 h-6 text-purple-600" />
              {session?.name ?? `Session #${id}`}
            </h1>
            {session?.created_at && (
              <p className="text-sm text-gray-500 mt-0.5">
                {new Date(session.created_at).toLocaleDateString('en-US', { dateStyle: 'long' })}
              </p>
            )}
          </div>
          <Button onClick={handleExportExcel} loading={exporting} variant="secondary">
            <Download className="w-4 h-4" /> Export Excel
          </Button>
        </div>

        {error && (
          <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 mb-6 text-sm">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-8">
          <StatCard icon={Users} label="Total Exams" value={exams.length} color="blue" />
          <StatCard icon={Award} label="Average Score" value={avg != null ? `${avg}%` : '—'} color="purple" />
          <StatCard icon={TrendingUp} label="Highest" value={highest != null ? `${highest}%` : '—'} color="green" />
          <StatCard icon={TrendingDown} label="Lowest" value={lowest != null ? `${lowest}%` : '—'} color="red" />
          <StatCard icon={AlertTriangle} label="Needs Review" value={reviewNeededCount} color="amber" />
        </div>

        {/* Table */}
        <Card>
          <CardHeader>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <h2 className="font-semibold text-gray-800">Exam Results</h2>
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search student…"
                  className="w-full sm:w-56 px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
                />
              </div>
              {/* Filter tabs */}
              <div className="flex gap-1.5 flex-wrap">
                {[
                  { key: 'all', label: 'All', count: exams.length },
                  { key: 'graded', label: 'Graded', count: exams.filter(e => e.status === 'graded').length },
                  { key: 'review_needed', label: 'Needs Review', count: reviewNeededCount },
                  { key: 'pending', label: 'Pending', count: exams.filter(e => e.status === 'pending' || e.status === 'processing').length },
                  ...(errorCount > 0 ? [{ key: 'error', label: 'Errors', count: errorCount }] : []),
                ].map(({ key, label, count }) => (
                  <button
                    key={key}
                    onClick={() => setStatusFilter(key)}
                    className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                      statusFilter === key
                        ? key === 'review_needed'
                          ? 'bg-amber-500 text-white'
                          : key === 'error'
                          ? 'bg-red-600 text-white'
                          : 'bg-blue-600 text-white'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                  >
                    {key === 'review_needed' && <AlertTriangle className="w-3 h-3" />}
                    {key === 'error' && <XCircle className="w-3 h-3" />}
                    {label}
                    <span className={`px-1.5 py-0.5 rounded-full text-xs ${
                      statusFilter === key ? 'bg-white/20' : 'bg-gray-200 text-gray-500'
                    }`}>{count}</span>
                  </button>
                ))}
              </div>
            </div>
          </CardHeader>

          {filtered.length === 0 ? (
            <CardBody>
              <div className="text-center py-12 text-gray-400">
                <Users className="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p className="font-medium">{search ? 'No students match your search' : 'No exams in this session'}</p>
              </div>
            </CardBody>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100">
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Student</th>
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Score</th>
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                    <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {filtered.map((exam) => {
                    const name = exam.student_name || `Exam #${exam.id}`
                    const maxScore = exam.max_score ?? 100
                    return (
                      <tr
                        key={exam.id}
                        className="hover:bg-gray-50 transition-colors group"
                      >
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-2.5">
                            <div className={`w-8 h-8 rounded-full flex items-center justify-center font-semibold text-xs shrink-0 ${
                              exam.status === 'error' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'
                            }`}>
                              {name.charAt(0).toUpperCase()}
                            </div>
                            <div>
                              <span className="font-medium text-gray-800">{name}</span>
                              {exam.status === 'error' && exam.error_message && (
                                <p className="text-xs text-red-600 mt-0.5 max-w-xs truncate" title={exam.error_message}>
                                  {exam.error_message}
                                </p>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <ScoreBadge score={exam.score_preview} maxScore={maxScore} />
                        </td>
                        <td className="px-6 py-4">
                          <StatusBadge status={exam.status ?? 'graded'} />
                        </td>
                        <td className="px-6 py-4 text-right">
                          <button
                            onClick={() => navigate(`/exams/${exam.id}`)}
                            className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 text-xs font-medium transition-colors opacity-0 group-hover:opacity-100"
                          >
                            View <ArrowUpRight className="w-3.5 h-3.5" />
                          </button>
                          <Link
                            to={`/exams/${exam.id}`}
                            className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 text-xs font-medium transition-colors sm:hidden"
                          >
                            View <ArrowUpRight className="w-3.5 h-3.5" />
                          </Link>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </main>
    </div>
  )
}
