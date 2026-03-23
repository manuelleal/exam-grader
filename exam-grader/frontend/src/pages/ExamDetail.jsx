import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ClipboardList, ChevronRight, ChevronLeft, AlertCircle, Loader2,
  Download, Edit3, BookOpen, Target, Lightbulb,
  CheckCircle2, XCircle, Image as ImageIcon, AlertTriangle, Check, Eye,
} from 'lucide-react'
import Navbar from '../components/Navbar'
import { Card, CardHeader, CardBody } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Modal } from '../components/ui/Modal'
import { ScoreGrid } from '../components/ui/ScoreCard'
import { examsService } from '../services/sessions'

function ImageCarousel({ images = [] }) {
  const [current, setCurrent] = useState(0)

  if (!images.length) {
    return (
      <div className="flex flex-col items-center justify-center bg-gray-100 rounded-xl h-48 border border-gray-200">
        <ImageIcon className="w-10 h-10 text-gray-300 mb-2" />
        <p className="text-sm text-gray-400">No images available</p>
      </div>
    )
  }

  return (
    <div className="relative">
      <div className="rounded-xl overflow-hidden border border-gray-200 bg-gray-50">
        <img
          src={images[current]}
          alt={`Exam page ${current + 1}`}
          className="w-full object-contain max-h-96"
          onError={(e) => { e.currentTarget.style.display = 'none' }}
        />
      </div>
      {images.length > 1 && (
        <div className="flex items-center justify-center gap-3 mt-3">
          <button
            onClick={() => setCurrent((c) => Math.max(0, c - 1))}
            disabled={current === 0}
            className="p-1.5 rounded-lg border border-gray-200 hover:bg-gray-100 disabled:opacity-30 transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-xs text-gray-500 font-medium">{current + 1} / {images.length}</span>
          <button
            onClick={() => setCurrent((c) => Math.min(images.length - 1, c + 1))}
            disabled={current === images.length - 1}
            className="p-1.5 rounded-lg border border-gray-200 hover:bg-gray-100 disabled:opacity-30 transition-colors"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  )
}

function getAnswerValue(answer) {
  if (answer === null || answer === undefined) return null
  if (typeof answer === 'object') return answer.value ?? null
  return answer
}

function getAnswerConfidence(answer) {
  if (answer === null || answer === undefined) return 'high'
  if (typeof answer === 'object') return answer.confidence ?? 'high'
  return 'high'
}

const CONFIDENCE_STYLE = {
  high:   { dot: 'bg-green-400',  text: '' },
  medium: { dot: 'bg-amber-400',  text: 'text-amber-600' },
  low:    { dot: 'bg-red-400',    text: 'text-red-600' },
}

function AnswerRow({ question, answer }) {
  const value = getAnswerValue(answer)
  const confidence = getAnswerConfidence(answer)
  const style = CONFIDENCE_STYLE[confidence] ?? CONFIDENCE_STYLE.high
  const isReviewed = typeof answer === 'object' && answer?.reviewed_by_teacher

  return (
    <div className={`flex items-center gap-3 px-4 py-2.5 rounded-lg border ${
      confidence === 'low' && !isReviewed
        ? 'bg-amber-50 border-amber-200'
        : 'bg-gray-50 border-gray-200'
    }`}>
      <span className="text-xs font-semibold text-gray-500 w-12 shrink-0">{question}</span>
      <span className={`text-sm font-medium flex-1 ${
        confidence === 'low' && !isReviewed ? 'text-amber-800' : 'text-gray-800'
      }`}>{value ?? '—'}</span>
      {confidence !== 'high' && !isReviewed && (
        <span className={`inline-flex items-center gap-1 text-xs font-medium ${style.text}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
          {confidence}
        </span>
      )}
      {isReviewed && (
        <span className="inline-flex items-center gap-1 text-xs text-green-600">
          <Check className="w-3 h-3" /> reviewed
        </span>
      )}
    </div>
  )
}

function ImprovementPlan({ plan }) {
  if (!plan) return null

  const inner = plan.plan ?? plan
  const overview = inner.overview ?? inner.summary ?? inner.general_feedback
  const topics = inner.topics ?? inner.weak_areas ?? inner.areas_to_improve ?? []
  const recommendations = inner.recommendations ?? inner.suggestions ?? []
  const resources = inner.resources ?? inner.study_materials ?? []

  return (
    <div className="space-y-5">
      {overview && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
          <p className="text-sm font-semibold text-blue-800 mb-1 flex items-center gap-1.5">
            <Target className="w-4 h-4" /> Overview
          </p>
          <p className="text-sm text-blue-700">{typeof overview === 'string' ? overview : JSON.stringify(overview)}</p>
        </div>
      )}

      {topics.length > 0 && (
        <div>
          <p className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1.5">
            <BookOpen className="w-4 h-4 text-amber-500" /> Topics to Review
          </p>
          <ul className="space-y-1.5">
            {topics.map((t, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                <span className="w-5 h-5 rounded-full bg-amber-100 text-amber-700 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">{i + 1}</span>
                {typeof t === 'string' ? t : t.name ?? t.topic ?? JSON.stringify(t)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {recommendations.length > 0 && (
        <div>
          <p className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1.5">
            <Lightbulb className="w-4 h-4 text-yellow-500" /> Recommendations
          </p>
          <ul className="space-y-1.5">
            {recommendations.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
                <span className="text-yellow-500 mt-0.5">•</span>
                {typeof r === 'string' ? r : r.text ?? r.recommendation ?? JSON.stringify(r)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {resources.length > 0 && (
        <div>
          <p className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1.5">
            <BookOpen className="w-4 h-4 text-purple-500" /> Study Resources
          </p>
          <ul className="space-y-1.5">
            {resources.map((r, i) => (
              <li key={i} className="text-sm text-gray-600 flex items-start gap-2">
                <span className="text-purple-400 mt-0.5">•</span>
                {typeof r === 'string' ? r : r.title ?? r.name ?? JSON.stringify(r)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {!overview && !topics.length && !recommendations.length && (
        <pre className="text-xs text-gray-600 bg-gray-50 rounded-xl p-4 border border-gray-200 overflow-auto whitespace-pre-wrap max-h-80">
          {JSON.stringify(inner, null, 2)}
        </pre>
      )}
    </div>
  )
}

const EMPTY_CORRECTION = { questionId: '', originalScore: '', correctedScore: '', reason: '' }

export default function ExamDetail() {
  const { id } = useParams()
  const [exam, setExam] = useState(null)
  const [result, setResult] = useState(null)
  const [plan, setPlan] = useState(null)
  const [loading, setLoading] = useState(true)
  const [planLoading, setPlanLoading] = useState(false)
  const [error, setError] = useState(null)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [correctModalOpen, setCorrectModalOpen] = useState(false)
  const [correctForm, setCorrectForm] = useState(EMPTY_CORRECTION)
  const [correctLoading, setCorrectLoading] = useState(false)
  const [correctError, setCorrectError] = useState(null)
  const [correctSuccess, setCorrectSuccess] = useState(false)
  // Review state
  const [reviewDecisions, setReviewDecisions] = useState({}) // { q_id: { mode: 'accept'|'correct', value: string } }
  const [reviewSubmitting, setReviewSubmitting] = useState(false)
  const [reviewError, setReviewError] = useState(null)
  const [reviewSuccess, setReviewSuccess] = useState(false)
  // Edit answers state
  const [isEditingAnswers, setIsEditingAnswers] = useState(false)
  const [editedAnswers, setEditedAnswers] = useState({})
  const [editSaving, setEditSaving] = useState(false)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const examData = await examsService.get(id)
        setExam(examData)
        if (examData?.extracted_answers_json) {
          setEditedAnswers(examData.extracted_answers_json)
        }
        try {
          const resultData = await examsService.getResult(id)
          setResult(resultData)
        } catch {
          // result may not exist yet if not graded
        }
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [id])

  const reloadExam = async () => {
    try {
      const [examData, resultData] = await Promise.allSettled([
        examsService.get(id),
        examsService.getResult(id),
      ])
      if (examData.status === 'fulfilled') {
        setExam(examData.value)
        if (examData.value?.extracted_answers_json) {
          setEditedAnswers(examData.value.extracted_answers_json)
        }
      }
      if (resultData.status === 'fulfilled') setResult(resultData.value)
    } catch {}
  }

  const handleSaveAnswers = async () => {
    setEditSaving(true)
    setError(null)
    try {
      await examsService.updateExtractedAnswers(id, editedAnswers)
      await examsService.regrade(id)
      await reloadExam()
      setIsEditingAnswers(false)
    } catch (err) {
      setError(err.message || 'Failed to update answers')
    } finally {
      setEditSaving(false)
    }
  }

  const handleReviewDecision = (qId, mode, value) => {
    setReviewDecisions((prev) => ({ ...prev, [qId]: { mode, value } }))
  }

  const handleSubmitReview = async () => {
    const answersDict = exam?.extracted_answers_json ?? {}
    const lowConfidenceQs = Object.entries(answersDict).filter(
      ([, a]) => typeof a === 'object' && a?.confidence === 'low'
    )
    // Build corrections map
    const corrections = {}
    for (const [qId, ans] of lowConfidenceQs) {
      const decision = reviewDecisions[qId]
      if (decision?.mode === 'accept') {
        corrections[qId] = ans?.value ?? null
      } else if (decision?.mode === 'correct') {
        corrections[qId] = decision.value ?? null
      } else {
        // Not yet decided — use extracted value
        corrections[qId] = ans?.value ?? null
      }
    }
    setReviewError(null)
    setReviewSubmitting(true)
    try {
      await examsService.reviewAnswers(id, corrections)
      setReviewSuccess(true)
      await reloadExam()
    } catch (err) {
      setReviewError(err.message)
    } finally {
      setReviewSubmitting(false)
    }
  }

  const loadPlan = async () => {
    if (plan) return
    setPlanLoading(true)
    try {
      const data = await examsService.getImprovementPlan(id)
      setPlan(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setPlanLoading(false)
    }
  }

  const handleDownloadPdf = async () => {
    setPdfLoading(true)
    try {
      const response = await examsService.downloadPdf(id)
      const url = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }))
      const a = document.createElement('a')
      a.href = url
      a.download = `improvement-plan-exam-${id}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.message)
    } finally {
      setPdfLoading(false)
    }
  }

  const handleCorrectScore = async (e) => {
    e.preventDefault()
    if (!correctForm.questionId.trim()) { setCorrectError('Question ID is required'); return }
    if (!correctForm.originalScore.trim()) { setCorrectError('Original score is required'); return }
    if (!correctForm.correctedScore.trim()) { setCorrectError('Corrected score is required'); return }
    if (!correctForm.reason.trim()) { setCorrectError('Reason is required'); return }
    setCorrectError(null)
    setCorrectLoading(true)
    try {
      const corrections = {
        [correctForm.questionId]: {
          original_score: parseFloat(correctForm.originalScore),
          corrected_score: parseFloat(correctForm.correctedScore),
          reason: correctForm.reason,
        },
      }
      const updated = await examsService.correctScore(result.id, corrections)
      setResult((prev) => ({ ...prev, final_score: updated.final_score, percentage: updated.percentage }))
      setCorrectSuccess(true)
      setTimeout(() => { setCorrectModalOpen(false); setCorrectSuccess(false); setCorrectForm(EMPTY_CORRECTION) }, 1500)
    } catch (err) {
      setCorrectError(err.message)
    } finally {
      setCorrectLoading(false)
    }
  }

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

  if (error && !exam) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Navbar />
        <div className="max-w-3xl mx-auto px-4 py-16 text-center">
          <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-gray-800 mb-2">Failed to load exam</h2>
          <p className="text-gray-500">{error}</p>
        </div>
      </div>
    )
  }

  const studentName = exam?.student_name || `Exam #${id}`
  const images = exam?.image_urls ?? []
  const answersDict = exam?.extracted_answers_json ?? {}
  const answerEntries = Object.entries(answersDict)
  const lowConfidenceEntries = answerEntries.filter(
    ([, a]) => typeof a === 'object' && a?.confidence === 'low' && !a?.reviewed_by_teacher
  )
  const isReviewNeeded = exam?.status === 'review_needed'
  const sessionId = exam?.session_id

  const finalScore = result?.final_score ?? result?.total_score
  const maxScore = result?.max_score ?? 100
  const pct = finalScore != null && maxScore > 0 ? Math.round((finalScore / maxScore) * 100) : null

  // Convert section_scores_json: { "Section": { earned, max } } → ScoreGrid format
  const sectionScores = result?.section_scores_json
  const sections = sectionScores
    ? Object.entries(sectionScores).map(([name, vals]) => ({
        label: name,
        score: vals?.earned ?? 0,
        maxScore: vals?.max ?? 0,
      }))
    : []

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="max-w-5xl mx-auto px-4 py-10 space-y-6">
        {/* Breadcrumb + Header */}
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-sm text-gray-400 mb-1 flex-wrap">
              <Link to="/dashboard" className="hover:text-blue-600 transition-colors">Dashboard</Link>
              <ChevronRight className="w-3.5 h-3.5" />
              {sessionId && (
                <>
                  <Link to={`/sessions/${sessionId}`} className="hover:text-blue-600 transition-colors">Results</Link>
                  <ChevronRight className="w-3.5 h-3.5" />
                </>
              )}
              <span>Exam Detail</span>
            </div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <ClipboardList className="w-6 h-6 text-blue-600" />
              {studentName}
            </h1>
          </div>
          <div className="flex gap-2 shrink-0">
            {result && (
              <Button variant="secondary" onClick={() => setCorrectModalOpen(true)}>
                <Edit3 className="w-4 h-4" /> Correct Score
              </Button>
            )}
            <Button onClick={handleDownloadPdf} loading={pdfLoading} variant="secondary">
              <Download className="w-4 h-4" /> PDF Plan
            </Button>
          </div>
        </div>

        {error && (
          <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column */}
          <div className="lg:col-span-1 space-y-5">
            {/* Student card */}
            <Card>
              <CardBody>
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-bold text-lg">
                    {studentName.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <p className="font-semibold text-gray-900">{studentName}</p>
                    <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${
                      exam?.status === 'review_needed'
                        ? 'bg-amber-100 text-amber-700'
                        : exam?.status === 'graded'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-500'
                    }`}>
                      {exam?.status === 'review_needed' && <AlertTriangle className="w-3 h-3" />}
                      {exam?.status === 'graded' && <CheckCircle2 className="w-3 h-3" />}
                      {exam?.status ?? 'pending'}
                    </span>
                  </div>
                </div>

                {pct != null ? (
                  <div className="text-center bg-gray-50 rounded-xl p-4 border border-gray-100">
                    <p className={`text-4xl font-black ${
                      pct >= 90 ? 'text-green-600' : pct >= 70 ? 'text-blue-600' : pct >= 50 ? 'text-amber-600' : 'text-red-600'
                    }`}>
                      {pct}%
                    </p>
                    <p className="text-sm text-gray-500 mt-0.5">{finalScore} / {maxScore} pts</p>
                    {result?.final_score != null && result.final_score !== result.total_score && (
                      <p className="text-xs text-amber-600 mt-0.5">
                        (original: {result.total_score})
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="text-center bg-gray-50 rounded-xl p-4 border border-gray-100">
                    <p className="text-gray-400 text-sm">Score not yet available</p>
                  </div>
                )}
              </CardBody>
            </Card>

            {/* Exam images */}
            <Card>
              <CardHeader>
                <h2 className="text-sm font-semibold text-gray-700">Exam Images</h2>
              </CardHeader>
              <CardBody className="pt-3">
                <ImageCarousel images={images} />
              </CardBody>
            </Card>
          </div>

          {/* Right column */}
          <div className="lg:col-span-2 space-y-5">
            {/* Score breakdown */}
            {sections.length > 0 && (
              <Card>
                <CardHeader>
                  <h2 className="font-semibold text-gray-800 flex items-center gap-2">
                    <Target className="w-4 h-4 text-purple-500" /> Score Breakdown
                  </h2>
                </CardHeader>
                <CardBody>
                  <ScoreGrid sections={sections} />
                </CardBody>
              </Card>
            )}

            {/* Review Required Panel */}
            {isReviewNeeded && lowConfidenceEntries.length > 0 && !reviewSuccess && (
              <Card>
                <CardHeader>
                  <h2 className="font-semibold text-amber-800 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-500" />
                    Review Required
                    <span className="ml-auto text-xs font-medium bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
                      {lowConfidenceEntries.length} question{lowConfidenceEntries.length !== 1 ? 's' : ''}
                    </span>
                  </h2>
                </CardHeader>
                <CardBody>
                  <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-4">
                    Claude was not confident about these answers. Review each one and either accept the extracted value or provide the correct answer.
                  </p>
                  <div className="space-y-4">
                    {lowConfidenceEntries.map(([qId, ans]) => {
                      const extracted = ans?.value ?? null
                      const reason = ans?.reason ?? 'Handwriting unclear'
                      const alternatives = ans?.alternatives ?? []
                      const decision = reviewDecisions[qId]
                      return (
                        <div key={qId} className="border border-amber-200 rounded-xl p-4 bg-amber-50/50 space-y-3">
                          <div className="flex items-start gap-3">
                            <span className="shrink-0 w-8 h-8 rounded-full bg-amber-100 text-amber-800 font-bold text-xs flex items-center justify-center border border-amber-200">
                              {qId}
                            </span>
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <Eye className="w-3.5 h-3.5 text-amber-500" />
                                <span className="text-xs text-amber-700 font-medium">Claude extracted:</span>
                                <span className="text-sm font-semibold text-gray-800">
                                  {extracted ?? <span className="italic text-gray-400">blank</span>}
                                </span>
                                <span className="text-xs bg-red-100 text-red-600 px-1.5 py-0.5 rounded-full">low confidence</span>
                              </div>
                              <p className="text-xs text-gray-500">{reason}</p>
                              {alternatives.length > 0 && (
                                <p className="text-xs text-gray-400 mt-0.5">
                                  Alternatives: {alternatives.join(', ')}
                                </p>
                              )}
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <button
                              onClick={() => handleReviewDecision(qId, 'accept', extracted)}
                              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                                decision?.mode === 'accept'
                                  ? 'bg-green-600 text-white border-green-600'
                                  : 'bg-white text-gray-700 border-gray-300 hover:border-green-500 hover:text-green-700'
                              }`}
                            >
                              <Check className="w-3.5 h-3.5" /> Accept "{extracted ?? 'blank'}"
                            </button>
                            <div className={`inline-flex items-center gap-1.5 border rounded-lg overflow-hidden transition-colors ${
                              decision?.mode === 'correct'
                                ? 'border-blue-500'
                                : 'border-gray-300'
                            }`}>
                              <span className="px-2.5 py-1.5 text-xs text-gray-500 bg-gray-50 border-r border-gray-200">
                                Correct to:
                              </span>
                              <input
                                type="text"
                                value={decision?.mode === 'correct' ? (decision.value ?? '') : ''}
                                onChange={(e) => handleReviewDecision(qId, 'correct', e.target.value)}
                                onFocus={() => { if (decision?.mode !== 'correct') handleReviewDecision(qId, 'correct', '') }}
                                placeholder="enter answer…"
                                className="w-28 px-2 py-1.5 text-xs focus:outline-none bg-white"
                              />
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  {reviewError && (
                    <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-3 py-2 text-sm mt-4">
                      <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                      <span>{reviewError}</span>
                    </div>
                  )}

                  <div className="flex justify-end mt-4">
                    <Button onClick={handleSubmitReview} loading={reviewSubmitting}>
                      <Check className="w-4 h-4" /> Submit Review & Re-grade
                    </Button>
                  </div>
                </CardBody>
              </Card>
            )}

            {/* Review success banner */}
            {reviewSuccess && (
              <div className="flex items-center gap-2 bg-green-50 border border-green-200 text-green-700 rounded-xl px-4 py-3 text-sm">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>Review submitted — exam re-graded successfully.</span>
              </div>
            )}

            {/* Extracted answers */}
            {answerEntries.length > 0 && (
              <Card>
                <CardHeader>
                  <div className="flex justify-between items-center">
                    <h2 className="font-semibold text-gray-800 flex items-center gap-2">
                      <ClipboardList className="w-4 h-4 text-blue-500" /> Extracted Answers
                    </h2>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => {
                        if (isEditingAnswers) {
                          // Cancel — restore from exam data
                          setEditedAnswers(exam?.extracted_answers_json ?? {})
                        }
                        setIsEditingAnswers(!isEditingAnswers)
                      }}
                    >
                      <Edit3 className="w-3.5 h-3.5" />
                      {isEditingAnswers ? 'Cancel Edit' : 'Edit Answers'}
                    </Button>
                  </div>
                </CardHeader>
                <CardBody>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-96 overflow-y-auto pr-1">
                    {Object.entries(editedAnswers || {}).map(([qId, answer]) => {
                      const value = getAnswerValue(answer)
                      const confidence = getAnswerConfidence(answer)
                      const style = CONFIDENCE_STYLE[confidence] ?? CONFIDENCE_STYLE.high

                      return (
                        <div key={qId} className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${
                          confidence === 'low' ? 'bg-amber-50 border-amber-200' : 'bg-gray-50 border-gray-200'
                        }`}>
                          <span className="text-xs font-semibold text-gray-500 w-10 shrink-0">{qId}</span>
                          {isEditingAnswers ? (
                            <input
                              type="text"
                              value={typeof answer === 'object' ? (answer?.value ?? '') : (answer ?? '')}
                              onChange={(e) => setEditedAnswers((prev) => ({
                                ...prev,
                                [qId]: e.target.value,
                              }))}
                              className="flex-1 px-2 py-1 border border-gray-300 rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                            />
                          ) : (
                            <span className="flex-1 text-sm font-medium text-gray-800 truncate">
                              {value ?? '\u2014'}
                            </span>
                          )}
                          {confidence === 'low' && !isEditingAnswers && (
                            <span className={`inline-flex items-center gap-1 text-xs font-medium ${style.text}`}>
                              <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
                            </span>
                          )}
                        </div>
                      )
                    })}
                  </div>

                  {isEditingAnswers && (
                    <div className="mt-4 flex gap-2 justify-end">
                      <Button
                        variant="secondary"
                        onClick={() => {
                          setEditedAnswers(exam?.extracted_answers_json ?? {})
                          setIsEditingAnswers(false)
                        }}
                      >
                        Cancel
                      </Button>
                      <Button onClick={handleSaveAnswers} loading={editSaving}>
                        Save & Re-grade
                      </Button>
                    </div>
                  )}
                </CardBody>
              </Card>
            )}

            {/* Improvement plan */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <h2 className="font-semibold text-gray-800 flex items-center gap-2">
                    <Lightbulb className="w-4 h-4 text-yellow-500" /> Improvement Plan
                  </h2>
                  {!plan && !planLoading && (
                    <Button size="sm" variant="secondary" onClick={loadPlan}>
                      Load Plan
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardBody>
                {planLoading ? (
                  <div className="flex items-center gap-2 text-sm text-gray-400 py-4 justify-center">
                    <Loader2 className="w-4 h-4 animate-spin" /> Loading improvement plan…
                  </div>
                ) : plan ? (
                  <ImprovementPlan plan={plan} />
                ) : (
                  <div className="text-center py-8 text-gray-400">
                    <Lightbulb className="w-8 h-8 mx-auto mb-2 opacity-30" />
                    <p className="text-sm">Click "Load Plan" to generate the AI improvement plan</p>
                  </div>
                )}
              </CardBody>
            </Card>
          </div>
        </div>
      </main>

      {/* Correct Score Modal */}
      <Modal
        open={correctModalOpen}
        onClose={() => { setCorrectModalOpen(false); setCorrectError(null); setCorrectSuccess(false) }}
        title="Correct Score"
        size="md"
      >
        {correctSuccess ? (
          <div className="flex flex-col items-center py-6 text-center">
            <CheckCircle2 className="w-12 h-12 text-green-500 mb-3" />
            <p className="font-semibold text-gray-800">Correction saved!</p>
          </div>
        ) : (
          <form onSubmit={handleCorrectScore} className="space-y-4">
            <div className="bg-gray-50 rounded-xl p-3 border border-gray-200 text-sm space-y-0.5">
              <p className="text-gray-500">Student: <span className="font-medium text-gray-800">{studentName}</span></p>
              <p className="text-gray-500">Current score: <span className="font-medium text-gray-800">
                {result?.final_score ?? result?.total_score ?? '—'} / {maxScore}
              </span></p>
            </div>

            <p className="text-xs text-gray-400">Enter a correction for a specific question. The final score will be recalculated automatically.</p>

            {correctError && (
              <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-3 py-2 text-sm">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{correctError}</span>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Question ID <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={correctForm.questionId}
                  onChange={(e) => setCorrectForm({ ...correctForm, questionId: e.target.value })}
                  placeholder="e.g. Q1, 1, question_1"
                  className="w-full px-3.5 py-2.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Original Score <span className="text-red-500">*</span>
                </label>
                <input
                  type="number"
                  min={0}
                  step="any"
                  value={correctForm.originalScore}
                  onChange={(e) => setCorrectForm({ ...correctForm, originalScore: e.target.value })}
                  placeholder="0"
                  className="w-full px-3.5 py-2.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Corrected Score <span className="text-red-500">*</span>
                </label>
                <input
                  type="number"
                  min={0}
                  step="any"
                  value={correctForm.correctedScore}
                  onChange={(e) => setCorrectForm({ ...correctForm, correctedScore: e.target.value })}
                  placeholder="0"
                  className="w-full px-3.5 py-2.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Reason <span className="text-red-500">*</span>
              </label>
              <textarea
                rows={2}
                value={correctForm.reason}
                onChange={(e) => setCorrectForm({ ...correctForm, reason: e.target.value })}
                placeholder="Reason for this correction…"
                className="w-full px-3.5 py-2.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition resize-none"
              />
            </div>

            <div className="flex gap-2 justify-end pt-1">
              <Button type="button" variant="secondary" onClick={() => { setCorrectModalOpen(false); setCorrectError(null) }}>
                Cancel
              </Button>
              <Button type="submit" loading={correctLoading}>
                Save Correction
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  )
}
