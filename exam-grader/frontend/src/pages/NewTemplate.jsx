import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  FileText, ChevronRight, Sparkles, Key, Save, CheckCircle2, AlertCircle,
  Upload, BookOpen, ClipboardList, AlertTriangle, Plus,
} from 'lucide-react'
import Navbar from '../components/Navbar'
import { Card, CardHeader, CardBody, CardFooter } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { FileUpload } from '../components/ui/FileUpload'
import { templatesService } from '../services/templates'

const STEPS = ['Details', 'Upload & Extract', 'Answer Key', 'Done']

function StepIndicator({ current }) {
  return (
    <div className="flex items-center gap-2 mb-8">
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

export default function NewTemplate() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Step 0 — form
  const [form, setForm] = useState({ name: '', subject: '', mode: 'integrated', max_score: '100' })

  // Step 1 — upload + extract
  const [template, setTemplate] = useState(null)
  // integrated mode
  const [integratedFiles, setIntegratedFiles] = useState([])
  // separate_answer_sheet mode
  const [bookletFiles, setBookletFiles] = useState([])
  const [answerSheetFiles, setAnswerSheetFiles] = useState([])
  // upload tracking
  const [uploadState, setUploadState] = useState({ integrated: false, question_book: false, answer_sheet: false })
  const [extractedStructure, setExtractedStructure] = useState(null)

  // Extraction validation
  const [extractionStatus, setExtractionStatus] = useState('complete')
  const [missingPoints, setMissingPoints] = useState(0)
  const [showAddSection, setShowAddSection] = useState(false)
  const [newSection, setNewSection] = useState({ name: '', points: '', questions: '', type: '' })

  // Step 2 — answer key
  const [answerKeyText, setAnswerKeyText] = useState('')

  const handleCreateTemplate = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) { setError('Template name is required'); return }
    if (!form.subject.trim()) { setError('Subject is required'); return }
    const maxScoreNum = parseFloat(form.max_score)
    if (!form.max_score || isNaN(maxScoreNum) || maxScoreNum <= 0) { setError('Max score must be a positive number'); return }
    setError(null)
    setLoading(true)
    try {
      const created = await templatesService.create({
        name: form.name.trim(),
        subject: form.subject.trim(),
        mode: form.mode,
        max_score: parseFloat(form.max_score),
      })
      setTemplate(created)
      setStep(1)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleUploadAndExtract = async () => {
    const mode = template?.mode ?? 'integrated'
    if (mode === 'integrated') {
      if (!integratedFiles.length) { setError('Please select an exam file'); return }
    } else {
      if (!answerSheetFiles.length) { setError('Answer sheet is required'); return }
    }
    setError(null)
    setLoading(true)
    try {
      if (mode === 'integrated') {
        await templatesService.uploadFile(template.id, integratedFiles[0], 'integrated')
        setUploadState((s) => ({ ...s, integrated: true }))
      } else {
        if (bookletFiles.length) {
          await templatesService.uploadFile(template.id, bookletFiles[0], 'question_book')
          setUploadState((s) => ({ ...s, question_book: true }))
        }
        await templatesService.uploadFile(template.id, answerSheetFiles[0], 'answer_sheet')
        setUploadState((s) => ({ ...s, answer_sheet: true }))
      }
      const result = await templatesService.extractStructure(template.id)
      setExtractedStructure(result?.structure ?? result)
      setExtractionStatus(result?.extraction_status ?? 'complete')
      setMissingPoints(result?.missing_points ?? 0)
      setStep(2)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleAddSection = async () => {
    if (!newSection.name || !newSection.points || !newSection.questions || !newSection.type) {
      setError('Complete all fields to add a section')
      return
    }
    const numQuestions = parseInt(newSection.questions)
    const totalPoints = parseFloat(newSection.points)
    const existingQuestions = (extractedStructure?.sections ?? []).flatMap(
      (sec) => sec.parts?.flatMap((p) => p.questions ?? []) ?? []
    )
    const startNum = existingQuestions.length + 1
    const questions = Array.from({ length: numQuestions }, (_, i) => String(startNum + i))

    const updatedStructure = {
      ...extractedStructure,
      sections: [
        ...(extractedStructure?.sections ?? []),
        {
          name: newSection.name,
          total_points: totalPoints,
          parts: [{
            name: newSection.name,
            questions,
            type: newSection.type,
            options: newSection.type === 'multiple_choice' ? ['A', 'B', 'C', 'D'] : null,
            points_each: totalPoints / numQuestions,
          }],
        },
      ],
      max_score: (extractedStructure?.max_score ?? 0) + totalPoints,
    }

    setError(null)
    setLoading(true)
    try {
      await templatesService.updateStructure(template.id, updatedStructure)
      setExtractedStructure(updatedStructure)
      setShowAddSection(false)
      setNewSection({ name: '', points: '', questions: '', type: '' })
      const expected = parseFloat(form.max_score) || 100
      const newMax = updatedStructure.max_score
      if (newMax >= expected * 0.9) {
        setExtractionStatus('complete')
        setMissingPoints(0)
      } else {
        setMissingPoints(Math.max(0, expected - newMax))
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleSaveAnswerKey = async () => {
    if (!answerKeyText.trim()) { setError('Answer key is required'); return }
    setError(null)
    setLoading(true)
    try {
      let parsed = answerKeyText.trim()
      try { parsed = JSON.parse(parsed) } catch { /* treat as raw string */ }
      await templatesService.saveAnswerKey(template.id, parsed)
      setStep(3)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="max-w-3xl mx-auto px-4 py-10">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <FileText className="w-6 h-6 text-blue-600" /> New Template
          </h1>
          <p className="text-gray-500 mt-1">Create a grading rubric from your exam image</p>
        </div>

        <StepIndicator current={step} />

        {error && (
          <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 mb-5 text-sm">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* ── Step 0: Details ── */}
        {step === 0 && (
          <Card>
            <CardHeader>
              <h2 className="font-semibold text-gray-800">Template Details</h2>
            </CardHeader>
            <form onSubmit={handleCreateTemplate}>
              <CardBody className="space-y-5">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">
                    Template Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="e.g. Math Midterm Q1 2025"
                    className="w-full px-3.5 py-2.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">
                    Subject <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={form.subject}
                    onChange={(e) => setForm({ ...form, subject: e.target.value })}
                    placeholder="e.g. Mathematics, Physics, History…"
                    className="w-full px-3.5 py-2.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">
                    Max Score <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="number"
                    min="1"
                    step="any"
                    value={form.max_score}
                    onChange={(e) => setForm({ ...form, max_score: e.target.value })}
                    placeholder="e.g. 100"
                    className="w-full px-3.5 py-2.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Exam Mode</label>
                  <div className="grid grid-cols-2 gap-3">
                    {[
                      { value: 'integrated', label: 'Integrated', desc: 'Answers on exam sheet' },
                      { value: 'separate_answer_sheet', label: 'Separate Sheet', desc: 'Answer sheet is separate' },
                    ].map((opt) => (
                      <label
                        key={opt.value}
                        className={`flex items-start gap-3 p-3.5 rounded-xl border-2 cursor-pointer transition-colors ${
                          form.mode === opt.value
                            ? 'border-blue-500 bg-blue-50'
                            : 'border-gray-200 hover:border-gray-300'
                        }`}
                      >
                        <input
                          type="radio"
                          name="mode"
                          value={opt.value}
                          checked={form.mode === opt.value}
                          onChange={(e) => setForm({ ...form, mode: e.target.value })}
                          className="mt-0.5 accent-blue-600"
                        />
                        <div>
                          <p className="text-sm font-medium text-gray-800">{opt.label}</p>
                          <p className="text-xs text-gray-500">{opt.desc}</p>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              </CardBody>
              <CardFooter className="flex justify-end">
                <Button type="submit" loading={loading}>
                  Create Template <ChevronRight className="w-4 h-4" />
                </Button>
              </CardFooter>
            </form>
          </Card>
        )}

        {/* ── Step 1: Upload & Extract ── */}
        {step === 1 && (
          <Card>
            <CardHeader>
              <h2 className="font-semibold text-gray-800">Upload Exam File(s)</h2>
              <p className="text-sm text-gray-500 mt-0.5">
                {template?.mode === 'separate_answer_sheet'
                  ? 'Upload the answer sheet (required). If it has 2 pages, upload page 2 as Additional Page.'
                  : 'Upload a blank/reference copy of the complete exam'}
              </p>
            </CardHeader>
            <CardBody className="space-y-5">

              {template?.mode === 'integrated' ? (
                /* ─ Integrated: single upload ─ */
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-gray-700 flex items-center gap-1.5">
                    <Upload className="w-4 h-4 text-blue-500" />
                    Exam File <span className="text-red-500">*</span>
                    {uploadState.integrated && <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />}
                  </label>
                  <FileUpload
                    accept="image/*,application/pdf"
                    files={integratedFiles}
                    onChange={setIntegratedFiles}
                    label="Drop exam image or PDF here or click to browse"
                    sublabel="PNG, JPG, WEBP, PDF — up to 20 MB"
                    disabled={loading}
                  />
                  <p className="text-xs text-gray-400">
                    This file contains both the questions and answer spaces.
                  </p>
                </div>
              ) : (
                /* ─ Separate: two uploads ─ */
                <div className="space-y-5">
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium text-gray-700 flex items-center gap-1.5">
                      <BookOpen className="w-4 h-4 text-purple-500" />
                      Page 2 / Question Booklet
                      <span className="text-xs text-gray-400 font-normal ml-1">(optional - for multi-page exams)</span>
                      {uploadState.question_book && <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />}
                    </label>
                    <FileUpload
                      accept="image/*,application/pdf"
                      files={bookletFiles}
                      onChange={setBookletFiles}
                      label="Drop page 2 or question booklet here"
                      sublabel="Upload page 2 if your answer sheet has multiple pages — PNG, JPG, PDF up to 20 MB"
                      disabled={loading}
                    />
                  </div>

                  <div className="border-t border-gray-100" />

                  <div className="space-y-1.5">
                    <label className="text-sm font-medium text-gray-700 flex items-center gap-1.5">
                      <ClipboardList className="w-4 h-4 text-blue-500" />
                      Answer Sheet Template <span className="text-red-500">*</span>
                      {uploadState.answer_sheet && <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />}
                    </label>
                    <FileUpload
                      accept="image/*,application/pdf"
                      files={answerSheetFiles}
                      onChange={setAnswerSheetFiles}
                      label="Drop answer sheet here or click to browse"
                      sublabel="Required — blank answer sheet where students write answers — PNG, JPG, PDF up to 20 MB"
                      disabled={loading}
                    />
                  </div>
                </div>
              )}

              {loading && (
                <div className="flex items-center gap-2 text-blue-600 text-sm">
                  <Sparkles className="w-4 h-4 animate-pulse" />
                  {uploadState.answer_sheet || uploadState.integrated
                    ? 'Extracting structure with AI…'
                    : 'Uploading file(s)…'}
                </div>
              )}

              {extractedStructure && (
                <div>
                  <p className="text-sm font-medium text-gray-700 mb-2 flex items-center gap-1.5">
                    <CheckCircle2 className="w-4 h-4 text-green-500" /> Extracted Structure
                  </p>
                  <pre className="bg-gray-50 border border-gray-200 rounded-xl p-4 text-xs text-gray-700 overflow-auto max-h-64 whitespace-pre-wrap">
                    {JSON.stringify(extractedStructure, null, 2)}
                  </pre>
                </div>
              )}
            </CardBody>
            <CardFooter className="flex justify-end">
              <Button
                onClick={handleUploadAndExtract}
                loading={loading}
                disabled={
                  template?.mode === 'integrated'
                    ? !integratedFiles.length
                    : !answerSheetFiles.length
                }
              >
                <Sparkles className="w-4 h-4" /> Extract Structure
              </Button>
            </CardFooter>
          </Card>
        )}

        {/* ── Step 2: Answer Key ── */}
        {step === 2 && (
          <Card>
            <CardHeader>
              <h2 className="font-semibold text-gray-800 flex items-center gap-2">
                <Key className="w-4 h-4 text-amber-500" /> Answer Key
              </h2>
              <p className="text-sm text-gray-500 mt-0.5">
                Enter the correct answers. Use JSON format or plain text.
              </p>
            </CardHeader>
            <CardBody className="space-y-4">
              {/* ── Incomplete extraction warning ── */}
              {extractionStatus === 'incomplete' && extractedStructure && (
                <div className="bg-amber-50 border-l-4 border-amber-400 rounded-r-xl p-4">
                  <div className="flex">
                    <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
                    <div className="ml-3 flex-1">
                      <h3 className="text-sm font-medium text-amber-800">
                        Incomplete extraction
                      </h3>
                      <p className="text-sm text-amber-700 mt-1">
                        Only detected <strong>{extractedStructure.max_score}</strong>/{form.max_score || 100} points.
                        Missing approximately <strong>{missingPoints}</strong> points.
                      </p>

                      <div className="mt-4 space-y-3">
                        <label className="flex items-center cursor-pointer">
                          <input
                            type="checkbox"
                            checked={showAddSection}
                            onChange={(e) => setShowAddSection(e.target.checked)}
                            className="rounded border-amber-300 text-amber-600 focus:ring-amber-500"
                          />
                          <span className="ml-2 text-sm text-amber-800">Add missing section manually</span>
                        </label>

                        {showAddSection && (
                          <div className="bg-white p-4 rounded-lg border border-amber-200 space-y-3">
                            <input
                              placeholder="Section name (e.g. Reading)"
                              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                              value={newSection.name}
                              onChange={(e) => setNewSection({ ...newSection, name: e.target.value })}
                            />
                            <div className="grid grid-cols-2 gap-3">
                              <input
                                type="number"
                                min="1"
                                placeholder="Total points (e.g. 25)"
                                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                                value={newSection.points}
                                onChange={(e) => setNewSection({ ...newSection, points: e.target.value })}
                              />
                              <input
                                type="number"
                                min="1"
                                placeholder="Number of questions (e.g. 20)"
                                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                                value={newSection.questions}
                                onChange={(e) => setNewSection({ ...newSection, questions: e.target.value })}
                              />
                            </div>
                            <select
                              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                              value={newSection.type}
                              onChange={(e) => setNewSection({ ...newSection, type: e.target.value })}
                            >
                              <option value="">Question type...</option>
                              <option value="multiple_choice">Multiple Choice</option>
                              <option value="true_false">True / False</option>
                              <option value="short_answer">Short Answer</option>
                              <option value="fill_blank">Fill in the Blank</option>
                            </select>
                            <Button onClick={handleAddSection} loading={loading} className="w-full">
                              <Plus className="w-4 h-4" /> Add Section
                            </Button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {extractedStructure && (
                <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 text-xs text-blue-700">
                  <p className="font-semibold mb-1">Detected structure (reference):</p>
                  <pre className="overflow-auto max-h-32 whitespace-pre-wrap">
                    {JSON.stringify(extractedStructure, null, 2)}
                  </pre>
                </div>
              )}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-sm font-medium text-gray-700">
                    Answer Key <span className="text-red-500">*</span>
                  </label>
                  {extractedStructure && (
                    <button
                      type="button"
                      onClick={() => {
                        const questions = {}
                        const sections = extractedStructure?.sections ?? []
                        sections.forEach((sec) => {
                          sec.parts?.forEach((part) => {
                            part.questions?.forEach((q) => { questions[String(q)] = '' })
                          })
                        })
                        if (Object.keys(questions).length > 0) {
                          setAnswerKeyText(JSON.stringify(questions, null, 2))
                        }
                      }}
                      className="text-xs text-blue-600 hover:text-blue-800 font-medium transition-colors"
                    >
                      Auto-fill question keys from structure
                    </button>
                  )}
                </div>
                <textarea
                  rows={10}
                  value={answerKeyText}
                  onChange={(e) => setAnswerKeyText(e.target.value)}
                  placeholder={'{\'1\': \'B\', \'2\': \'A\', \'3\': \'C\', \'4\': \'Twenty-five\'}'}
                  className="w-full px-3.5 py-2.5 text-sm font-mono border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition resize-none"
                />
                <p className="text-xs text-gray-400 mt-1.5">
                  Map question numbers to correct answers. Multiple choice: use the letter (A, B, C). Fill-in-the-blank: write the expected answer.
                </p>
              </div>
            </CardBody>
            <CardFooter className="flex justify-between">
              <Button variant="secondary" onClick={() => setStep(1)}>Back</Button>
              <Button onClick={handleSaveAnswerKey} loading={loading}>
                <Save className="w-4 h-4" /> Save Template
              </Button>
            </CardFooter>
          </Card>
        )}

        {/* ── Step 3: Done ── */}
        {step === 3 && (
          <Card>
            <CardBody className="flex flex-col items-center py-16 text-center">
              <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mb-4">
                <CheckCircle2 className="w-8 h-8 text-green-600" />
              </div>
              <h2 className="text-xl font-bold text-gray-900 mb-2">Template Created!</h2>
              <p className="text-gray-500 mb-1">
                <span className="font-medium text-gray-700">{template?.name}</span> is ready to use.
              </p>
              <p className="text-sm text-gray-400 mb-8">You can now create a grading session with this template.</p>
              <div className="flex gap-3">
                <Button variant="secondary" onClick={() => navigate('/sessions/new')}>
                  Start Grading Session
                </Button>
                <Button onClick={() => navigate('/dashboard')}>
                  Back to Dashboard
                </Button>
              </div>
            </CardBody>
          </Card>
        )}
      </main>
    </div>
  )
}
