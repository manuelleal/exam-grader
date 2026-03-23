import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  PlayCircle, ChevronRight, CheckCircle2, AlertCircle, Loader2,
  Users, Zap, Clock,
} from 'lucide-react'
import Navbar from '../components/Navbar'
import { Card, CardHeader, CardBody, CardFooter } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { FileUpload } from '../components/ui/FileUpload'
import { ProgressBar } from '../components/ui/ProgressBar'
import { templatesService } from '../services/templates'
import { sessionsService } from '../services/sessions'

const STEPS = ['Setup', 'Upload Exams', 'Processing', 'Done']

function StepIndicator({ current }) {
  return (
    <div className="flex items-center gap-2 mb-8 flex-wrap">
      {STEPS.map((s, i) => (
        <div key={s} className="flex items-center gap-2">
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-colors ${
            i < current ? 'bg-green-100 text-green-700' :
            i === current ? 'bg-blue-600 text-white' :
            'bg-gray-100 text-gray-400'
          }`}>
            {i < current ? <CheckCircle2 className="w-3.5 h-3.5" /> : <span>{i + 1}</span>}
            {s}
          </div>
          {i < STEPS.length - 1 && <ChevronRight className="w-4 h-4 text-gray-300 shrink-0" />}
        </div>
      ))}
    </div>
  )
}

const STATUS_LABELS = {
  pending: 'Pending',
  processing: 'Processing…',
  completed: 'Completed',
  failed: 'Failed',
}

const STATUS_COLORS = {
  pending: 'text-gray-500',
  processing: 'text-blue-600',
  completed: 'text-green-600',
  failed: 'text-red-600',
}

export default function NewSession() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Step 0 — setup
  const [templates, setTemplates] = useState([])
  const [templatesLoading, setTemplatesLoading] = useState(true)
  const [form, setForm] = useState({ name: '', template_id: '' })

  // Step 1 — upload
  const [session, setSession] = useState(null)
  const [files, setFiles] = useState([])
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadDone, setUploadDone] = useState(false)

  // Step 2 — processing
  const [status, setStatus] = useState(null)
  const [processingProgress, setProcessingProgress] = useState(0)
  const pollRef = useRef(null)

  useEffect(() => {
    setTemplatesLoading(true)
    templatesService.list()
      .then((data) => {
        const list = Array.isArray(data) ? data : data?.items ?? data?.templates ?? []
        setTemplates(list)
        if (list.length > 0) setForm((f) => ({ ...f, template_id: String(list[0].id) }))
      })
      .catch(() => setTemplates([]))
      .finally(() => setTemplatesLoading(false))
  }, [])

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const handleCreateSession = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) { setError('Session name is required'); return }
    if (!form.template_id) { setError('Please select a template'); return }
    setError(null)
    setLoading(true)
    try {
      const created = await sessionsService.create({
        name: form.name,
        template_id: String(form.template_id),
      })
      setSession(created)
      setStep(1)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleUpload = async () => {
    if (!files.length) { setError('Please add at least one exam file'); return }
    setError(null)
    setLoading(true)
    setUploadProgress(0)
    try {
      await sessionsService.uploadExams(session.id, files, (pct) => setUploadProgress(pct))
      setUploadDone(true)
      setUploadProgress(100)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleProcess = async () => {
    setError(null)
    setLoading(true)
    try {
      await sessionsService.process(session.id)
      setStep(2)
      setProcessingProgress(5)
      pollRef.current = setInterval(async () => {
        try {
          const s = await sessionsService.getStatus(session.id)
          setStatus(s)
          const pct = s.total > 0
            ? Math.round((s.processed / s.total) * 100)
            : (s.status === 'completed' ? 100 : processingProgress)
          setProcessingProgress(pct)
          if (s.status === 'completed' || s.status === 'failed') {
            clearInterval(pollRef.current)
            setLoading(false)
            setStep(3)
          }
        } catch {
          // keep polling
        }
      }, 2500)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="max-w-3xl mx-auto px-4 py-10">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <PlayCircle className="w-6 h-6 text-green-600" /> New Grading Session
          </h1>
          <p className="text-gray-500 mt-1">Upload student exams and let AI grade them</p>
        </div>

        <StepIndicator current={step} />

        {error && (
          <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 mb-5 text-sm">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* ── Step 0: Setup ── */}
        {step === 0 && (
          <Card>
            <CardHeader>
              <h2 className="font-semibold text-gray-800">Session Setup</h2>
            </CardHeader>
            <form onSubmit={handleCreateSession}>
              <CardBody className="space-y-5">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">
                    Template <span className="text-red-500">*</span>
                  </label>
                  {templatesLoading ? (
                    <div className="flex items-center gap-2 text-sm text-gray-400 py-2">
                      <Loader2 className="w-4 h-4 animate-spin" /> Loading templates…
                    </div>
                  ) : templates.length === 0 ? (
                    <div className="bg-amber-50 border border-amber-200 text-amber-700 rounded-lg px-3 py-2.5 text-sm">
                      No templates found.{' '}
                      <button
                        type="button"
                        className="underline font-medium"
                        onClick={() => navigate('/templates/new')}
                      >
                        Create one first
                      </button>
                    </div>
                  ) : (
                    <select
                      value={form.template_id}
                      onChange={(e) => setForm({ ...form, template_id: e.target.value })}
                      className="w-full px-3.5 py-2.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition bg-white"
                    >
                      {templates.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name} {t.subject ? `— ${t.subject}` : ''}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">
                    Session Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="e.g. Group A — March 2025"
                    className="w-full px-3.5 py-2.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
                  />
                </div>
              </CardBody>
              <CardFooter className="flex justify-end">
                <Button type="submit" loading={loading} disabled={templates.length === 0}>
                  Create Session <ChevronRight className="w-4 h-4" />
                </Button>
              </CardFooter>
            </form>
          </Card>
        )}

        {/* ── Step 1: Upload ── */}
        {step === 1 && (
          <Card>
            <CardHeader>
              <h2 className="font-semibold text-gray-800">Upload Exam Photos</h2>
              <p className="text-sm text-gray-500 mt-0.5">
                Upload one image per student exam. Multiple files supported.
              </p>
            </CardHeader>
            <CardBody className="space-y-5">
              <FileUpload
                accept="image/*,application/pdf"
                multiple
                files={files}
                onChange={setFiles}
                label="Drop exam photos here or click to browse"
                sublabel="PNG, JPG, WEBP, or PDF (multi-page PDFs will be converted to images)"
                disabled={loading || uploadDone}
              />

              {(loading || uploadDone) && files.length > 0 && (
                <ProgressBar
                  value={uploadProgress}
                  label={uploadDone ? 'Upload complete!' : 'Uploading…'}
                  color={uploadDone ? 'green' : 'blue'}
                />
              )}

              {uploadDone && (
                <div className="bg-green-50 border border-green-200 text-green-700 rounded-xl px-4 py-3 text-sm flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  {files.length} exam{files.length !== 1 ? 's' : ''} uploaded successfully. Ready to process.
                </div>
              )}
            </CardBody>
            <CardFooter className="flex justify-between">
              {!uploadDone ? (
                <>
                  <Button variant="secondary" onClick={() => setStep(0)}>Back</Button>
                  <Button onClick={handleUpload} loading={loading} disabled={!files.length}>
                    Upload Files
                  </Button>
                </>
              ) : (
                <>
                  <div />
                  <Button onClick={handleProcess} loading={loading}>
                    <Zap className="w-4 h-4" /> Start Processing
                  </Button>
                </>
              )}
            </CardFooter>
          </Card>
        )}

        {/* ── Step 2: Processing ── */}
        {step === 2 && (
          <Card>
            <CardBody className="py-12 space-y-6">
              <div className="text-center">
                <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                  <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
                </div>
                <h2 className="text-lg font-bold text-gray-900">Grading in progress…</h2>
                <p className="text-sm text-gray-500 mt-1">
                  {status?.current_processing
                    ? `Processing: ${status.current_processing}`
                    : 'AI is analyzing and grading each exam.'}
                </p>
              </div>

              <ProgressBar
                value={status?.progress_percentage ?? processingProgress}
                label="Processing exams"
                color="blue"
                size="lg"
              />

              {status && (
                <div className="grid grid-cols-4 gap-3 mt-4">
                  {[
                    { icon: Users, label: 'Total', value: status.total ?? '—' },
                    { icon: CheckCircle2, label: 'Graded', value: status.processed ?? '—' },
                    { icon: Clock, label: 'Remaining', value: status.pending ?? '—' },
                    { icon: Zap, label: 'ETA', value: status.estimated_time_remaining != null ? `~${status.estimated_time_remaining}s` : '—' },
                  ].map(({ icon: Icon, label, value }) => (
                    <div key={label} className="bg-gray-50 rounded-xl p-3 text-center border border-gray-200">
                      <Icon className="w-4 h-4 text-gray-400 mx-auto mb-1" />
                      <p className="text-lg font-bold text-gray-800">{value}</p>
                      <p className="text-xs text-gray-500">{label}</p>
                    </div>
                  ))}
                </div>
              )}

              {status?.errors?.length > 0 && (
                <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3">
                  <p className="text-sm font-medium text-red-700 mb-2 flex items-center gap-1.5">
                    <AlertCircle className="w-4 h-4" />
                    {status.errors.length} exam{status.errors.length !== 1 ? 's' : ''} failed
                  </p>
                  <ul className="space-y-1">
                    {status.errors.map((e) => (
                      <li key={e.exam_id} className="text-xs text-red-600">
                        <span className="font-medium">{e.student_name || e.exam_id}:</span> {e.error}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </CardBody>
          </Card>
        )}

        {/* ── Step 3: Done ── */}
        {step === 3 && (
          <Card>
            <CardBody className="flex flex-col items-center py-16 text-center">
              {status?.status === 'failed' ? (
                <>
                  <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mb-4">
                    <AlertCircle className="w-8 h-8 text-red-600" />
                  </div>
                  <h2 className="text-xl font-bold text-gray-900 mb-2">Processing Failed</h2>
                  <p className="text-gray-500 mb-8">{status?.error || 'An error occurred during processing.'}</p>
                  <Button onClick={() => navigate('/dashboard')}>Back to Dashboard</Button>
                </>
              ) : (
                <>
                  <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mb-4">
                    <CheckCircle2 className="w-8 h-8 text-green-600" />
                  </div>
                  <h2 className="text-xl font-bold text-gray-900 mb-2">
                    {status?.failed > 0 ? 'Grading Complete (with errors)' : 'All Exams Graded!'}
                  </h2>
                  <p className="text-gray-500 mb-1">
                    Session <span className="font-medium text-gray-700">{session?.name}</span> is complete.
                  </p>
                  {status?.failed > 0 && (
                    <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 mb-4 text-sm text-red-700 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 shrink-0" />
                      {status.failed} exam{status.failed !== 1 ? 's' : ''} failed — check the results page for details.
                    </div>
                  )}
                  <p className="text-sm text-gray-400 mb-8">Review results, export to Excel, or view individual exams.</p>
                  <Button onClick={() => navigate(`/sessions/${session?.id}`)}>
                    View Results <ChevronRight className="w-4 h-4" />
                  </Button>
                </>
              )}
            </CardBody>
          </Card>
        )}
      </main>
    </div>
  )
}
