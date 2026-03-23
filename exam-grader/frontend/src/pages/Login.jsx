import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { GraduationCap, Mail, Lock, AlertCircle } from 'lucide-react'
import useAuthStore from '../store/authStore'
import { Button } from '../components/ui/button'
import { Card, CardBody } from '../components/ui/card'

export default function Login() {
  const navigate = useNavigate()
  const login      = useAuthStore((s) => s.login)
  const isLoading  = useAuthStore((s) => s.isLoading)
  const error      = useAuthStore((s) => s.error)
  const token      = useAuthStore((s) => s.token)
  const clearError = useAuthStore((s) => s.clearError)

  const [form, setForm] = useState({ email: '', password: '' })
  const [validationErrors, setValidationErrors] = useState({})

  useEffect(() => {
    if (token) navigate('/dashboard', { replace: true })
  }, [token, navigate])

  useEffect(() => {
    return () => clearError()
  }, [clearError])

  const validate = () => {
    const errors = {}
    if (!form.email.trim()) errors.email = 'Email is required'
    else if (!/\S+@\S+\.\S+/.test(form.email)) errors.email = 'Enter a valid email'
    if (!form.password) errors.password = 'Password is required'
    return errors
  }

  const handleChange = (e) => {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
    if (validationErrors[name]) {
      setValidationErrors((prev) => ({ ...prev, [name]: '' }))
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    console.log('[Login] handleSubmit fired, email:', form.email)
    const errors = validate()
    if (Object.keys(errors).length) {
      console.warn('[Login] Validation blocked submission:', errors)
      setValidationErrors(errors)
      return
    }
    console.log('[Login] Validation passed — calling login action')
    const ok = await login(form.email, form.password)
    console.log('[Login] login() returned:', ok)
    if (ok) navigate('/dashboard')
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 bg-blue-600 rounded-2xl mb-4 shadow-lg">
            <GraduationCap className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Welcome back</h1>
          <p className="text-gray-500 mt-1">Sign in to ExamGrader</p>
        </div>

        <Card>
          <CardBody className="p-8">
            {/* Global error */}
            {error && (
              <div className="flex items-start gap-3 bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 mb-5 text-sm">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} noValidate className="space-y-5">
              {/* Email */}
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1.5">
                  Email address
                </label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    id="email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    value={form.email}
                    onChange={handleChange}
                    placeholder="you@example.com"
                    className={`w-full pl-10 pr-4 py-2.5 text-sm border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition ${
                      validationErrors.email ? 'border-red-400' : 'border-gray-300'
                    }`}
                  />
                </div>
                {validationErrors.email && (
                  <p className="mt-1 text-xs text-red-600">{validationErrors.email}</p>
                )}
              </div>

              {/* Password */}
              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1.5">
                  Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    id="password"
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    value={form.password}
                    onChange={handleChange}
                    placeholder="••••••••"
                    className={`w-full pl-10 pr-4 py-2.5 text-sm border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition ${
                      validationErrors.password ? 'border-red-400' : 'border-gray-300'
                    }`}
                  />
                </div>
                {validationErrors.password && (
                  <p className="mt-1 text-xs text-red-600">{validationErrors.password}</p>
                )}
              </div>

              <Button
                type="submit"
                size="lg"
                loading={isLoading}
                className="w-full mt-2"
              >
                Sign in
              </Button>
            </form>
          </CardBody>
        </Card>

        <p className="text-center text-sm text-gray-500 mt-6">
          Don't have an account?{' '}
          <Link to="/register" className="text-blue-600 font-medium hover:underline">
            Create one
          </Link>
        </p>
      </div>
    </div>
  )
}
