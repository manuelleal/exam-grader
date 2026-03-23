import axios from 'axios'

const api = axios.create({
  baseURL: 'https://exam-grader-production.up.railway.app/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor — attach Bearer token automatically
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

// Response interceptor — global error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status

    // On 401: clear stored credentials so ProtectedRoute redirects naturally.
    // Do NOT do window.location.href here — it fires before catch blocks in
    // the store can set the error message, causing a silent redirect.
    if (status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
    }

    const message =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      'An unexpected error occurred'

    console.error('[api] HTTP error', status, '→', message)
    return Promise.reject(new Error(message))
  },
)

export default api
