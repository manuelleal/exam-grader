import api from './api'

export const sessionsService = {
  async list() {
    const { data } = await api.get('/sessions')
    return data
  },

  async get(id) {
    const { data } = await api.get(`/sessions/${id}`)
    return data
  },

  async create(payload) {
    const { data } = await api.post('/sessions', payload)
    return data
  },

  async uploadExams(id, files, onProgress) {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    const { data } = await api.post(`/sessions/${id}/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (onProgress && e.total) {
          onProgress(Math.round((e.loaded * 100) / e.total))
        }
      },
    })
    return data
  },

  async process(id) {
    const { data } = await api.post(`/sessions/${id}/process`)
    return data
  },

  async getStatus(id) {
    const { data } = await api.get(`/sessions/${id}/status`)
    return data
  },

  async getExams(sessionId) {
    const { data } = await api.get(`/exams/sessions/${sessionId}`)
    return data
  },

  async exportExcel(id) {
    const response = await api.get(`/sessions/${id}/export`, {
      params: { format: 'excel' },
      responseType: 'blob',
    })
    return response
  },
}

export const examsService = {
  async get(id) {
    const { data } = await api.get(`/exams/${id}`)
    return data
  },

  async getResult(id) {
    const { data } = await api.get(`/exams/${id}/result`)
    return data
  },

  async getImprovementPlan(id) {
    const { data } = await api.get(`/exams/${id}/improvement-plan`)
    return data
  },

  async downloadPdf(id) {
    const response = await api.get(`/exams/${id}/improvement-plan/pdf`, {
      responseType: 'blob',
    })
    return response
  },

  async correctScore(resultId, corrections) {
    const { data } = await api.put(`/results/${resultId}/correct`, { corrections })
    return data
  },

  async reviewAnswers(examId, corrections) {
    const { data } = await api.patch(`/exams/${examId}/review-answers`, { corrections })
    return data
  },

  async updateExtractedAnswers(examId, answers) {
    const { data } = await api.patch(`/exams/${examId}/extracted-answers`, { answers })
    return data
  },

  async regrade(examId) {
    const { data } = await api.post(`/exams/${examId}/regrade`)
    return data
  },
}
