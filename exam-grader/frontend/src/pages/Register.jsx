import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { GraduationCap, User, Mail, Lock, AlertCircle } from 'lucide-react'
import useAuthStore from '../store/authStore'
import { Button } from '../components/ui/button'
import { Card, CardBody } from '../components/ui/card'

export default function Register() {
  const navigate = useNavigate()
  const register   = useAuthStore((s) => s.register)
  const isLoading  = useAuthStore((s) => s.isLoading)
  const error      = useAuthStore((s) => s.error)
  const token      = useAuthStore((s) => s.token)
  const clearError = useAuthStore((s) => s.clearError)

  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [validationErrors, setValidationErrors] = useState({})

  useEffect(() => {
    if (token) navigate('/dashboard', { replace: true })
  }, [token, navigate])

  useEffect(() => {
    return () => clearError()
  }, [clearError])

  const validate = () => {
    const errors = {}
    if (!form.name.trim()) errors.name = 'Name is required'
    if (!form.email.trim()) errors.email = 'Email is required'
    else if (!/\S+@\S+\.\S+/.test(form.email)) errors.email = 'Enter a valid email'
    if (!form.password) errors.password = 'Password is required'
    else if (form.password.length < 8) errors.password = 'Password must be at least 8 characters'
    console.log('[Register] validate() errors:', errors)
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
    console.log('[Register] handleSubmit fired, form:', { ...form, password: '***' })
    const errors = validate()
    if (Object.keys(errors).length) {
      console.warn('[Register] Validation blocked submission:', errors)
      setValidationErrors(errors)
      return
    }
    console.log('[Register] Validation passed — calling register action')
    const ok = await register(form.name, form.email, form.password)
    console.log('[Register] register() returned:', ok)
    if (ok) navigate('/dashboard')
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 bg-blue-600 rounded-2xl mb-4 shadow-lg">
            <GraduationCap className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Create an account</h1>
          <p className="text-gray-500 mt-1">Start grading smarter with AI</p>
        </div>

        <Card>
          <CardBody className="p-8">
            {error && (
              <div className="flex items-start gap-3 bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 mb-5 text-sm">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} noValidate className="space-y-5">
              <div>
                <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1.5">
                  Full name
                </label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    id="name"
                    name="name"
                    type="text"
                    autoComplete="name"
                    value={form.name}
                    onChange={handleChange}
                    placeholder="Jane Smith"
                    className={`w-full pl-10 pr-4 py-2.5 text-sm border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition ${
                      validationErrors.name ? 'border-red-400' : 'border-gray-300'
                    }`}
                  />
                </div>
                {validationErrors.name && (
                  <p className="mt-1 text-xs text-red-600">{validationErrors.name}</p>
                )}
              </div>

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
                    autoComplete="new-password"
                    value={form.password}
                    onChange={handleChange}
                    placeholder="Min. 8 characters"
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
                Create account
              </Button>
            </form>
          </CardBody>
        </Card>

        <p className="text-center text-sm text-gray-500 mt-6">
          Already have an account?{' '}
          <Link to="/login" className="text-blue-600 font-medium hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
