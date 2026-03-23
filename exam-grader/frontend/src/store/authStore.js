import { create } from 'zustand'
import { authService } from '../services/auth'

const TOKEN_KEY = 'access_token'
const USER_KEY = 'user'

const useAuthStore = create((set) => ({
  token: localStorage.getItem(TOKEN_KEY) || null,
  user: (() => {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY)) || null
    } catch {
      return null
    }
  })(),
  isLoading: false,
  error: null,

  login: async (email, password) => {
    console.log('[authStore] login() called for:', email)
    set({ isLoading: true, error: null })
    try {
      const { access_token } = await authService.login(email, password)
      console.log('[authStore] login() got token:', access_token ? 'OK' : 'MISSING')
      localStorage.setItem(TOKEN_KEY, access_token)

      const user = await authService.getMe()
      console.log('[authStore] getMe() returned:', user)
      localStorage.setItem(USER_KEY, JSON.stringify(user))

      set({ token: access_token, user, isLoading: false })
      return true
    } catch (err) {
      console.error('[authStore] login() error:', err.message)
      set({ isLoading: false, error: err.message })
      return false
    }
  },

  register: async (name, email, password) => {
    console.log('[authStore] register() called for:', email)
    set({ isLoading: true, error: null })
    try {
      console.log('[authStore] Step 1: calling authService.register()')
      const newUser = await authService.register(name, email, password)
      console.log('[authStore] Step 1 OK — created user:', newUser)

      console.log('[authStore] Step 2: auto-login')
      const { access_token } = await authService.login(email, password)
      console.log('[authStore] Step 2 OK — token:', access_token ? 'received' : 'MISSING')
      localStorage.setItem(TOKEN_KEY, access_token)

      console.log('[authStore] Step 3: getMe()')
      const user = await authService.getMe()
      console.log('[authStore] Step 3 OK — user profile:', user)
      localStorage.setItem(USER_KEY, JSON.stringify(user))

      set({ token: access_token, user, isLoading: false })
      return true
    } catch (err) {
      console.error('[authStore] register() FAILED at some step:', err.message)
      set({ isLoading: false, error: err.message })
      return false
    }
  },

  logout: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    set({ token: null, user: null, error: null })
  },

  clearError: () => set({ error: null }),
}))

export default useAuthStore
