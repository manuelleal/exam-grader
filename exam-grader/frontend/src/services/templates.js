import api from './api'

export const templatesService = {
  async list() {
    const { data } = await api.get('/templates')
    return data
  },

  async get(id) {
    const { data } = await api.get(`/templates/${id}`)
    return data
  },

  async create(payload) {
    const { data } = await api.post('/templates', payload)
    return data
  },

  async uploadImage(id, file) {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.post(`/templates/${id}/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  async uploadFile(id, file, fileType = 'auto') {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.post(
      `/templates/${id}/upload?file_type=${encodeURIComponent(fileType)}`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
    return data
  },

  async extractStructure(id) {
    const { data } = await api.post(`/templates/${id}/extract`)
    return data
  },

  async saveAnswerKey(id, answerKey) {
    let keyDict = answerKey
    if (typeof answerKey === 'string') {
      try { keyDict = JSON.parse(answerKey) } catch { keyDict = { raw: answerKey } }
    }
    if (typeof keyDict !== 'object' || Array.isArray(keyDict) || keyDict === null) {
      keyDict = { raw: String(answerKey) }
    }
    const { data } = await api.put(`/templates/${id}/answer-key`, {
      answer_key: keyDict,
      method: 'manual',
    })
    return data
  },

  async updateStructure(id, structure) {
    const { data } = await api.put(`/templates/${id}/structure`, { structure })
    return data
  },

  async delete(id) {
    const { data } = await api.delete(`/templates/${id}`)
    return data
  },
}
