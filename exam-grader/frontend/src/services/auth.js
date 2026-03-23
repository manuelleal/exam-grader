import api from './api'

export const authService = {
  async login(email, password) {
    console.log('[authService] POST /auth/login', { email })
    try {
      const { data } = await api.post('/auth/login', { email, password })
      console.log('[authService] POST /auth/login response:', data)
      return data
    } catch (err) {
      console.error('[authService] POST /auth/login FAILED:', err.message)
      throw err
    }
  },

  async register(name, email, password) {
    console.log('[authService] POST /auth/register', { name, email })
    try {
      const { data } = await api.post('/auth/register', { name, email, password })
      console.log('[authService] POST /auth/register response:', data)
      return data
    } catch (err) {
      console.error('[authService] POST /auth/register FAILED:', err.message)
      throw err
    }
  },

  async getMe() {
    console.log('[authService] GET /auth/me')
    try {
      const { data } = await api.get('/auth/me')
      console.log('[authService] GET /auth/me response:', data)
      return data
    } catch (err) {
      console.error('[authService] GET /auth/me FAILED:', err.message)
      throw err
    }
  },
}
